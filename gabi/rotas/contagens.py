"""Contadores do sino e do menu do painel: quantos itens pedem uma decisão do Ricardo, por área.
Reusa as consultas das próprias telas (sem SQL novo), para o número nunca divergir da lista. Consome sugestao, contas_pagar, cartões, assinaturas e lançamentos a indicar (quem gastou)."""
from fastapi import APIRouter, Depends, Request

from gabi.dinheiro import consultas, contas_pagar as cp
from gabi.envelope import envelope
from gabi.identidade import exigir
from gabi.rotas.dinheiro import _agora, _con
from gabi.rotas.gastos import assinaturas

router = APIRouter(prefix="/api/v1", dependencies=[Depends(exigir("boss"))])


@router.get("/contagens")
def contagens(request: Request):
    """Itens que pedem decisão por área do menu (caixa, gastos, regras) e o total do sino."""
    con = _con(request)
    try:
        hoje = _agora(request).date()
        grupos = cp.contas_a_pagar(con, hoje, None)
        caixa = len(grupos["atrasadas"]) + len(grupos["a_conferir"])
        regras = con.execute("select count(*) from sugestao where estado='pendente'").fetchone()[0]
        vencidas = sum(1 for f in cp.faturas_abertas(con, hoje) if f["vencimento"] < hoje.isoformat())
        alerta = sum(1 for i in assinaturas(request)["dados"]["itens"] if i["no_rol"] and (i["sinais"]["cobrada_depois_de_cancelar"] or i["sinais"]["reajustou"]))
        avisos = con.execute("select count(*) from aviso where entregue_em is null").fetchone()[0]
        # quem gastou a indicar: só o mês corrente (o histórico dos cartões compartilhados tem milhares; fica no filtro da tela)
        a_indicar = con.execute(f"select count(*) from lancamento l join conta c on c.id=l.conta_id where {consultas.A_INDICAR} and l.data>=?",
                                (hoje.replace(day=1).isoformat(),)).fetchone()[0]
        menu = {"caixa": caixa, "gastos": vencidas + alerta + a_indicar, "regras": regras, "avisos": avisos}
        return envelope(con, {"sino": sum(menu.values()), "menu": menu}, agora=_agora(request))
    finally:
        con.close()
