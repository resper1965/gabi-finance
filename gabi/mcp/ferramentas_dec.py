"""Ferramentas MCP do canal de decisão (escopo `decisoes`): listar perguntas abertas e registrar a resposta do Ricardo.
R1: a única escrita é gravar a escolha que ele deu (um número) numa pergunta que a própria Gabi criou; o efeito vem da lista fechada de gabi.decisoes
e não existe ferramenta para criar pergunta nem para escolher efeito pelo canal. Texto de terceiros nunca vira opção. Consome: decisoes."""
from gabi import decisoes
from gabi.mcp.ferramentas_prop import ErroFerramenta

ESCOPOS = {"decisoes_abertas": "decisoes", "decisao_responder": "decisoes"}


def registrar(srv, executar) -> None:
    @srv.tool()
    def decisoes_abertas() -> dict:
        """Perguntas que esperam a decisão do Ricardo, cada uma com opções numeradas (n, rotulo). Apresente título, contexto e as opções; não escolha por ele."""
        def f(con, agora):
            return {"itens": decisoes.abertas(con)}
        return executar("decisoes_abertas", f)

    @srv.tool()
    def decisao_responder(pergunta_id: int, opcao: int) -> dict:
        """Registra a escolha do Ricardo (o NÚMERO da opção) numa pergunta aberta. Só chame depois de ele responder com um número claro; se for ambíguo, confirme antes."""
        def f(con, agora):
            try:
                return decisoes.responder(con, pergunta_id, opcao, "ricardo", agora.isoformat())
            except decisoes.ErroDecisao as e:
                raise ErroFerramenta(e.codigo, e.mensagem) from None
        return executar("decisao_responder", f)
