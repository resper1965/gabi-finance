"""Lista "reembolsos a pedir e a conferir" (a de segunda 08h do gabi-fin), SEM modelo e SEM nomes (ADR-014): lê só a projeção do `gabi.db`
(número do dossiê, mês, códigos do que falta). Texto curto, pronto para o celular. Consome: reembolso_saude_dossie, requisitos, avisos."""
import datetime as dt
import json
from zoneinfo import ZoneInfo

from gabi.avisos import _novo
from gabi.reembolso_saude import requisitos

BRT = ZoneInfo("America/Sao_Paulo")
SEM_REEMBOLSO = "Nenhum reembolso de saúde a pedir nem a conferir."
RODAPE = "Quem é cada dossiê: painel (Família) ou Paperless."
HORA_SEMANAL = 8


def _mes(m: str) -> str:
    return f"{m[5:7]}/{m[:4]}"


def _parado(r, hoje: dt.date) -> int:
    return max((hoje - dt.date.fromisoformat(r["parado_desde"])).days, 0) if r["parado_desde"] else 0


def montar_segunda(con, hoje: dt.date) -> list[str]:
    """Linhas da lista: dossiês a pedir (pronto ou o que falta, e há quantos dias parado) e os a conferir (ids dos documentos). Nada a listar: uma frase."""
    req = requisitos.carregar(con)
    a_pedir = list(con.execute("select * from reembolso_saude_dossie where estado='a_pedir' order by id"))
    conferir = list(con.execute("select * from reembolso_saude_dossie where estado='a_conferir' order by id"))
    if not a_pedir and not conferir:
        return [SEM_REEMBOLSO]
    linhas = [f"🩺 Reembolsos de saúde: segunda {hoje:%d/%m}"]
    for r in a_pedir:
        st = "pronto para pedir" if r["pronto"] else "falta " + ", ".join(requisitos.rotulo(req, i) for i in json.loads(r["faltam"]))
        linhas.append(f"• Dossiê {r['id']} ({_mes(r['mes'])}): {st} · parado há {_parado(r, hoje)} dias")
    if conferir:
        linhas.append("A conferir:")
        for r in conferir:
            ids = json.loads(r["doc_ids"])
            linhas.append(f"• Dossiê {r['id']} ({_mes(r['mes'])}): documento{'s' if len(ids) > 1 else ''} {', '.join(map(str, ids))}")
    linhas.append(RODAPE)
    return linhas


def avisar_semana(con, agora: dt.datetime) -> int | None:
    """Na segunda a partir das 08h (Brasília) grava UM aviso com a lista (o Telegram do brain entrega). Sem reembolso a listar: nada. Id do aviso ou None."""
    local = agora.astimezone(BRT)
    if local.weekday() != 0 or local.hour < HORA_SEMANAL:
        return None
    linhas = montar_segunda(con, local.date())
    if linhas == [SEM_REEMBOLSO]:
        return None
    return _novo(con, agora, "reembolso_saude_semana", local.date().isoformat(), {"linhas": linhas})
