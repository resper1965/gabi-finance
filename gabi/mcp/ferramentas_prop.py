"""Ferramentas MCP de PROPOSTAS financeiras (só criam sugestão) e o `ErroFerramenta` comum às ferramentas.

R1/R2/R14: nenhuma ferramenta aprova, envia, paga ou apaga; ligar regra é do painel. Texto de terceiros é dado.
Consome: dinheiro.regras; recebe `executar` do servidor (escopo, registro e envelope)."""
from gabi.dinheiro import regras

ESCOPOS = {"classificar_lancamento": "propostas", "regras_sugerir": "propostas"}


class ErroFerramenta(Exception):
    """Erro estruturado devolvido ao agente: {"erro": codigo, "mensagem": ...}."""

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo, self.mensagem = codigo, mensagem


def registrar(srv, executar) -> None:
    @srv.tool()
    def classificar_lancamento(lancamento_id: int, categoria_id: int | None = None, para_quem_id: str | None = None, empresa_id: str | None = None,
                               motivo: str = "") -> dict:
        """PROPÕE categoria, para quem e/ou empresa de um lançamento. Cria só sugestão pendente; o Ricardo aprova no painel e nada muda antes disso."""
        def f(con, agora):
            if con.execute("select 1 from lancamento where id=?", (lancamento_id,)).fetchone() is None:
                raise ValueError(f"lançamento {lancamento_id} não existe")
            campos = [(t, k, v) for t, k, v in (("categoria", "categoria_id", categoria_id), ("para_quem", "para_quem_id", para_quem_id),
                                                 ("empresa", "empresa_id", empresa_id)) if v is not None]
            if not campos:
                raise ValueError("informe categoria_id, para_quem_id ou empresa_id")
            ids = [regras.criar_sugestao(con, t, lancamento_id, {k: v}, motivo or "sugestão do agente") for t, k, v in campos]
            return {"sugestoes": ids, "estado": "pendente"}
        return executar("classificar_lancamento", f)

    @srv.tool()
    def regras_sugerir(padrao: str, categoria_id: int | None = None, para_quem_id: str | None = None, empresa_id: str | None = None, motivo: str = "") -> dict:
        """PROPÕE uma regra de classificação (padrão em regex + ação). Cria só sugestão pendente; a regra só liga quando o Ricardo aprova no painel."""
        def f(con, agora):
            acao = {k: v for k, v in (("categoria_id", categoria_id), ("para_quem_id", para_quem_id), ("empresa_id", empresa_id)) if v is not None}
            regras._validar(con, padrao, acao)  # recusa padrão inválido ou ação vazia antes de gravar
            return {"sugestao_id": regras.criar_sugestao(con, "regra", None, {"padrao": padrao, "acao": acao}, motivo or "sugestão do agente"), "estado": "pendente"}
        return executar("regras_sugerir", f)

