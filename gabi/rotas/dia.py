"""Rotas /api/v1 do dia: Hoje e Agenda (vieram de rotas/trabalho.py; ADR-023). Só leitura. Consome: dia, agenda.consulta, envelope."""
from fastapi import APIRouter, Depends, Request

from gabi import dia
from gabi.agenda import consulta
from gabi.envelope import envelope
from gabi.identidade import exigir
from gabi.rotas.dinheiro import _agora, _con, _data

router = APIRouter(prefix="/api/v1", dependencies=[Depends(exigir("boss"))])


@router.get("/hoje")
def hoje(request: Request):
    """O dia do Ricardo: prioridades, agenda, e-mails que importam e dinheiro."""
    con = _con(request)
    try:
        return envelope(con, dia.hoje(con, _agora(request), painel=True), agora=_agora(request))
    finally:
        con.close()


@router.get("/agenda")
def agenda(request: Request, de: str | None = None, ate: str | None = None):
    """Eventos do período e conflitos com sugestão de horário (proposta, não envia nada)."""
    con = _con(request)
    try:
        d1, d2 = _data(de, "de"), _data(ate, "ate")
        d1 = d1 or consulta.dia_local(_agora(request), consulta.fuso_da_agenda(con))
        d2 = d2 or d1
        fuso = consulta.fuso_da_agenda(con)
        eventos = consulta.agenda_intervalo(con, d1.isoformat(), d2.isoformat(), fuso, painel=True)
        for e in eventos:  # `inicio`/`fim` ficam como alias do horário local até o painel migrar (Task 8)
            e["inicio"], e["fim"] = e["inicio_local"], e["fim_local"]
        conflitos = [{"evento_a": c.evento_a, "evento_b": c.evento_b, "sugestao_inicio": c.sugestao_inicio}
                     for c in consulta.conflitos(con, d1.isoformat(), d2.isoformat(), fuso)]
        return envelope(con, {"eventos": eventos, "conflitos": conflitos}, agora=_agora(request))
    finally:
        con.close()
