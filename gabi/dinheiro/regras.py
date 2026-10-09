"""Regras e sugestões (R1): a Gabi sugere; só o Ricardo, ao aprovar, faz uma regra nascer ativa e valer no passado e no futuro.

Regra casa por regex (sem caixa) com a descrição original OU com o estabelecimento normalizado. Aplicar nunca sobrescreve
decisão do Ricardo (origem `voce`) nem resultado de regra anterior. Consome: db (regra, sugestao, lancamento, decisao).
"""
import datetime as dt
import json
import math
import re

CAMPOS_ACAO = ("categoria_id", "para_quem_id", "empresa_id")
_CAMPO = {"categoria_id": "categoria", "para_quem_id": "para_quem", "empresa_id": "empresa"}
_TABELA = {"categoria_id": ("categoria", "id"), "para_quem_id": ("pessoa", "id"), "empresa_id": ("empresa", "id")}
HISTORICO_MESES = 6


class ConflitoDeEstado(ValueError):
    """A sugestão já foi decidida (a API responde 409, não 400)."""


def _agora() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _decisao(con, quem: str, o_que: str) -> None:
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'regras')", (_agora(), quem, o_que))


def casa(rx: re.Pattern, descricao: str | None, estabelecimento: str | None) -> bool:
    return bool(rx.search(descricao or "") or rx.search(estabelecimento or ""))


def _validar(con, padrao, acao) -> tuple[re.Pattern, dict]:
    if not isinstance(padrao, str) or not padrao.strip():
        raise ValueError("a regra precisa de um padrão")
    try:
        rx = re.compile(padrao, re.I)
    except re.error as e:
        raise ValueError(f"padrão inválido: {e}") from e
    if not isinstance(acao, dict) or not acao:
        raise ValueError("a regra precisa de ao menos uma ação (categoria, para quem ou empresa)")
    if set(acao) - set(CAMPOS_ACAO):
        raise ValueError(f"ação com campos desconhecidos: {sorted(set(acao) - set(CAMPOS_ACAO))}")
    for col, valor in acao.items():
        tabela, pk = _TABELA[col]
        if valor is None or con.execute(f"select 1 from {tabela} where {pk}=?", (valor,)).fetchone() is None:
            raise ValueError(f"{col}={valor!r} não existe")
    return rx, dict(acao)


def _anteriores(con, rid: int | None) -> list[re.Pattern]:
    """Regras ATIVAS que vencem esta na ordem do classificador (a primeira que casa vale): as de id menor; sem id (regra nova/prévia), todas."""
    saida = []
    for r in con.execute("select padrao from regra where ativa=1" + (" and id<?" if rid is not None else ""), (rid,) if rid is not None else ()):
        try:
            saida.append(re.compile(r["padrao"], re.I))
        except re.error:
            continue
    return saida


def _linhas_afetadas(con, rx, acao, rid: int | None = None):
    """(id, [colunas que mudariam]) dos lançamentos em que a regra faria diferença. Não toca no que uma regra anterior já pega:
    no classificador a primeira regra que casa vale, e as seguintes não completam os campos que ela deixou."""
    anteriores = _anteriores(con, rid)
    for r in con.execute("select * from lancamento"):
        if not casa(rx, r["descricao_original"], r["estabelecimento"]):
            continue
        if any(casa(a, r["descricao_original"], r["estabelecimento"]) for a in anteriores):
            continue
        mudam = [c for c in acao if not (r[f"{_CAMPO[c]}_origem"] in ("voce", "regra") and r[c] is not None)]
        if mudam:
            yield r["id"], mudam


def _aplicar(con, rx, acao, rid: int | None = None) -> int:
    n = 0
    for lid, cols in list(_linhas_afetadas(con, rx, acao, rid)):
        for c in cols:
            con.execute(f"update lancamento set {c}=?, {_CAMPO[c]}_origem='regra' where id=?", (acao[c], lid))
        n += 1
    return n


def contar_afetados(con, padrao: str, acao: dict, hoje: dt.date) -> dict:
    """Quantos lançamentos a regra mudaria no passado e a média MENSAL que ela deve pegar daqui para a frente (últimos 6 meses)."""
    rx, acao = _validar(con, padrao, acao)
    passado = sum(1 for _ in _linhas_afetadas(con, rx, acao))
    desde = (hoje - dt.timedelta(days=30 * HISTORICO_MESES)).isoformat()
    recentes = sum(1 for r in con.execute("select descricao_original, estabelecimento from lancamento where data>=?", (desde,))
                   if casa(rx, r["descricao_original"], r["estabelecimento"]))
    return {"passado": passado, "futuro_estimado": round(recentes / HISTORICO_MESES, 1)}  # média por mês, 1 casa


def contar_casados(con, padrao: str) -> int:
    """Quantos lançamentos o padrão pega hoje (com a ação já aplicada ou não)."""
    try:
        rx = re.compile(padrao, re.I)
    except re.error:
        return 0
    return sum(1 for r in con.execute("select descricao_original, estabelecimento from lancamento") if casa(rx, r["descricao_original"], r["estabelecimento"]))


def criar_sugestao(con, tipo: str, lancamento_id: int | None, payload: dict, motivo: str) -> int:
    return con.execute("insert into sugestao(tipo, lancamento_id, payload, motivo, criado_em) values (?,?,?,?,?)",
                       (tipo, lancamento_id, json.dumps(payload, ensure_ascii=False), motivo, _agora())).lastrowid


def _em_transacao(con, fn):
    con.execute("begin")
    try:
        r = fn()
        con.execute("commit")
        return r
    except BaseException:
        con.execute("rollback")
        raise


def _pendente(con, sugestao_id: int):
    s = con.execute("select * from sugestao where id=?", (sugestao_id,)).fetchone()
    if s is None:
        raise LookupError(f"sugestão {sugestao_id} não existe")
    if s["estado"] != "pendente":
        raise ConflitoDeEstado(f"sugestão {sugestao_id} já foi {s['estado']}")
    return s


def _aprovar(con, sugestao_id: int, edicao: dict | None, por: str) -> int | None:
    s = _pendente(con, sugestao_id)
    payload = {**json.loads(s["payload"]), **(edicao or {})}
    rid = None
    if s["tipo"] == "regra":
        rx, acao = _validar(con, payload.get("padrao"), payload.get("acao"))
        rid = con.execute("insert into regra(padrao, acao, ativa, criado_em, criada_por) values (?,?,1,?,?)",
                          (payload["padrao"], json.dumps(acao, ensure_ascii=False), _agora(), por)).lastrowid
        n = _aplicar(con, rx, acao, rid)
        _decisao(con, por, f"regra {rid} criada ({payload['padrao']}) aplicada a {n} lançamento(s)")
    elif s["tipo"] in ("categoria", "para_quem", "empresa"):
        col = f"{s['tipo']}_id"
        _validar(con, "x", {col: payload.get(col)})
        l = con.execute("select * from lancamento where id=?", (s["lancamento_id"],)).fetchone()
        if l is None:
            raise LookupError("o lançamento da sugestão não existe mais")
        if l[f"{s['tipo']}_origem"] == "voce" and l[col] is not None:
            raise ValueError("esse campo já foi decidido por você")
        con.execute(f"update lancamento set {col}=?, {s['tipo']}_origem='voce' where id=?", (payload[col], l["id"]))
        _decisao(con, por, f"sugestão {sugestao_id} aprovada: {col}={payload[col]} no lançamento {l['id']}")
    else:
        _decisao(con, por, f"sugestão {sugestao_id} aprovada ({s['tipo']})")
    con.execute("update sugestao set estado='aprovada', decidida_em=?, payload=? where id=?",
                (_agora(), json.dumps(payload, ensure_ascii=False), sugestao_id))
    return rid


def aprovar(con, sugestao_id: int, edicao: dict | None, por: str) -> int | None:
    """Aprova (com edição opcional). Sugestão de regra cria a regra ATIVA e a aplica ao passado; devolve o id da regra."""
    return _em_transacao(con, lambda: _aprovar(con, sugestao_id, edicao, por))


def aprovar_lote(con, ids: list[int], por: str) -> list[int | None]:
    """Atômico: se uma falhar, nenhuma é aprovada."""
    return _em_transacao(con, lambda: [_aprovar(con, i, None, por) for i in ids])


def rejeitar(con, sugestao_id: int, por: str) -> None:
    def fazer():
        _pendente(con, sugestao_id)
        con.execute("update sugestao set estado='rejeitada', decidida_em=? where id=?", (_agora(), sugestao_id))
        _decisao(con, por, f"sugestão {sugestao_id} rejeitada")
    _em_transacao(con, fazer)


def sempre_assim(con, lancamento_id: int, por: str) -> int:
    """"Sempre assim para X": cria regra ATIVA com o que o Ricardo decidiu neste lançamento e aplica ao passado."""
    l = con.execute("select * from lancamento where id=?", (lancamento_id,)).fetchone()
    if l is None:
        raise LookupError(f"lançamento {lancamento_id} não existe")
    acao = {c: l[c] for c in CAMPOS_ACAO if l[c] is not None and l[f"{_CAMPO[c]}_origem"] == "voce"}
    if not acao:
        raise ValueError("decida primeiro categoria, para quem ou empresa neste lançamento")
    chave = l["estabelecimento"] or l["descricao_original"]
    if not chave:
        raise ValueError("lançamento sem estabelecimento nem descrição")

    def fazer():
        padrao = re.escape(chave)
        rx, ac = _validar(con, padrao, acao)
        rid = con.execute("insert into regra(padrao, acao, ativa, criado_em, criada_por) values (?,?,1,?,?)",
                          (padrao, json.dumps(ac, ensure_ascii=False), _agora(), por)).lastrowid
        n = _aplicar(con, rx, ac, rid)
        _decisao(con, por, f"regra {rid} criada (sempre assim para {chave}) aplicada a {n} lançamento(s)")
        return rid
    return _em_transacao(con, fazer)


def criar_regra_ativa(con, padrao: str, acao: dict, por: str) -> int | None:
    """Regra ATIVA direta, para quando o Ricardo a dita (chat ou arquivo de seeds). Aplica ao passado sem sobrescrever o que ele ou outra
    regra já decidiu. Mesmo padrão já cadastrado: devolve None e não duplica."""
    def fazer():
        rx, ac = _validar(con, padrao, acao)
        if con.execute("select 1 from regra where padrao=?", (padrao,)).fetchone():
            return None
        rid = con.execute("insert into regra(padrao, acao, ativa, criado_em, criada_por) values (?,?,1,?,?)",
                          (padrao, json.dumps(ac, ensure_ascii=False), _agora(), por)).lastrowid
        n = _aplicar(con, rx, ac, rid)
        _decisao(con, por, f"regra {rid} criada ({padrao}) aplicada a {n} lançamento(s)")
        return rid
    return _em_transacao(con, fazer)


def definir_ativa(con, regra_id: int, ativa: bool, por: str) -> None:
    """Liga/desliga. Ligar aplica ao passado; desligar não desfaz o que já foi feito."""
    def fazer():
        r = con.execute("select * from regra where id=?", (regra_id,)).fetchone()
        if r is None:
            raise LookupError(f"regra {regra_id} não existe")
        con.execute("update regra set ativa=? where id=?", (1 if ativa else 0, regra_id))
        if ativa:
            rx, acao = _validar(con, r["padrao"], json.loads(r["acao"]))
            _aplicar(con, rx, acao, regra_id)
        _decisao(con, por, f"regra {regra_id} {'ligada' if ativa else 'desligada'}")
    _em_transacao(con, fazer)
