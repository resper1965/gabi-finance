"""Consultas de leitura compartilhadas pela API HTTP e pelo servidor MCP (uma lógica só, dois transportes).

Erros de entrada levantam ValueError; cada transporte os traduz (HTTP 400 / MCP erro). Consome: db, dinheiro.valor.
"""
import datetime as dt

from gabi.dinheiro.valor import formatar

LIMITE_MAX = 200
CATEGORIA = "coalesce(cat.nome, l.categoria_banco, 'sem categoria')"
SQL_LANCAMENTO = ("select l.*, c.apelido as conta_nome, cat.nome as cat_nome, p.nome as pessoa_nome, e.nome as empresa_nome from lancamento l "
                  "join conta c on c.id=l.conta_id left join categoria cat on cat.id=l.categoria_id left join pessoa p on p.id=l.para_quem_id "
                  "left join empresa e on e.id=l.empresa_id")


def _m(centavos):
    return None if centavos is None else formatar(centavos)


def lancamento_dict(r) -> dict:
    d = _lancamento_base(r)
    if r["moeda"]:  # só quando a compra foi em moeda estrangeira
        d.update({"moeda": r["moeda"], "valor_original": _m(r["valor_original_centavos"]), "convertido": bool(r["convertido"])})
    return d


def _lancamento_base(r) -> dict:
    return {"id": r["id"], "data": r["data"], "estabelecimento": r["estabelecimento"], "descricao": r["descricao_original"],
            "valor": _m(r["valor_centavos"]), "forma": r["forma"], "status": r["status"], "natureza": r["natureza"], "conta": r["conta_nome"],
            "categoria": {"id": r["categoria_id"], "nome": r["cat_nome"], "origem": r["categoria_origem"]},
            "para_quem": {"id": r["para_quem_id"], "nome": r["pessoa_nome"], "origem": r["para_quem_origem"]},
            "empresa": {"id": r["empresa_id"], "nome": r["empresa_nome"], "origem": r["empresa_origem"]},
            "frente_id": r["frente_id"], "fatura_id": r["fatura_id"], "parcela": r["parcela"], "parcelas": r["parcelas"]}


def data_iso(texto: str | None, nome: str) -> dt.date | None:
    if texto is None:
        return None
    try:
        return dt.date.fromisoformat(texto)
    except ValueError:
        raise ValueError(f"{nome} deve ser AAAA-MM-DD")


def listar_lancamentos(con, *, pendente=None, de=None, ate=None, conta=None, categoria=None, para_quem=None, empresa=None, texto=None,
                       limite=50, offset=0) -> dict:
    limite, offset = min(max(limite, 1), LIMITE_MAX), max(offset, 0)
    onde, args = [], []
    if pendente:
        if pendente not in ("para_quem", "categoria", "empresa"):
            raise ValueError("pendente deve ser para_quem, categoria ou empresa")
        onde.append(f"l.{pendente}_id is null")
    for cond, valor in (("l.data>=?", data_iso(de, "de")), ("l.data<=?", data_iso(ate, "ate"))):
        if valor:
            onde.append(cond)
            args.append(valor.isoformat())
    for cond, valor in (("(c.apelido=? or c.externo_id=?)", conta), ("l.categoria_id=?", categoria), ("l.para_quem_id=?", para_quem), ("l.empresa_id=?", empresa)):
        if valor is not None:
            onde.append(cond)
            args += [valor, valor] if cond.startswith("(c.") else [valor]
    if texto:
        onde.append("(l.descricao_original like ? or l.estabelecimento like ?)")
        args += [f"%{texto}%", f"%{texto}%"]
    filtro = (" where " + " and ".join(onde)) if onde else ""
    total = con.execute(f"select count(*) from lancamento l join conta c on c.id=l.conta_id{filtro}", args).fetchone()[0]
    linhas = con.execute(f"{SQL_LANCAMENTO}{filtro} order by l.data desc, l.id desc limit ? offset ?", args + [limite, offset]).fetchall()
    return {"itens": [lancamento_dict(r) for r in linhas], "total": total, "limite": limite, "offset": offset}


def janelas(periodo: str, hoje: dt.date):
    """(ini, fim, ini_anterior, fim_anterior). mes = do dia 1 até hoje, comparado ao mesmo trecho do mês anterior."""
    if periodo == "mes":
        ini = hoje.replace(day=1)
        span = (hoje - ini).days
        ant_ini = (ini - dt.timedelta(days=1)).replace(day=1)
        return ini, hoje, ant_ini, ant_ini + dt.timedelta(days=span)
    dias = {"semana": 7, "12m": 365}[periodo]
    ini = hoje - dt.timedelta(days=dias - 1)
    ant_fim = ini - dt.timedelta(days=1)
    return ini, hoje, ant_fim - dt.timedelta(days=dias - 1), ant_fim


def custos(con, de: dt.date, ate: dt.date):
    return con.execute(
        f"select -l.valor_centavos as gasto, c.apelido as conta, {CATEGORIA} as cat, e.nome as empresa, p.nome as pessoa, "
        "coalesce(l.estabelecimento, l.descricao_original) as fornecedor from lancamento l join conta c on c.id=l.conta_id "
        "left join categoria cat on cat.id=l.categoria_id left join empresa e on e.id=l.empresa_id left join pessoa p on p.id=l.para_quem_id "
        "where l.natureza like '%custo%' and l.data>=? and l.data<=?", (de.isoformat(), ate.isoformat())).fetchall()


POR = {"categoria": "cat", "pessoa": "pessoa", "fornecedor": "fornecedor"}


def agrupar(con, periodo: str, por: str, hoje: dt.date) -> dict:
    """Para onde foi o dinheiro agrupado por categoria, pessoa ou fornecedor, com % do total e variação contra o período anterior.
    ValueError em entrada inválida (a rota e o MCP traduzem)."""
    if periodo not in ("mes", "semana", "12m"):
        raise ValueError("periodo deve ser mes, semana ou 12m")
    if por not in POR:
        raise ValueError("por deve ser categoria, pessoa ou fornecedor")
    ini, fim, a_ini, a_fim = janelas(periodo, hoje)
    chave = POR[por]

    def somar(de, ate):
        s = {}
        for r in custos(con, de, ate):
            k = r[chave] or ("(sem pessoa)" if por == "pessoa" else "(sem nome)")
            s[k] = s.get(k, 0) + r["gasto"]
        return s
    atual, antes = somar(ini, fim), somar(a_ini, a_fim)
    total = sum(atual.values())
    itens = [{"nome": k, "valor": formatar(v), "pct": round(v / total * 100, 1) if total else 0.0, "variacao": formatar(v - antes.get(k, 0))}
             for k, v in sorted(atual.items(), key=lambda kv: (-kv[1], kv[0])) if v]
    return {"periodo": {"de": ini.isoformat(), "ate": fim.isoformat()}, "por": por, "itens": itens, "total": formatar(total)}
