"""Convites de agenda recebidos: pendentes e conflito calculados na leitura (spec 2026-11-04-convites-agenda). Regras puras, sem rede.
Nunca expõe e-mail de participante: só título, organizador (nome) e horários."""
import datetime as dt

from gabi.agenda import tempo
from gabi.agenda.tempo import Janela
from gabi.envios.propostas import contas_agenda

_DIAS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
_RESPOSTAS_QUE_OCUPAM = ("accepted", "needsAction")


def _iso(d: dt.datetime) -> str:
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _janela(r) -> Janela:
    return Janela(r["inicio_utc"], r["fim_utc"], r["dia_local"], r["dia_fim_local"], False)


def pendentes(con, agora: dt.datetime) -> list[dict]:
    contas = contas_agenda(con)
    if not contas:
        return []
    marcas = ",".join("?" * len(contas))
    base = ("select e.id, e.inicio_utc, e.fim_utc, e.dia_local, e.dia_fim_local, e.titulo, e.resposta, e.livre, e.organizador_nome, e.serie_id, f.conta "
            "from agenda_evento e join agenda_fonte f on f.id=e.fonte_id where f.estado='sim' and e.dia_inteiro=0 ")
    convites = con.execute(base + f"and e.resposta='needsAction' and e.inicio_utc>? and lower(f.conta) in ({marcas}) order by e.inicio_utc, e.id",
                           (_iso(agora), *contas)).fetchall()
    if not convites:
        return []
    ocupam = [r for r in con.execute(base + "and e.livre=0 and (e.resposta is null or e.resposta in (?,?)) order by e.inicio_utc, e.id", _RESPOSTAS_QUE_OCUPAM)]
    saida = []
    for c in convites:
        jc = _janela(c)
        conflitos = [o["titulo"] or "(sem título)" for o in ocupam if o["id"] != c["id"] and tempo.se_sobrepoem(jc, _janela(o))]
        saida.append({"evento_id": c["id"], "conta": c["conta"], "titulo": c["titulo"] or "(sem título)", "inicio_utc": c["inicio_utc"],
                      "fim_utc": c["fim_utc"], "organizador_nome": c["organizador_nome"], "serie_id": c["serie_id"], "conflita_com": conflitos})
    return saida


def _hora(d: dt.datetime) -> str:
    return f"{d.hour}h" if d.minute == 0 else f"{d.hour}h{d.minute:02d}"


def texto_aviso(item: dict, fuso: str) -> str:
    ini, fim = tempo.para_local(item["inicio_utc"], fuso), tempo.para_local(item["fim_utc"], fuso)
    partes = [item["titulo"], f"{_DIAS[ini.weekday()]} {_hora(ini)}–{_hora(fim)}"]
    if item.get("organizador_nome"):
        partes.append(f"de {item['organizador_nome']}")
    conf = item.get("conflita_com") or []
    partes.append("conflita com " + ", ".join(conf) if conf else "sem conflito")
    return " · ".join(partes)
