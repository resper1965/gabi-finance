"""Ponte entre o banco e a lógica portada do gabi-fin (gerar/conciliar). TODO o SQL da conciliação vive aqui.

A lógica portada trabalha em reais (float) como no gabi-fin; o banco guarda centavos (R7). A conversão acontece só nesta fronteira.
Consome: db (compromisso_linha, parametro, valor_do_mes, lancamento, conta, fatura, conta_estado, compromisso, conciliacao).
"""
import datetime as dt
import json

from gabi.dinheiro import planilha
from gabi.dinheiro.valor import para_centavos

_CONJUNTOS = {"horas_envio", "horas_silenciosas", "bancos_pj"}  # no JSON são listas; a lógica espera set
_DADOS = ("valor_tipo", "valor_fonte", "extrato_chaves", "cartao_account_id", "doc_id", "doc_ids", "aviso", "pix", "payment_status")
JANELA_TX_DIAS = 120  # lançamentos considerados na conciliação (a janela de vencimento é de ~10 dias)


def _real(centavos):
    return None if centavos is None else centavos / 100.0


def _cent(reais):
    return None if reais is None else para_centavos(round(reais, 2))


# ---------------- Cadastros (linhas, parâmetros, valores do mês) ----------------
def gravar_leitura(con, leitura: dict) -> None:
    """Substitui os Cadastros pelo conteúdo validado (formato de planilha.validar). Atômico: tudo ou nada."""
    con.execute("begin")
    try:
        con.execute("delete from valor_do_mes")
        con.execute("delete from compromisso_linha")
        con.execute("delete from parametro")
        for l in leitura["linhas"]:
            con.execute(
                "insert into compromisso_linha(id, nome, extrato, apelidos, vencimento, ajuste_dia_util, valor_tipo, valor_padrao_centavos, "
                "forma, conta, cartao, documento, pix, ativo, valido_de, valido_ate, linha_planilha) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (l["id"], l["nome"], l["extrato"], json.dumps(l.get("apelidos") or [], ensure_ascii=False), l["vencimento"],
                 l.get("ajuste_dia_util") or "adia", l.get("valor_tipo") or "fixo", _cent(l.get("valor_padrao")), l.get("forma") or "",
                 l.get("conta") or "", l.get("cartao") or "", l.get("documento") or "", l.get("pix") or "",
                 1 if l.get("ativo", True) else 0, l.get("valido_de"), l.get("valido_ate"), l.get("linha_planilha")))
        for v in leitura.get("valores", []):
            con.execute(
                "insert into valor_do_mes(mes, compromisso, tipo, valor_centavos, vencimento, data_pagamento, origem, linha_planilha) values (?,?,?,?,?,?,?,?)",
                (v["mes"], v["compromisso"], v["tipo"], _cent(v.get("valor")), v.get("vencimento"), v.get("data_pagamento"),
                 v.get("origem"), v.get("linha_planilha")))
        for k, v in (leitura.get("params") or {}).items():
            con.execute("insert into parametro(chave, valor) values (?,?)",
                        (k, json.dumps(sorted(v) if isinstance(v, (set, frozenset)) else v, ensure_ascii=False)))
        con.execute("commit")
    except BaseException:
        con.execute("rollback")
        raise


def ler_leitura(con) -> dict:
    """{'linhas', 'params', 'valores'} no formato que o gerar/conciliar esperam. Só linhas ativas e não excluídas."""
    linhas = []
    # Linha/valor criados no painel não têm número de planilha: recebem um número alto e crescente (o mais recente vence,
    # como na planilha, onde linha de baixo prevalece) — e a lógica portada ordena por esse número.
    for r in con.execute("select rowid as rid, * from compromisso_linha where ativo=1 and excluido_em is null "
                         "order by coalesce(linha_planilha, 1000000 + rowid), id"):
        linhas.append({"id": r["id"], "nome": r["nome"], "extrato": r["extrato"], "apelidos": json.loads(r["apelidos"]),
                       "vencimento": r["vencimento"], "ajuste_dia_util": r["ajuste_dia_util"], "valor_tipo": r["valor_tipo"],
                       "valor_padrao": _real(r["valor_padrao_centavos"]), "forma": r["forma"], "conta": r["conta"],
                       "cartao": r["cartao"], "documento": r["documento"], "pix": r["pix"], "ativo": True,
                       "valido_de": r["valido_de"], "valido_ate": r["valido_ate"],
                       "linha_planilha": r["linha_planilha"] if r["linha_planilha"] is not None else 1_000_000 + r["rid"]})
    ativos = {l["id"] for l in linhas}
    params = {k: (set(v) if isinstance(v, set) else v) for k, v in planilha.PADROES.items()}
    for r in con.execute("select chave, valor from parametro"):
        v = json.loads(r["valor"])
        params[r["chave"]] = set(v) if r["chave"] in _CONJUNTOS else v
    valores = [{"mes": r["mes"], "compromisso": r["compromisso"], "tipo": r["tipo"], "valor": _real(r["valor_centavos"]),
                "vencimento": r["vencimento"], "data_pagamento": r["data_pagamento"], "origem": r["origem"] or "",
                "linha_planilha": r["linha_planilha"] if r["linha_planilha"] is not None else 1_000_000 + r["id"]}
               for r in con.execute("select * from valor_do_mes order by coalesce(linha_planilha, 1000000 + id), id") if r["compromisso"] in ativos]
    return {"linhas": linhas, "params": params, "valores": valores}


# ---------------- o que o `gerar` lê do banco ----------------
class FontesBanco:
    def __init__(self, con):
        self.con = con

    def debitos(self, hoje: dt.date):
        """Débitos de conta BANK não-PJ até hoje (inclui pendentes, como o gabi-fin), mais recentes primeiro: (descricao, valor, data, account_id, id)."""
        rows = self.con.execute(
            "select l.descricao_original, l.valor_centavos, l.data, c.externo_id, l.externo_id from lancamento l join conta c on c.id=l.conta_id "
            "where c.tipo='BANK' and l.valor_centavos<0 and substr(l.data,1,10)<=? and c.pj=0 "
            "order by l.data desc, l.externo_id", (hoje.isoformat(),)).fetchall()
        return [(r[0], _real(r[1]), r[2], r[3], r[4]) for r in rows]

    def faturas(self):
        return [{"account_id": r["account_id"], "nome": r["nome"] or "", "vencimento": r["vencimento"][:10],
                 "total": _real(r["total_centavos"]), "status": r["pagamento_status"]}
                for r in self.con.execute("select f.account_id, c.apelido as nome, f.vencimento, f.total_centavos, f.pagamento_status "
                                          "from fatura f left join conta c on c.id=f.conta_id where f.vencimento is not null and f.vencimento<>''")]

    def anterior(self):
        return {r["id"]: (_real(r["valor_centavos"]), r["valor_fonte"]) for r in self.con.execute("select id, valor_centavos, valor_fonte from compromisso")}


# ---------------- o que o `conciliar` lê do banco ----------------
def txs_para_conciliar(con, hoje: dt.date) -> list[dict]:
    desde = (hoje - dt.timedelta(days=JANELA_TX_DIAS)).isoformat()
    ligados = {r[0] for r in con.execute("select tx_id from conciliacao")}
    saida = []
    for r in con.execute("select l.externo_id, c.externo_id as conta, c.tipo, l.data, l.descricao_original, l.valor_centavos, l.categoria_banco, l.natureza "
                         "from lancamento l join conta c on c.id=l.conta_id order by l.data, l.externo_id"):
        if r["data"] >= desde or r["externo_id"] in ligados:
            saida.append({"id": r["externo_id"], "account_id": r["conta"], "tipo_conta": r["tipo"], "data": r["data"],
                          "descricao": r["descricao_original"], "valor": _real(r["valor_centavos"]), "categoria": r["categoria_banco"],
                          "natureza": r["natureza"]})
    return saida


def estado_contas(con) -> dict:
    return {r["account_id"]: {"tipo": r["tipo"], "pj": r["pj"], "banco": r["banco"], "nome": r["nome"],
                              "ult_sync_ok": r["ult_sync_ok"], "ult_tx_real": r["ult_tx_real"]}
            for r in con.execute("select * from conta_estado")}


def vinculos(con) -> dict:
    return {r["tx_id"]: r["compromisso_id"] for r in con.execute("select tx_id, compromisso_id from conciliacao")}


def titulares(con) -> list[str]:
    return [r[0] for r in con.execute("select distinct titular from conta where titular is not null and tipo<>'CREDIT'")]


# ---------------- gravação do resultado ----------------
def gravar_resultado(con, comps, resultado, novos_vinculos, agora: dt.datetime) -> None:
    """Grava a rodada: compromissos (insert or replace) e vínculos novos (insert or ignore: o primeiro vínculo de um
    lançamento fica). Baixa manual que saiu dos Cadastros tem o vínculo `manual:` apagado. Idempotente e atômico."""
    ts = agora.isoformat(timespec="seconds")
    manuais = {v[0] for v in novos_vinculos if v[2] == "manual"}
    con.execute("begin")
    try:
        for comp in comps:
            r = resultado.get(comp["id"])
            if r is None:
                continue
            dados = {k: comp.get(k) for k in _DADOS}
            dados.update(r)
            con.execute(
                "insert or replace into compromisso(id, origem, linha_id, nome, vencimento, vencimento_util, valor_centavos, valor_fonte, forma, "
                "account_id, estado, motivo, dados, atualizado_em) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (comp["id"], comp.get("origem"), comp.get("linha_id"), comp.get("nome"), comp.get("vencimento"), comp.get("vencimento_util"),
                 _cent(comp.get("valor")), comp.get("valor_fonte"), comp.get("forma"), comp.get("account_id"), r["estado"], r.get("motivo"),
                 json.dumps(dados, ensure_ascii=False), ts))
            if f"manual:{comp['id']}" not in manuais:
                con.execute("delete from conciliacao where tx_id=?", (f"manual:{comp['id']}",))
        for tx_id, comp_id, metodo, dif in novos_vinculos:
            con.execute("insert or ignore into conciliacao(tx_id, compromisso_id, metodo, diferenca_centavos, criado_em) values (?,?,?,?,?)",
                        (tx_id, comp_id, metodo, _cent(dif), ts))
        con.execute("commit")
    except BaseException:
        con.execute("rollback")
        raise
