"""Canal de decisão (/api/v1/decisoes): criar e listar perguntas com opções numeradas. Só o boss.
Quem responde é o Ricardo, pelo canal (ferramenta MCP `decisao_responder`); a API só cria a pergunta e deixa ler o estado. Consome: decisoes."""
from fastapi import APIRouter, Depends, Request

from gabi import decisoes
from gabi.envelope import envelope
from gabi.identidade import Identidade, exigir
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, erro

router = APIRouter(prefix="/api/v1/decisoes", dependencies=[Depends(exigir("boss"))])


@router.get("/perguntas")
def perguntas(request: Request, estado: str | None = None):
    """Perguntas do canal de decisão (padrão: todas, as mais novas primeiro; `estado=aberta` só as que esperam resposta)."""
    con = _con(request)
    try:
        itens = decisoes.abertas(con) if estado == "aberta" else decisoes.todas(con)
        return envelope(con, {"perguntas": itens}, agora=_agora(request))
    finally:
        con.close()


@router.post("/perguntas")
async def criar(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Cria uma pergunta com opções numeradas (n, rotulo, efeito, parametros); `efeito` só da lista fechada (registrar_nota, marcar_conta_nao, marcar_conta_sim, criar_compromisso, atribuir_para_quem)."""
    corpo = _corpo(await _json(request))
    con = _con(request)
    try:
        try:
            pid = decisoes.criar_pergunta(con, corpo.get("tipo"), corpo.get("titulo"), corpo.get("contexto"), corpo.get("opcoes"),
                                          f"api:{ident.login}", _agora(request).isoformat())
        except decisoes.ErroDecisao as e:
            raise erro(400, e.codigo if e.codigo != "opcoes_invalidas" else "requisicao_invalida", e.mensagem) from None
        return envelope(con, {"id": pid}, agora=_agora(request))
    finally:
        con.close()
