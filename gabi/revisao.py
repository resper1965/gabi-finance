"""Revisão da semana (ADR-037): o que andou e o que parou nos últimos 7 dias, só de tabelas locais, sem gravar.
Atividades concluídas, vencidas e sem data há mais de 14 dias; projetos parados; decisões abertas há mais de 7 dias; variação do caixa
(hoje contra 7 dias atrás, pelos saldos dos extratos) e documentos que vencem. Descartar é pedido do Ricardo (atividade_cancelar), nunca daqui.
Consome: atividades, projetos, decisoes, dinheiro.contas_pagar, antecipar."""
import datetime as dt
from zoneinfo import ZoneInfo

from gabi import antecipar, atividades, decisoes, projetos
from gabi.dinheiro import contas_pagar

BRT = ZoneInfo("America/Sao_Paulo")
SEMANA = dt.timedelta(days=7)
SEM_DATA_ANTIGA = dt.timedelta(days=14)


def _antes(iso: str | None, limite: dt.datetime) -> bool:
    return bool(iso) and dt.datetime.fromisoformat(iso) < limite


def _atividades(con, agora: dt.datetime) -> dict:
    concluidas, vencidas, antigas = [], [], []
    for a in atividades.listar(con, agora, "feita"):
        if a.get("concluida_em") and not _antes(a["concluida_em"], agora - SEMANA):
            concluidas.append({"id": a["id"], "texto": a["texto"]})
    for a in atividades.listar(con, agora, "aberta"):
        if a["prazo"] == "vencida":
            vencidas.append({"id": a["id"], "texto": a["texto"], "vence_em": a["vence_em"]})
        elif a["prazo"] == "sem_data":
            criada = con.execute("select criada_em from atividade where id=?", (a["id"],)).fetchone()["criada_em"]
            if _antes(criada, agora - SEM_DATA_ANTIGA):
                antigas.append({"id": a["id"], "texto": a["texto"], "criada_em": criada})
    return {"concluidas": concluidas, "vencidas": vencidas, "sem_data_antigas": antigas}


def _caixa(con, hoje: dt.date) -> dict:
    agora_, antes = contas_pagar.caixa_unico(con, hoje).saldo_centavos, contas_pagar.caixa_unico(con, hoje - SEMANA).saldo_centavos
    return {"hoje_centavos": agora_, "ha_7_dias_centavos": antes, "variacao_centavos": agora_ - antes}


def revisao_semana(con, agora: dt.datetime) -> dict:
    hoje = agora.astimezone(BRT).date()
    antigas = [{"id": d["id"], "titulo": d["titulo"], "criada_em": d["criada_em"]} for d in decisoes.abertas(con) if _antes(d["criada_em"], agora - SEMANA)]
    return {"atividades": _atividades(con, agora),
            "projetos_parados": [{"id": p["id"], "nome": p["nome"], "parado_ha_dias": p["parado_ha_dias"]} for p in projetos.parados(con, agora)],
            "decisoes_antigas": antigas, "caixa": _caixa(con, hoje), "documentos": antecipar._documentos(con, hoje)}
