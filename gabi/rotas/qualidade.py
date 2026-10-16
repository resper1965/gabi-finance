"""GET /api/v1/gabi/qualidade (EV5): aceite das sugestões, custo por tarefa e latência das ferramentas. Só o boss; só leitura. Consome: qualidade."""
from fastapi import APIRouter, Depends, Request

from gabi import qualidade
from gabi.envelope import envelope
from gabi.identidade import exigir
from gabi.rotas.dinheiro import _agora, _con

router = APIRouter(prefix="/api/v1/gabi", dependencies=[Depends(exigir("boss"))])


@router.get("/qualidade")
def ler(request: Request):
    """A Gabi acerta, custa pouco e responde rápido? Sugestões aceitas, custo por tarefa (30 dias) e latência por ferramenta (7 dias)."""
    con = _con(request)
    try:
        return envelope(con, qualidade.qualidade(con, _agora(request).date()), agora=_agora(request))
    finally:
        con.close()
