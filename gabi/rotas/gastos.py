"""Rotas /api/v1 de análise de gastos: semanas, destino (para onde vai), cartões, parcelas, assinaturas e custo do modelo.

Somas em centavos inteiros; texto só na borda (R7). Consome: dinheiro.{analise,repositorio,contas_pagar,modelo}, envelope.
"""
import datetime as dt
import json
import re

from fastapi import APIRouter, Depends, Request

from gabi.dinheiro import analise, assinaturas as assinaturas_mod, consultas, contas_pagar as cp, repositorio
from gabi.dinheiro.modelo import orcamento_do_banco
from gabi.dinheiro.valor import formatar, para_centavos
from gabi.envelope import envelope
from gabi.identidade import exigir
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, _m, erro

router = APIRouter(prefix="/api/v1", dependencies=[Depends(exigir("boss"))])
SEM_CATEGORIA = "sem categoria"
CATEGORIA = "coalesce(cat.nome, l.categoria_banco, 'sem categoria')"
STATUS_ASSINATURA = ("a_conferir", "manter", "cancelar", "nao_assinatura", "encerrada")
FORA_DO_ROL = ("nao_assinatura", "encerrada")  # o Ricardo disse que não é (ou acabou): sai da lista padrão, do total e dos alertas


def _lista(por_categoria: dict, sinal: int) -> list[dict]:
    """[{categoria, valor}] dos maiores para os menores; `sinal` -1 mostra saídas como negativas."""
    itens = sorted(((k, v) for k, v in por_categoria.items() if v), key=lambda kv: (-abs(kv[1]), kv[0]))
    return [{"categoria": k, "valor": formatar(sinal * v)} for k, v in itens]


def _contas_liberadas(con) -> list[int]:
    return [r[0] for r in con.execute("select id from conta where estado='sim' and tipo='BANK' and excluido_em is null")]


def _saldo_ate(con, ids: list[int], dia: dt.date):
    total, algum = 0, False
    for cid in ids:
        s = con.execute("select saldo_centavos from saldo where conta_id=? and em<=? order by em desc limit 1", (cid, f"{dia.isoformat()}T23:59:59")).fetchone()
        if s:
            total, algum = total + s[0], True
    return total if algum else None


# ---------------- semanas ----------------
@router.get("/caixa/semanas")
def semanas(request: Request, passadas: int = 8, futuras: int = 4):
    """Semanas (passado real e projeção): entradas e saídas por categoria e saldo."""
    passadas, futuras = min(max(passadas, 0), 52), min(max(futuras, 0), 12)
    con = _con(request)
    try:
        hoje = _agora(request).date()
        seg = hoje - dt.timedelta(days=hoje.weekday())
        ini0 = seg - dt.timedelta(days=7 * passadas)
        total = passadas + 1 + futuras
        ids = _contas_liberadas(con)
        cx = cp.caixa_unico(con, hoje)
        prev = analise.previsao(repositorio.FonteAnalise(con), (ini0 + dt.timedelta(days=7 * total - 1) - hoje).days, None, hoje)
        delta = cx.saldo_centavos - para_centavos(prev["saldo_inicial"])
        eventos = [(dt.date.fromisoformat(e["data"]), e["tipo"], para_centavos(e["valor"]), para_centavos(e["saldo"]) + delta) for e in prev["eventos"]]
        saida, ultimo_saldo = [], None
        for i in range(total):
            ini = ini0 + dt.timedelta(days=7 * i)
            fim = ini + dt.timedelta(days=6)
            futura = ini > hoje
            entradas, saidas = {}, {}
            if not futura:
                marcas = ",".join("?" * len(ids)) or "NULL"
                for r in con.execute(f"select l.valor_centavos, {CATEGORIA} as cat from lancamento l left join categoria cat on cat.id=l.categoria_id "
                                     f"where l.conta_id in ({marcas}) and l.natureza like '%caixa%' and l.data>=? and l.data<=?",
                                     [*ids, ini.isoformat(), min(fim, hoje).isoformat()]):
                    alvo = entradas if r[0] > 0 else saidas
                    alvo[r["cat"]] = alvo.get(r["cat"], 0) + r[0]
                saldo = _saldo_ate(con, ids, min(fim, hoje))
            else:
                saldo = None
                for d, tipo, valor, acumulado in eventos:
                    if ini <= d <= fim:
                        alvo = entradas if valor > 0 else saidas
                        alvo[tipo] = alvo.get(tipo, 0) + valor
                    if d <= fim:
                        saldo = acumulado
                if saldo is None:
                    saldo = ultimo_saldo if ultimo_saldo is not None else cx.saldo_centavos
            ultimo_saldo = saldo if saldo is not None else ultimo_saldo
            saida.append({"inicio": ini.isoformat(), "fim": fim.isoformat(), "entradas": _lista(entradas, 1), "saidas": _lista(saidas, 1),
                          "saldo": _m(saldo), "projecao": futura})
        return envelope(con, {"semanas": saida}, agora=_agora(request))
    finally:
        con.close()


# ---------------- para onde vai ----------------
@router.get("/destino")
def destino(request: Request, periodo: str = "mes"):
    """Para onde vai o dinheiro: origem, categoria e destino, com comparação ao período anterior."""
    if periodo not in ("mes", "semana", "12m"):
        raise erro(400, "requisicao_invalida", "periodo deve ser mes, semana ou 12m")
    con = _con(request)
    try:
        hoje = _agora(request).date()
        ini, fim, a_ini, a_fim = consultas.janelas(periodo, hoje)
        origem_cat, cat_destino, por_cat, total = {}, {}, {}, 0
        for r in consultas.custos(con, ini, fim):
            dest = f"A receber: {r['empresa']}" if r["empresa"] else "Consumo pessoal"
            origem_cat[(r["conta"], r["cat"])] = origem_cat.get((r["conta"], r["cat"]), 0) + r["gasto"]
            cat_destino[(r["cat"], dest)] = cat_destino.get((r["cat"], dest), 0) + r["gasto"]
            por_cat[r["cat"]] = por_cat.get(r["cat"], 0) + r["gasto"]
            total += r["gasto"]
        anterior = {}
        for r in consultas.custos(con, a_ini, a_fim):
            anterior[r["cat"]] = anterior.get(r["cat"], 0) + r["gasto"]
        fluxos = [{"de": a, "para": b, "valor": formatar(v)} for (a, b), v in sorted({**origem_cat, **cat_destino}.items(), key=lambda kv: (-kv[1], kv[0])) if v]
        nos, vistos = [], set()
        for (conta, cat) in origem_cat:
            for nome, tipo in ((conta, "origem"), (cat, "categoria")):
                if (nome, tipo) not in vistos:
                    vistos.add((nome, tipo))
                    nos.append({"nome": nome, "tipo": tipo})
        for (_, dest) in cat_destino:
            if (dest, "destino") not in vistos:
                vistos.add((dest, "destino"))
                nos.append({"nome": dest, "tipo": "destino"})
        cats = sorted(set(por_cat) | set(anterior), key=lambda c: (-abs(por_cat.get(c, 0) - anterior.get(c, 0)), c))
        comparacao = [{"categoria": c, "atual": formatar(por_cat.get(c, 0)), "anterior": formatar(anterior.get(c, 0)),
                       "variacao": formatar(por_cat.get(c, 0) - anterior.get(c, 0))} for c in cats]
        return envelope(con, {"periodo": {"de": ini.isoformat(), "ate": fim.isoformat(), "anterior_de": a_ini.isoformat(), "anterior_ate": a_fim.isoformat()},
                              "nos": nos, "fluxos": fluxos, "total": formatar(total), "comparacao": comparacao}, agora=_agora(request))
    finally:
        con.close()


@router.get("/destino/agrupado")
def destino_agrupado(request: Request, periodo: str = "mes", por: str = "categoria"):
    """Para onde vai o dinheiro agrupado por categoria, pessoa (para quem), gastador (quem gastou) ou fornecedor (abas Fornecedores e Por pessoa)."""
    con = _con(request)
    try:
        try:
            dados = consultas.agrupar(con, periodo, por, _agora(request).date())
        except ValueError as e:
            raise erro(400, "requisicao_invalida", str(e))
        return envelope(con, dados, agora=_agora(request))
    finally:
        con.close()


# ---------------- cartões ----------------
def _meses(hoje: dt.date, n: int) -> list[str]:
    saida, a, m = [], hoje.year, hoje.month
    for _ in range(n):
        saida.append(f"{a}-{m:02d}")
        m -= 1
        if m == 0:
            a, m = a - 1, 12
    return saida[::-1]


@router.get("/cartoes")
def cartoes(request: Request):
    """Cartões: fatura aberta, % do limite, série de 12 meses e categorias."""
    con = _con(request)
    try:
        hoje = _agora(request).date()
        itens = []
        abertas = {}  # mesma regra do Caixa: fatura com débito no banco não é aberta, mesmo se o banco ainda diz UNCONFIRMED
        for a in cp.faturas_abertas(con, hoje):
            abertas[a["conta_id"]] = a["id"]  # ordenadas por vencimento: a última de cada cartão vence por último
        for c in con.execute("select * from conta where tipo='CREDIT' and estado='sim' and excluido_em is null order by id"):
            f = con.execute("select * from fatura where id=?", (abertas[c["id"]],)).fetchone() if c["id"] in abertas else None
            fatura = None
            if f:
                pct = round(f["total_centavos"] / c["limite_centavos"] * 100, 1) if c["limite_centavos"] and f["total_centavos"] is not None else None
                fatura = {"id": f["id"], "vencimento": f["vencimento"], "total": _m(f["total_centavos"]), "status": f["pagamento_status"], "percentual_limite": pct}
            meses = {r[0]: r[1] for r in con.execute("select substr(data,1,7), sum(-valor_centavos) from lancamento where conta_id=? and natureza like '%custo%' group by 1", (c["id"],))}
            cats = {}
            if f:
                for r in con.execute(f"select {CATEGORIA} as cat, sum(-l.valor_centavos) from lancamento l left join categoria cat on cat.id=l.categoria_id "
                                     "where l.conta_id=? and l.fatura_id=? group by 1", (c["id"], f["id"])):
                    cats[r[0]] = r[1]
            itens.append({"id": c["id"], "apelido": c["apelido"] or c["externo_id"], "limite": _m(c["limite_centavos"]), "fatura_aberta": fatura,
                          "serie_12m": [{"mes": m, "total": formatar(meses.get(m, 0))} for m in _meses(hoje, 12)],
                          "por_categoria": _lista(cats, 1)})
        return envelope(con, {"itens": itens}, agora=_agora(request))
    finally:
        con.close()


# ---------------- parcelas ----------------
def _soma_meses(mes: str, n: int) -> str:
    a, m = int(mes[:4]), int(mes[5:7])
    t = a * 12 + (m - 1) + n
    return f"{t // 12}-{t % 12 + 1:02d}"


@router.get("/parcelas")
def parcelas(request: Request):
    """Parcelas: comprometido por mês e andamento de cada compra parcelada."""
    con = _con(request)
    try:
        hoje = _agora(request).date()
        atual = hoje.strftime("%Y-%m")
        ultimas = {}
        for r in con.execute("select l.*, c.apelido from lancamento l join conta c on c.id=l.conta_id where c.tipo='CREDIT' and l.parcelas>1 order by l.data, l.id"):
            k = (r["conta_id"], r["descricao_original"], r["parcelas"], r["valor_centavos"])
            if k not in ultimas or r["parcela"] >= ultimas[k]["parcela"]:
                ultimas[k] = r
        itens, por_mes = [], {}
        for r in ultimas.values():
            restante, base, valor = r["parcelas"] - r["parcela"], r["data"][:7], -r["valor_centavos"]
            fim = _soma_meses(base, restante)
            itens.append({"descricao": r["descricao_original"], "conta": r["apelido"], "parcela": r["parcela"], "parcelas": r["parcelas"], "restante": restante,
                          "valor_parcela": formatar(valor), "termina_em": fim, "termina_neste_mes": fim == atual})
            for k in range(1, restante + 1):
                m = _soma_meses(base, k)
                if m > atual:
                    por_mes[m] = por_mes.get(m, 0) + valor
        itens.sort(key=lambda i: (i["termina_em"], i["descricao"]))
        return envelope(con, {"itens": itens, "por_mes": [{"mes": m, "total": formatar(v)} for m, v in sorted(por_mes.items())]}, agora=_agora(request))
    finally:
        con.close()


# ---------------- assinaturas ----------------
def _assinatura(con, chave: str, nome: str, r: dict, hoje: dt.date) -> dict:
    con.execute("insert or ignore into assinatura(estabelecimento) values (?)", (chave,))
    a = con.execute("select * from assinatura where estabelecimento=?", (chave,)).fetchone()
    cobrada = False
    if a["status"] == "cancelar" and a["status_em"]:
        cobrada = con.execute("select 1 from lancamento where natureza like '%custo%' and data>? and (estabelecimento=? or descricao_original like ?) limit 1",
                              (a["status_em"][:10], chave, f"{chave}%")).fetchone() is not None
    ini12 = _soma_meses(hoje.strftime("%Y-%m"), -11) + "-01"
    deb = con.execute("select data, valor_centavos from lancamento where natureza like '%custo%' and (estabelecimento=? or descricao_original like ?) and data>=? order by data",
                      (chave, f"{chave}%", ini12)).fetchall()
    por_mes = {}
    for d in deb:
        por_mes[d["data"][:7]] = por_mes.get(d["data"][:7], 0) - d["valor_centavos"]
    serie = [{"mes": m, "total": formatar(por_mes.get(m, 0))} for m in _meses(hoje, 12)]
    reaj = None
    if r["mediana_anterior"] and r["ultimo"] > r["mediana_anterior"] * 1.10:
        reaj = {"antes": formatar(para_centavos(r["mediana_anterior"])), "agora": formatar(para_centavos(r["ultimo"]))}
    return {"id": a["id"], "nome": nome, "mensal": formatar(para_centavos(r["valor_medio"])), "anual": formatar(para_centavos(round(r["valor_medio"] * 12, 2))),
            "meses_vistos": r["meses"], "status": a["status"], "no_rol": a["status"] not in FORA_DO_ROL, "lembrar_ate_cancelar": bool(a["lembrar_ate_cancelar"]),
            "serie_12m": serie, "desde": deb[0]["data"] if deb else None, "ultimo": deb[-1]["data"] if deb else None, "total_12m": formatar(sum(por_mes.values())),
            "sinais": {"nova": r["meses"] == 3, "reajustou": reaj, "cobrada_depois_de_cancelar": cobrada}}


def calcular_assinaturas(con, hoje: dt.date) -> dict:
    """O rol de assinaturas (a mesma conta da tela, do Resumo e do contador): itens com status e sinais, total mensal só do que está no rol."""
    recs = [r for r in analise.recorrentes(repositorio.FonteAnalise(con), "custo", hoje) if r["sentido"] == "saida" and r["valor_medio"] < 600]
    # Além do detector: lojas das categorias de assinatura (parâmetro editável) com cobrança em 2+ meses; as que pararam vêm como inativas.
    p = con.execute("select valor from parametro where chave='categorias_assinatura'").fetchone()
    nomes = json.loads(p["valor"]) if p else []
    h = con.execute("select valor from parametro where chave='categorias_habito'").fetchone()
    habito = json.loads(h["valor"]) if h else []
    recs = [r for r in recs if not assinaturas_mod.eh_habito(con, r["chave"], habito)]   # almoço, mercado... repetem todo mês mas não são assinatura
    extras = assinaturas_mod.candidatas_por_categoria(con, hoje, nomes, {r["chave"] for r in recs})
    todas = [{**r, "ativa": True} for r in recs] + extras
    con.execute("begin")
    try:
        itens = [{**_assinatura(con, r["chave"], r["descricao"], r, hoje), "ativa": r["ativa"]} for r in todas]
        con.execute("commit")
    except BaseException:
        con.execute("rollback")
        raise
    itens.sort(key=lambda i: (not i["ativa"], -float(i["anual"])))
    total = sum(para_centavos(i["mensal"]) for i in itens if i["ativa"] and i["no_rol"])
    return {"itens": itens, "total_mensal_centavos": total,
            "alerta_forte": any(i["sinais"]["cobrada_depois_de_cancelar"] for i in itens if i["no_rol"])}


@router.get("/assinaturas")
def assinaturas(request: Request):
    """Assinaturas detectadas, com os sinais: nova, reajustou, cobrada depois de cancelar."""
    con = _con(request)
    try:
        r = calcular_assinaturas(con, _agora(request).date())
        return envelope(con, {"itens": r["itens"], "total_mensal": formatar(r["total_mensal_centavos"]), "alerta_forte": r["alerta_forte"]},
                        agora=_agora(request))
    finally:
        con.close()


@router.patch("/assinaturas/{aid}")
async def assinatura_patch(aid: int, request: Request):
    """Muda o status da assinatura e o lembrete até cancelar."""
    corpo = _corpo(await _json(request))
    if not corpo or set(corpo) - {"status", "lembrar_ate_cancelar"}:
        raise erro(400, "requisicao_invalida", "informe status e/ou lembrar_ate_cancelar")
    if "status" in corpo and corpo["status"] not in STATUS_ASSINATURA:
        raise erro(400, "requisicao_invalida", f"status deve ser um de {list(STATUS_ASSINATURA)}")
    if "lembrar_ate_cancelar" in corpo and not isinstance(corpo["lembrar_ate_cancelar"], bool):
        raise erro(400, "requisicao_invalida", "lembrar_ate_cancelar deve ser true ou false")
    con = _con(request)
    try:
        a = con.execute("select * from assinatura where id=?", (aid,)).fetchone()
        if a is None:
            raise erro(404, "nao_encontrado", f"assinatura {aid} não existe")
        status = corpo.get("status", a["status"])
        status_em = _agora(request).date().isoformat() if status == "cancelar" and a["status"] != "cancelar" else (a["status_em"] if status == "cancelar" else None)
        con.execute("update assinatura set status=?, status_em=?, lembrar_ate_cancelar=? where id=?",
                    (status, status_em, int(corpo.get("lembrar_ate_cancelar", bool(a["lembrar_ate_cancelar"]))), aid))
        return envelope(con, {"id": aid, "nome": a["estabelecimento"], "status": status, "lembrar_ate_cancelar": bool(corpo.get("lembrar_ate_cancelar", a["lembrar_ate_cancelar"]))},
                        agora=_agora(request))
    finally:
        con.close()


# ---------------- custo do modelo ----------------
@router.get("/custo")
def custo(request: Request):
    """Custo do modelo (OpenRouter) no dia e no mês contra o teto."""
    con = _con(request)
    try:
        hoje = _agora(request).date()
        orc = orcamento_do_banco(con, hoje)
        dia, mes, td, tm = orc.gasto_dia_usd, orc.gasto_mes_usd, orc.teto_dia_usd, orc.teto_mes_usd
        cambio = con.execute("select valor from parametro where chave='cambio_usd_brl'").fetchone()  # editável; nunca fixo no código (R6)
        cambio = f"{float(__import__('json').loads(cambio['valor'])):.2f}" if cambio else None
        return envelope(con, {"dia_usd": round(dia, 4), "mes_usd": round(mes, 4), "teto_dia_usd": td, "teto_mes_usd": tm, "alerta": orc.alerta(),
                              "cambio_usd_brl": cambio}, agora=_agora(request))
    finally:
        con.close()


@router.get("/rumo")
def rumo(request: Request, ano: int | None = None):
    """Rumo do ano, mês a mês: entradas, saídas, poupança, gasto (por pessoa e por frente) e patrimônio das contas liberadas."""
    from gabi.dinheiro.rumo import rumo_mensal
    hoje = _agora(request).date()
    ano = ano or hoje.year
    if not 2000 <= ano <= 2100:
        raise erro(400, "requisicao_invalida", "ano deve estar entre 2000 e 2100")
    con = _con(request)
    try:
        meses = [{"mes": l.mes, "entradas": _m(l.entradas), "saidas": _m(l.saidas), "poupanca": _m(l.poupanca), "gasto": _m(l.gasto),
                  "patrimonio": _m(l.patrimonio), "por_pessoa": {k: _m(v) for k, v in l.por_pessoa.items()}, "por_frente": {k: _m(v) for k, v in l.por_frente.items()}}
                 for l in rumo_mensal(con, ano)]
        return envelope(con, {"ano": ano, "meses": meses}, agora=_agora(request))
    finally:
        con.close()
