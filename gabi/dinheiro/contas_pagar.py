"""Compromissos do mês (gerar + conciliar), contas a pagar e caixa único. Consome: dinheiro.{repositorio,compromissos,conciliacao,caixa}."""
import datetime as dt
import json
import re
from collections import Counter
from dataclasses import dataclass, field

from gabi.dinheiro import caixa, compromissos, conciliacao, repositorio
from gabi.dinheiro.valor import para_centavos


@dataclass
class ResumoCompromissos:
    gerados: int
    estados: dict
    invalidas: list = field(default_factory=list)


def atualizar_compromissos(con, hoje: dt.date, agora: dt.datetime, docs=()) -> ResumoCompromissos:
    """Gera os compromissos do mês corrente e do seguinte, concilia com o extrato e grava. Idempotente."""
    leitura = repositorio.ler_leitura(con)
    invalidas: list = []
    comps = compromissos.gerar(repositorio.FontesBanco(con), leitura, list(docs), hoje, invalidas)
    donos = caixa.dono_tokens(repositorio.titulares(con)) or None
    res, novos = conciliacao.conciliar(comps, repositorio.txs_para_conciliar(con, hoje), repositorio.vinculos(con),
                                       repositorio.estado_contas(con), leitura["valores"], leitura["params"], hoje, agora, donos)
    repositorio.gravar_resultado(con, comps, res, novos, agora)
    return ResumoCompromissos(len(comps), dict(Counter(r["estado"] for r in res.values())), invalidas)


# ---------------- contas a pagar ----------------
GRUPOS = ("atrasadas", "hoje", "proximas", "adiante", "debito_automatico", "a_conferir", "pagas")


def _cent(reais):
    return None if reais is None else para_centavos(round(reais, 2))


def contas_a_pagar(con, hoje: dt.date, ate: dt.date | None = None) -> dict:
    """Compromissos agrupados como o painel mostra. `ate` corta o que vence depois (nunca as atrasadas)."""
    saida = {g: [] for g in GRUPOS}
    limite_proximas = hoje + dt.timedelta(days=7)
    for r in con.execute("select * from compromisso order by vencimento_util, id"):
        d = json.loads(r["dados"] or "{}")
        vu = dt.date.fromisoformat(r["vencimento_util"])
        item = {"id": r["id"], "nome": r["nome"], "vencimento": r["vencimento"], "vencimento_util": r["vencimento_util"],
                "valor_centavos": r["valor_centavos"], "valor_fonte": r["valor_fonte"], "estado": r["estado"],
                "motivo": r["motivo"], "forma": r["forma"]}
        e = r["estado"]
        if e == "pago":
            item.update(pago_em=d.get("pago_em"), tx_id=d.get("tx_id"), metodo=d.get("metodo"), diferenca_centavos=_cent(d.get("diferenca")))
            saida["pagas"].append(item)
        elif e == "debito_automatico":
            saida["debito_automatico"].append(item)
        elif e == "a_conferir":
            saida["a_conferir"].append(item)
        elif e == "atrasado" or vu < hoje:
            item["dias_atraso"] = (hoje - vu).days
            saida["atrasadas"].append(item)
        elif ate is not None and vu > ate:
            continue
        elif vu == hoje:
            saida["hoje"].append(item)
        elif vu <= limite_proximas:
            saida["proximas"].append(item)
        else:
            saida["adiante"].append(item)
    return saida


def marcar_paga_manual(con, compromisso_id: str, por: str, hoje: dt.date) -> None:
    """Baixa manual: registra 'pago' em Valores do mês; a próxima rodada concilia (vale só sem lançamento no extrato)."""
    r = con.execute("select linha_id from compromisso where id=?", (compromisso_id,)).fetchone()
    if r is None:
        raise LookupError(f"compromisso {compromisso_id} não existe")
    m = re.search(r":(\d{4}-\d{2})$", compromisso_id)
    if not r["linha_id"] or not m:
        raise ValueError("baixa manual só vale para compromisso de linha (não fatura nem documento avulso)")
    linha, mes = r["linha_id"], m.group(1)
    if con.execute("select 1 from compromisso_linha where id=?", (linha,)).fetchone() is None:
        raise ValueError(f"a linha {linha} não existe mais nos Cadastros")
    if con.execute("select 1 from valor_do_mes where tipo='pago' and compromisso=? and mes=?", (linha, mes)).fetchone():
        return  # idempotente
    con.execute("begin")
    try:
        con.execute("insert into valor_do_mes(mes, compromisso, tipo, data_pagamento, origem) values (?,?, 'pago', ?, 'manual (painel)')",
                    (mes, linha, hoje.isoformat()))
        con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'api')",
                    (dt.datetime.now(dt.timezone.utc).isoformat(), por, f"baixa manual: {compromisso_id}"))
        con.execute("commit")
    except BaseException:
        con.execute("rollback")
        raise


# ---------------- caixa único ----------------
@dataclass(frozen=True)
class CaixaUnico:
    saldo_centavos: int
    contas: list
    faturas_abertas_centavos: int


JANELA_PAGAMENTO_DIAS = 7  # o débito da fatura pode sair alguns dias antes do vencimento


def faturas_abertas(con, em: dt.date) -> list:
    """Faturas ainda não pagas dos cartões liberados (id, conta_id, vencimento, total_centavos).
    O banco demora a trocar PAST_DUE_UNCONFIRMED por PAID: se já saiu da conta BANK um débito do mesmo valor
    entre (vencimento − 7 dias) e `em`, a fatura está paga e não pode contar de novo ao lado do saldo que já caiu."""
    return con.execute(
        "select f.id, f.conta_id, f.vencimento, f.total_centavos from fatura f join conta c on c.id=f.conta_id "
        "where c.estado='sim' and c.tipo='CREDIT' and c.excluido_em is null and upper(coalesce(f.pagamento_status,''))<>'PAID' "
        "and not (upper(coalesce(f.pagamento_status,''))='PAST_DUE_UNCONFIRMED' and f.total_centavos>0 and exists ("
        "  select 1 from lancamento l join conta b on b.id=l.conta_id where b.tipo='BANK' and l.valor_centavos=-f.total_centavos "
        "  and l.data>=date(f.vencimento, ?) and l.data<=?)) order by f.vencimento",
        (f"-{JANELA_PAGAMENTO_DIAS} days", em.isoformat())).fetchall()


def caixa_unico(con, em: dt.date) -> CaixaUnico:
    """Soma o saldo mais recente (até `em`) das contas BANK que o Ricardo liberou (estado 'sim'). Cartão não entra no saldo;
    as faturas ainda não pagas dos cartões liberados (ver `faturas_abertas`) somam em `faturas_abertas_centavos`."""
    fim = f"{em.isoformat()}T23:59:59"
    contas = []
    for c in con.execute("select id, apelido, externo_id from conta where estado='sim' and tipo='BANK' and excluido_em is null order by id"):
        s = con.execute("select em, saldo_centavos from saldo where conta_id=? and em<=? order by em desc limit 1", (c["id"], fim)).fetchone()
        if s:
            contas.append({"apelido": c["apelido"] or c["externo_id"], "saldo_centavos": s["saldo_centavos"], "em": s["em"]})
    abertas = sum(f["total_centavos"] for f in faturas_abertas(con, em))
    return CaixaUnico(sum(c["saldo_centavos"] for c in contas), contas, abertas)
