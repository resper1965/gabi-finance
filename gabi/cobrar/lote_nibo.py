"""Lote diário "Lançar na PJ": despesas da Bekaa pagas no PF viram agendamento a pagar ao sócio no Nibo. ÚNICA gravação externa (R2):
só executa com o texto de confirmação IGUAL, byte a byte, ao que o servidor gerou (409 se divergir). Idempotente por `reference gabi:<id>`.
Consome: db (lancamento, empresa.relacao, categoria.nibo_category_id, parametro nibo_socio_id), fontes.nibo_escrita."""
import datetime as dt
import json
from dataclasses import dataclass
from typing import Callable

from gabi.fontes.nibo import ErroNibo


class ConfirmacaoDivergente(ValueError):
    """O texto enviado não é o que o servidor gerou (a API responde 409 e nada é gravado)."""


@dataclass(frozen=True)
class ItemLote:
    lancamento_id: int
    data: str
    descricao: str | None
    valor_centavos: int


@dataclass(frozen=True)
class Lote:
    id: int
    dia: dt.date
    itens: list[ItemLote]
    texto_confirmacao: str


@dataclass(frozen=True)
class ResultadoLote:
    ok: int
    erro: int


def _agora() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _brl(centavos: int) -> str:
    return f"R$ {centavos // 100:,}".replace(",", ".") + f",{centavos % 100:02d}"


def _texto_lote(itens: list[ItemLote]) -> str:
    return f"Lançar no Nibo da Bekaa: {len(itens)} despesas, {_brl(sum(i.valor_centavos for i in itens))}."


def montar_lote(con, dia: dt.date) -> Lote:
    """Despesas da Bekaa (`pj_titular`) pagas em conta PF e ainda sem agendamento ok no Nibo. Remonta o lote aberto do dia, se houver."""
    itens = [ItemLote(r["id"], r["data"], r["descricao_original"], -r["valor_centavos"]) for r in con.execute(
        "select l.id, l.data, l.descricao_original, l.valor_centavos from lancamento l join conta c on c.id=l.conta_id "
        "join empresa e on e.id=l.empresa_id where e.relacao='pj_titular' and l.valor_centavos<0 and c.pj=0 and not exists ("
        "  select 1 from lote_nibo_item i where i.lancamento_id=l.id and i.estado='ok') order by l.data, l.id")]
    texto = _texto_lote(itens)
    aberto = con.execute("select id from lote_nibo where dia=? and estado='montado'", (dia.isoformat(),)).fetchone()
    if aberto:
        lote_id = aberto["id"]
        con.execute("delete from lote_nibo_item where lote_id=?", (lote_id,))
        con.execute("update lote_nibo set texto_confirmacao=? where id=?", (texto, lote_id))
    else:
        lote_id = con.execute("insert into lote_nibo(dia, texto_confirmacao, criado_em) values (?,?,?)", (dia.isoformat(), texto, _agora())).lastrowid
    for i in itens:
        con.execute("insert into lote_nibo_item(lote_id, lancamento_id) values (?,?)", (lote_id, i.lancamento_id))
    return Lote(lote_id, dia, itens, texto)


def _marcar(con, lote_id, lancamento_id, estado, schedule_id=None, erro=None):
    con.execute("update lote_nibo_item set estado=?, schedule_id=coalesce(?, schedule_id), erro=? where lote_id=? and lancamento_id=?",
                (estado, schedule_id, erro, lote_id, lancamento_id))


def executar_lote(con, lote_id: int, confirmacao: str, nibo, *, baixar_comprovante: Callable[[int], "tuple[str, bytes]"] | None = None) -> ResultadoLote:
    """Grava no Nibo os itens do lote. Erro num item não desfaz os outros (fica `erro` e volta no próximo lote). Repetir é seguro."""
    lote = con.execute("select * from lote_nibo where id=?", (lote_id,)).fetchone()
    if lote is None:
        raise LookupError(f"lote {lote_id} não existe")
    if confirmacao != lote["texto_confirmacao"]:
        raise ConfirmacaoDivergente("a confirmação não é igual ao texto gerado pelo servidor; nada foi gravado")
    if lote["estado"] == "executado":
        return ResultadoLote(0, 0)
    socio = con.execute("select valor from parametro where chave='nibo_socio_id'").fetchone()
    if socio is None:
        raise ValueError("falta cadastrar o sócio do Nibo (parâmetro nibo_socio_id); nada foi gravado")
    socio = json.loads(socio["valor"])
    con.execute("update lote_nibo set estado='confirmado' where id=?", (lote_id,))
    ok = erro = 0
    for it in con.execute("select * from lote_nibo_item where lote_id=? and estado in ('pendente','erro') order by lancamento_id", (lote_id,)).fetchall():
        lid = it["lancamento_id"]
        l = con.execute("select l.data, l.valor_centavos, coalesce(l.estabelecimento, l.descricao_original) as desc, c.nibo_category_id as cat "
                        "from lancamento l left join categoria c on c.id=l.categoria_id where l.id=?", (lid,)).fetchone()
        if not l["cat"]:
            _marcar(con, lote_id, lid, "erro", erro="categoria sem equivalente no Nibo (cadastre o nibo_category_id)")
            erro += 1
            continue
        ref = f"gabi:{lid}"
        try:
            sid = it["schedule_id"]  # já criado numa tentativa anterior (o anexo é que faltou): só retoma dali
            if not sid:
                existente = nibo.agendamento_por_reference(ref)  # idempotência: um agendamento por lançamento, mesmo se rodar duas vezes
                sid = existente["scheduleId"] if existente else nibo.criar_agendamento_debito(
                    stakeholder_id=socio, valor_centavos=-l["valor_centavos"], data=l["data"], category_id=l["cat"], descricao=l["desc"], reference=ref)
                _marcar(con, lote_id, lid, "erro", schedule_id=sid, erro="anexo pendente")  # guarda o id já: se o anexo falhar, o reprocesso só anexa
            vinc = con.execute("select c.paperless_id from comprovante_vinculo v join comprovante c on c.id=v.comprovante_id "
                               "where v.lancamento_id=? and v.estado='confirmado' order by v.id limit 1", (lid,)).fetchone()
            if vinc and baixar_comprovante:
                nome, conteudo = baixar_comprovante(vinc["paperless_id"])
                nibo.anexar_arquivo(sid, nome, conteudo)
            _marcar(con, lote_id, lid, "ok", schedule_id=sid)
            ok += 1
        except (ErroNibo, ValueError, OSError) as e:
            _marcar(con, lote_id, lid, "erro", erro=str(e)[:300])
            erro += 1
    con.execute("update lote_nibo set estado='executado' where id=?", (lote_id,))
    return ResultadoLote(ok, erro)


def _baixa(con, lancamento_id: int, credito_id: int):
    it = con.execute("select i.schedule_id, i.baixa_credito_id, l.valor_centavos, coalesce(l.estabelecimento, l.descricao_original) as desc "
                     "from lote_nibo_item i join lancamento l on l.id=i.lancamento_id where i.lancamento_id=? and i.estado='ok' "
                     "order by i.lote_id desc limit 1", (lancamento_id,)).fetchone()
    if it is None:
        raise ValueError("a despesa ainda não foi lançada no Nibo")
    c = con.execute("select l.data, l.valor_centavos, cn.pj from lancamento l join conta cn on cn.id=l.conta_id where l.id=?", (credito_id,)).fetchone()
    if c is None or not c["pj"] or c["valor_centavos"] != -it["valor_centavos"]:
        raise ValueError("o crédito precisa ser uma entrada em conta PJ de valor igual ao da despesa")
    return it, c


def texto_baixa(con, lancamento_id: int, credito_id: int) -> str:
    it, c = _baixa(con, lancamento_id, credito_id)
    dia = dt.date.fromisoformat(c["data"][:10])
    return f"Baixar no Nibo: {it['desc']}, {_brl(c['valor_centavos'])}, pelo Pix de {dia:%d/%m}."


def executar_baixa(con, lancamento_id: int, credito_id: int, confirmacao: str, nibo, *, account_id: str) -> None:
    """Dá baixa no agendamento quando a PJ reembolsa o sócio; exige a mesma confirmação textual. Repetir não baixa de novo."""
    it, c = _baixa(con, lancamento_id, credito_id)
    if confirmacao != texto_baixa(con, lancamento_id, credito_id):
        raise ConfirmacaoDivergente("a confirmação não é igual ao texto gerado pelo servidor; nada foi gravado")
    if it["baixa_credito_id"] == credito_id:
        return
    nibo.baixar_pagamento(it["schedule_id"], account_id=account_id, data=c["data"][:10], valor_centavos=c["valor_centavos"], identifier=f"gabi:baixa:{credito_id}")
    con.execute("update lote_nibo_item set baixa_credito_id=? where lancamento_id=? and estado='ok'", (credito_id, lancamento_id))
