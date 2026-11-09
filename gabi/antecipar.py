"""Olhar à frente (ADR-037): o que vai virar problema nos próximos dias, só de tabelas locais (sem rede, sem modelo, sem gravar).
Caixa projetado que fica negativo, a receber atrasado há 10 dias ou mais, documentos que vencem em 30 dias e atividades que vencem em 7.
Consome: dinheiro.projecao, cobrar.a_receber, documentos.repositorio, atividades. O resumo da manhã só ganha o bloco quando há alerta."""
import datetime as dt
from zoneinfo import ZoneInfo

from gabi import atividades
from gabi.cobrar.a_receber import a_receber_do_mes
from gabi.dinheiro.projecao import projetar
from gabi.documentos import repositorio

BRT = ZoneInfo("America/Sao_Paulo")
ATRASO_MINIMO_DIAS = 10
DOCUMENTO_DIAS = 30
ATIVIDADE_DIAS = 7


def _caixa(con, hoje: dt.date, dias: int) -> dict | None:
    serie = projetar(con, hoje, dias)
    negativos = [d for d in serie if d["saldo_centavos"] < 0]
    if not negativos:
        return None
    minimo = min(serie, key=lambda d: d["saldo_centavos"])
    return {"primeiro_dia_negativo": negativos[0]["dia"], "saldo_minimo_centavos": minimo["saldo_centavos"], "dia_do_minimo": minimo["dia"]}


def _atrasados(con, hoje: dt.date) -> list[dict]:
    r = a_receber_do_mes(con, hoje)
    saida = []
    for i in r["recorrentes"]:
        if i["situacao"] == "atrasado" and (i["dias_atraso"] or 0) >= ATRASO_MINIMO_DIAS:
            saida.append({"pagador": i["pagador"], "valor_centavos": i["esperado_centavos"], "dias_atraso": i["dias_atraso"], "origem": "recorrente"})
    for n in r["notas"]:
        if n["situacao"] == "atrasado":
            dias = (hoje - dt.date.fromisoformat(n["vencimento"])).days
            if dias >= ATRASO_MINIMO_DIAS:
                saida.append({"pagador": n["pagador"], "valor_centavos": n["esperado_centavos"], "dias_atraso": dias, "origem": f"nota {n['numero']}"})
    return sorted(saida, key=lambda i: -i["dias_atraso"])


def _documentos(con, hoje: dt.date) -> list[dict]:
    limite = (hoje + dt.timedelta(days=DOCUMENTO_DIAS)).isoformat()
    return [d for d in repositorio.vencimentos(con, hoje, 2) if d["data"] <= limite]


def _atividades(con, agora: dt.datetime, hoje: dt.date) -> list[dict]:
    limite = hoje + dt.timedelta(days=ATIVIDADE_DIAS)
    saida = []
    for a in atividades.listar(con, agora, "aberta"):
        if a["vence_em"] and a["vence_em"][:10] <= limite.isoformat():
            saida.append({"id": a["id"], "texto": a["texto"], "vence_em": a["vence_em"], "prazo": a["prazo"]})
    return saida


def olhar_a_frente(con, agora: dt.datetime, dias: int = 30) -> dict:
    hoje = agora.astimezone(BRT).date()
    caixa, atrasados, docs, ativs = _caixa(con, hoje, dias), _atrasados(con, hoje), _documentos(con, hoje), _atividades(con, agora, hoje)
    return {"dias": dias, "caixa": caixa, "a_receber_atrasado": atrasados, "documentos": docs, "atividades_vencendo": ativs,
            "ha_alerta": bool(caixa or atrasados or docs)}  # atividade fica de fora: o resumo das 07:00 de atividades já a cobre


def _brl(centavos: int) -> str:
    sinal, c = ("-" if centavos < 0 else ""), abs(centavos)
    return f"{sinal}R$ {c // 100:,}".replace(",", ".") + f",{c % 100:02d}"


def _dm(iso: str) -> str:
    return dt.date.fromisoformat(iso[:10]).strftime("%d/%m")


def bloco_resumo(con, agora: dt.datetime) -> list[str]:
    r = olhar_a_frente(con, agora)
    if not r["ha_alerta"]:
        return []
    linhas = ["👀 *Olhando à frente*"]
    if r["caixa"]:
        c = r["caixa"]
        linhas.append(f"• Caixa fica negativo em {_dm(c['primeiro_dia_negativo'])}; pior ponto {_brl(c['saldo_minimo_centavos'])} em {_dm(c['dia_do_minimo'])}.")
    for i in r["a_receber_atrasado"][:3]:
        linhas.append(f"• {i['pagador']} está {i['dias_atraso']} dias atrasado ({_brl(i['valor_centavos'])}).")
    for d in r["documentos"][:3]:
        linhas.append(f"• {d['titular_nome']}: {d['tipo']} {'venceu' if d['vencido'] else 'vence'} em {_dm(d['data'])}.")
    return linhas
