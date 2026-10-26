"""Despesas (fixas e avulsas): regras de criar e listar sobre `compromisso_linha`. Chamado pela API, pelo painel e pelo MCP.

`ValueError` = dado inválido; `LookupError` = série não encontrada. Toda escrita grava `decisao` e recalcula A Pagar.
Consome: dinheiro.{planilha,compromissos,contas_pagar,valor}.
"""
import datetime as dt
import json
import re
import sqlite3
import unicodedata

from gabi.dinheiro import contas_pagar as cp, planilha
from gabi.dinheiro.compromissos import _serie
from gabi.dinheiro.valor import formatar, para_centavos

CAMPOS = {"nome", "extrato", "apelidos", "vencimento", "ajuste_dia_util", "valor_tipo", "valor_padrao", "forma", "conta", "cartao", "pix"}


def _slug(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "item"


def _id_unico(con, tabela: str, base: str) -> str:
    cand, n = base, 2
    while con.execute(f"select 1 from {tabela} where id=?", (cand,)).fetchone():
        cand, n = f"{base}-{n}", n + 1
    return cand


def validar_linha(con, d: dict, proprio: str | None) -> dict:
    """Passa pela MESMA validação da planilha; devolve a linha normalizada ou levanta ValueError com o motivo."""
    cols = planilha.COLUNAS_COMPROMISSOS
    apelidos = d.get("apelidos") or []
    if not isinstance(apelidos, list) or not all(isinstance(a, str) for a in apelidos):
        raise ValueError("apelidos deve ser uma lista de textos")
    v = {**d, "apelidos": "; ".join(apelidos), "ativo": "sim"}  # a validação das regras vale mesmo para linha desativada
    celulas = ["" if v.get(c) is None else v.get(c) for c in cols]
    idx = {c: i for i, c in enumerate(cols)}
    linha, motivo = planilha._linha(idx, 2, celulas)
    if linha is None:
        raise ValueError(motivo or "linha inválida")
    for o in con.execute("select id, valido_de, valido_ate from compromisso_linha where excluido_em is null and id<>?", (proprio or "",)):
        if _serie(o["id"]) == _serie(linha["id"]) and planilha._meses_sobrepoe(linha, {"valido_de": o["valido_de"], "valido_ate": o["valido_ate"]}):
            raise ValueError(f"os meses de validade se sobrepõem aos de {o['id']}")
    return linha


def gravar_linha(con, linha: dict, ativo: bool, obs, inserir: bool, tipo: str = "fixa") -> None:
    args = (linha["nome"], linha["extrato"], json.dumps(linha["apelidos"], ensure_ascii=False), linha["vencimento"], linha["ajuste_dia_util"],
            linha["valor_tipo"], None if linha["valor_padrao"] is None else para_centavos(round(linha["valor_padrao"], 2)), linha["forma"],
            linha["conta"], linha["cartao"], linha["documento"], linha["pix"], int(ativo), linha["valido_de"], linha["valido_ate"], obs)
    if inserir:
        con.execute("insert into compromisso_linha(id, nome, extrato, apelidos, vencimento, ajuste_dia_util, valor_tipo, valor_padrao_centavos, forma, conta, cartao, "
                    "documento, pix, ativo, valido_de, valido_ate, obs, tipo) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (linha["id"], *args, tipo))
    else:
        con.execute("update compromisso_linha set nome=?, extrato=?, apelidos=?, vencimento=?, ajuste_dia_util=?, valor_tipo=?, valor_padrao_centavos=?, forma=?, "
                    "conta=?, cartao=?, documento=?, pix=?, ativo=?, valido_de=?, valido_ate=?, obs=? where id=?", (*args, linha["id"]))


def _auditar(con, agora: dt.datetime, quem: str, origem: str, o_que: str) -> None:
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?,?)", (agora.astimezone(dt.timezone.utc).isoformat(), quem, o_que, origem))


def _campos_validos(campos: dict) -> dict:
    extra = set(campos) - CAMPOS
    if extra:
        raise ValueError(f"campos desconhecidos: {sorted(extra)}")
    nome = campos.get("nome")
    if not isinstance(nome, str) or not nome.strip():
        raise ValueError("nome é obrigatório")
    return {**campos, "nome": nome.strip()}


def _gravar_nova(con, agora, quem, origem, dado: dict, tipo: str, hoje: dt.date) -> dict:
    linha = validar_linha(con, dado, None)
    con.execute("begin")
    try:
        gravar_linha(con, linha, True, None, True, tipo)
        _auditar(con, agora, quem, origem, f"despesa {_serie(linha['id'])} criada ({tipo})")
        con.execute("commit")
    except Exception:
        con.execute("rollback")
        raise
    cp.atualizar_compromissos(con, hoje, agora)
    return _item(con, hoje, _serie(linha["id"]))


def criar_fixa(con, agora: dt.datetime, quem: str, origem: str, campos: dict) -> dict:
    hoje = agora.date()
    c = _campos_validos(campos)
    dado = {**c, "id": _id_unico(con, "compromisso_linha", _slug(c["nome"])), "extrato": c.get("extrato") or c["nome"], "valido_de": hoje.strftime("%Y-%m")}
    return _gravar_nova(con, agora, quem, origem, dado, "fixa", hoje)


def criar_avulsa(con, agora: dt.datetime, quem: str, origem: str, campos: dict, data: str) -> dict:
    hoje = agora.date()
    try:
        d = dt.date.fromisoformat(data)
    except (TypeError, ValueError):
        raise ValueError(f"data '{data}' não é AAAA-MM-DD")
    c = _campos_validos(campos)
    mes = data[:7]
    base = f"{_slug(c['nome'])}-{mes.replace('-', '')}"
    dado = {**c, "id": _id_unico(con, "compromisso_linha", base), "extrato": c.get("extrato") or c["nome"], "vencimento": f"dia:{d.day}",
            "valido_de": mes, "valido_ate": mes}
    return _gravar_nova(con, agora, quem, origem, dado, "avulsa", hoje)


def serie_de(con, id_: str) -> list[sqlite3.Row]:
    """Versões não excluídas da série, da mais antiga à mais nova (`valido_de` vazio = desde sempre)."""
    linhas = [r for r in con.execute("select * from compromisso_linha where excluido_em is null") if _serie(r["id"]) == _serie(id_)]
    if not linhas:
        raise LookupError(f"despesa {id_} não existe")
    return sorted(linhas, key=lambda r: (r["valido_de"] or "", r["id"]))


def _item(con, hoje: dt.date, serie: str) -> dict:
    vs = serie_de(con, serie)
    u = vs[-1]
    mes_hoje = hoje.strftime("%Y-%m")
    encerrada = bool(u["valido_ate"]) and u["valido_ate"] < mes_hoje
    ids = [v["id"] for v in vs]
    prox = con.execute(f"select min(vencimento_util) from compromisso where origem='planilha' and estado<>'pago' and vencimento_util>=? "
                       f"and linha_id in ({','.join('?' * len(ids))})", (hoje.isoformat(), *ids)).fetchone()[0]
    return {"id": _serie(serie), "versao_id": u["id"], "nome": u["nome"], "tipo": u["tipo"],
            "valor": None if u["valor_padrao_centavos"] is None else formatar(u["valor_padrao_centavos"]),
            "vencimento": u["vencimento"], "forma": u["forma"], "valido_de": u["valido_de"], "valido_ate": u["valido_ate"],
            "situacao": "encerrada" if encerrada else "ativa", "proximo_vencimento": None if encerrada else prox,
            "versoes": [{"id": v["id"], "valido_de": v["valido_de"], "valido_ate": v["valido_ate"],
                         "valor": None if v["valor_padrao_centavos"] is None else formatar(v["valor_padrao_centavos"]), "vencimento": v["vencimento"]} for v in vs]}


def listar(con, hoje: dt.date, tipo: str | None = None, situacao: str | None = None) -> list[dict]:
    series = {}
    for r in con.execute("select id from compromisso_linha where excluido_em is null order by coalesce(linha_planilha, 1000000 + rowid), id"):
        series.setdefault(_serie(r["id"]), None)
    itens = [_item(con, hoje, s) for s in series]
    return [i for i in itens if (tipo is None or i["tipo"] == tipo) and (situacao is None or i["situacao"] == situacao)]
