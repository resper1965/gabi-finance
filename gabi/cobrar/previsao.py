"""Previsão de caixa (entradas) a partir das NFS-e importadas do Nibo. Consome: db (nota_fiscal).

Três blocos, sempre separados para ninguém confundir previsão com fato:
- `a_vencer`: notas autorizadas, não baixadas no Nibo, com vencimento no mês (valor líquido, depois das retenções, e bruto).
- `projetado`: contrato recorrente (nota autorizada em cada um dos 3 meses completos anteriores) ainda sem nota no mês;
  vale o ÚLTIMO valor e o mesmo dia do vencimento (nunca mediana, preferência do Ricardo).
- `a_confirmar` / `antigas`: vencidas e não baixadas. O Nibo está defasado (a maioria já foi paga e não teve baixa): isto é
  fila de conferência com o extrato, NÃO entra na previsão. Recebimento real = crédito no extrato (casamento por valor, futuro).
"""
import calendar
import datetime as dt

RECENTE_DIAS = 60


def _mes(d: dt.date) -> str:
    return d.strftime("%Y-%m")


def _soma_mes(d: dt.date, n: int) -> dt.date:
    m = d.month - 1 + n
    return dt.date(d.year + m // 12, m % 12 + 1, 1)


def _dia(d: dt.date, dia: int) -> dt.date:
    return d.replace(day=min(dia, calendar.monthrange(d.year, d.month)[1]))


def _nota(l) -> dict:
    return {"numero": l["numero"], "tomador": l["tomador_nome"], "vencimento": l["vencimento"],
            "liquido_centavos": l["valor_liquido_centavos"], "bruto_centavos": l["valor_bruto_centavos"]}


def _bloco(notas: list[dict]) -> dict:
    return {"qtd": len(notas), "liquido_centavos": sum(n["liquido_centavos"] or 0 for n in notas),
            "bruto_centavos": sum(n["bruto_centavos"] or 0 for n in notas), "notas": notas}


def previsao(con, hoje: dt.date, meses: int = 3, projetar: bool = True) -> dict:
    abertas = [l for l in con.execute(
        "select * from nota_fiscal where status='autorizada' and nibo_pago=0 and vencimento is not null order by vencimento, numero")]
    inicio = hoje.replace(day=1)
    alvos = [_soma_mes(inicio, k) for k in range(meses)]
    por_mes = {_mes(a): {"mes": _mes(a), "a_vencer": [], "projetado": []} for a in alvos}
    vencidas = []
    for l in abertas:
        v = dt.date.fromisoformat(l["vencimento"])
        if v < hoje:
            vencidas.append((v, _nota(l)))
        elif _mes(v) in por_mes:
            por_mes[_mes(v)]["a_vencer"].append(_nota(l))
    recentes = [n for v, n in vencidas if (hoje - v).days <= RECENTE_DIAS]
    antigas = [n for v, n in vencidas if (hoje - v).days > RECENTE_DIAS]
    if projetar:
        _projetar(con, hoje, alvos, por_mes)
    return {"hoje": hoje.isoformat(), "aviso": "Nibo defasado: vencida e não baixada não é prova de que não foi paga; confirmar pelo extrato.",
            "meses": [{"mes": m["mes"], "a_vencer": _bloco(m["a_vencer"]), "projetado": _bloco(m["projetado"])} for m in por_mes.values()],
            "a_confirmar": _bloco(recentes), "antigas": _bloco(antigas)}


def _projetar(con, hoje, alvos, por_mes):
    anteriores = [_mes(_soma_mes(hoje.replace(day=1), -k)) for k in (1, 2, 3)]
    todas = con.execute("select * from nota_fiscal where status='autorizada' and vencimento is not null and tomador_doc is not null").fetchall()
    por_tomador: dict[str, dict[str, list]] = {}
    for l in todas:
        por_tomador.setdefault(l["tomador_doc"], {}).setdefault(l["vencimento"][:7], []).append(l)
    for doc, meses in por_tomador.items():
        if not all(m in meses for m in anteriores):
            continue  # não é recorrente: faltou nota em algum dos 3 meses completos anteriores
        ultimo = meses[anteriores[0]]
        liquido = sum(l["valor_liquido_centavos"] or 0 for l in ultimo)
        bruto = sum(l["valor_bruto_centavos"] or 0 for l in ultimo)
        dia = max(dt.date.fromisoformat(l["vencimento"]).day for l in ultimo)
        for alvo in alvos:
            if _mes(alvo) in meses:
                continue  # o mês já tem nota emitida
            venc = _dia(alvo, dia)
            por_mes[_mes(alvo)]["projetado"].append({
                "numero": None, "tomador": ultimo[0]["tomador_nome"], "vencimento": venc.isoformat(),
                "liquido_centavos": liquido, "bruto_centavos": bruto})
    for m in por_mes.values():
        m["projetado"].sort(key=lambda n: (n["vencimento"], n["tomador"] or ""))
