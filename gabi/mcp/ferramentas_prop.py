"""Ferramentas MCP da Fase 2: documentos (leitura), pedidos do canal, PROPOSTAS (só criam sugestão ou rascunho) e dado sensível com liberação única.

R1/R2/R14: nenhuma ferramenta aprova, envia, paga ou apaga; aprovar pedido e ligar regra são do painel. Texto de terceiros é dado.
Consome: cobrar.*, dinheiro.regras, fontes.paperless; recebe `executar` do servidor (escopo, registro e envelope)."""
import base64
import datetime as dt
import json

from gabi.cobrar import cobranca, pedidos
from gabi.cobrar.reembolso import itens_a_reembolsar
from gabi.dinheiro import regras
from gabi.dinheiro.valor import formatar
from gabi.fontes.paperless import ErroPaperless

ESCOPOS = {
    "documentos_buscar": "docs", "documentos_baixar": "docs",
    "pedidos_registrar": "pedidos", "pedidos_estado": "pedidos", "avisos_pendentes": "pedidos", "avisos_confirmar_entrega": "pedidos",
    "classificar_lancamento": "propostas", "regras_sugerir": "propostas", "tarefas_propor": "propostas", "reembolsos_preparar_email": "propostas",
    "reembolsos_listar": "fin", "pessoas_dado": "sensivel",
}
LIMITE_PDF = 5 * 1024 * 1024
CAMPOS_SENSIVEIS = ("cpf", "nascimento", "documento")


class ErroFerramenta(Exception):
    """Erro estruturado devolvido ao agente: {"erro": codigo, "mensagem": ...}."""

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo, self.mensagem = codigo, mensagem


def _paperless(paperless):
    if paperless is None:
        raise ErroFerramenta("fonte_indisponivel", "o Paperless não está configurado neste servidor")
    return paperless


def registrar(srv, executar, paperless) -> None:
    @srv.tool()
    def documentos_buscar(texto: str, limite: int = 20) -> dict:
        """Busca documentos no Paperless por texto. Devolve só id, título e data; use documentos_baixar para o arquivo."""
        def f(con, agora):
            try:
                docs = _paperless(paperless).docs(query=texto, page_size=min(max(limite, 1), 50))
            except ErroPaperless as e:
                raise ErroFerramenta("fonte_indisponivel", str(e)) from None
            return {"itens": [{"id": d["id"], "titulo": d.get("title"), "criado_em": d.get("created")} for d in docs[:limite]]}
        return executar("documentos_buscar", f)

    @srv.tool()
    def documentos_baixar(id: int) -> dict:
        """Baixa um documento do Paperless (PDF em base64, até 5 MB). Exige o escopo docs."""
        def f(con, agora):
            try:
                dados = _paperless(paperless).baixar(id)
            except ErroPaperless as e:
                raise ErroFerramenta("fonte_indisponivel", str(e)) from None
            if len(dados) > LIMITE_PDF:
                raise ValueError("documento maior que 5 MB")
            return {"id": id, "pdf_base64": base64.b64encode(dados).decode()}
        return executar("documentos_baixar", f)

    @srv.tool()
    def pedidos_registrar(solicitante: str, canal: str, mensagem_original: str, descricao: str, valor: str | None = None, vencimento: str | None = None,
                          anexo_paperless_id: int | None = None, pix_chave: str | None = None, linha_digitavel: str | None = None,
                          para_quem: str | None = None) -> dict:
        """Registra um pedido de pagamento feito por alguém no canal (solicitante = "canal:identificador"). Fica PENDENTE; quem decide é o Ricardo, no painel."""
        def f(con, agora):
            try:
                r = pedidos.registrar(con, solicitante=solicitante, canal=canal, mensagem_original=mensagem_original, descricao=descricao, valor=valor,
                                      vencimento=vencimento, anexo_base64=None, anexo_paperless_id=anexo_paperless_id, pix_chave=pix_chave,
                                      linha_digitavel=linha_digitavel, para_quem=para_quem)
            except pedidos.SemEscopo as e:
                raise ErroFerramenta("sem_escopo", str(e)) from None
            return {"pedido_id": r.pedido_id, "estado": r.estado, "texto_para_responder": r.texto_para_responder}
        return executar("pedidos_registrar", f)

    @srv.tool()
    def pedidos_estado(pedido_id: int) -> dict:
        """Estado de um pedido (pendente, aprovado, recusado ou info_pedida) e a mensagem ao solicitante, se houver."""
        def f(con, agora):
            try:
                p = pedidos.estado(con, pedido_id)
            except LookupError as e:
                raise ValueError(str(e)) from None
            return {k: p[k] for k in ("id", "estado", "descricao", "mensagem_ao_solicitante")}
        return executar("pedidos_estado", f)

    @srv.tool()
    def avisos_pendentes(desde: str | None = None) -> dict:
        """Avisos para entregar no canal (resultado de pedidos decididos). Ler NÃO tira da fila: confirme com avisos_confirmar_entrega depois de entregar."""
        def f(con, agora):
            return {"itens": pedidos.avisos_pendentes(con, dt.datetime.fromisoformat(desde) if desde else None)}
        return executar("avisos_pendentes", f)

    @srv.tool()
    def avisos_confirmar_entrega(aviso_id: int) -> dict:
        """Marca um aviso como entregue no canal (só depois da entrega de fato)."""
        def f(con, agora):
            pedidos.marcar_entregue(con, aviso_id)
            return {"aviso_id": aviso_id, "entregue": True}
        return executar("avisos_confirmar_entrega", f)

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

    @srv.tool()
    def tarefas_propor(titulo: str, vencimento: str | None = None, motivo: str = "") -> dict:
        """PROPÕE uma tarefa para o Ricardo. Cria só sugestão pendente; nada vai para a origem (Microsoft 365, Linear) sem ele aprovar."""
        def f(con, agora):
            if not titulo.strip():
                raise ValueError("a tarefa precisa de um título")
            return {"sugestao_id": regras.criar_sugestao(con, "tarefa", None, {"titulo": titulo.strip(), "vencimento": vencimento}, motivo or "sugestão do agente"),
                    "estado": "pendente"}
        return executar("tarefas_propor", f)

    @srv.tool()
    def reembolsos_preparar_email(empresa_id: str, itens: list[int] | None = None) -> dict:
        """Prepara o RASCUNHO do e-mail de cobrança de reembolso de uma empresa contratante. Não envia nada: o rascunho fica no painel (ADR-006)."""
        def f(con, agora):
            c = cobranca.montar(con, empresa_id, itens, hoje=agora.date())
            total = sum(i.em_aberto_centavos for i in c.itens)
            return {"rascunho": True, "cobranca_id": c.id, "para": c.para, "assunto": c.assunto, "itens": len(c.itens), "total": formatar(total),
                    "anexos": len(c.anexos), "itens_sem_comprovante": c.aviso_sem_comprovante}
        return executar("reembolsos_preparar_email", f)

    @srv.tool()
    def reembolsos_listar() -> dict:
        """Reembolsos em aberto por empresa contratante (ness, IONIC): valor a receber, número de itens e cobranças em andamento."""
        def f(con, agora):
            saida = []
            for e in con.execute("select id, nome from empresa where relacao='contratante' and excluido_em is null order by nome"):
                itens = itens_a_reembolsar(con, e["id"])
                saida.append({"empresa_id": e["id"], "nome": e["nome"], "itens": len(itens), "em_aberto": formatar(sum(i.em_aberto_centavos for i in itens)),
                              "reembolsos": [{"id": r["id"], "estado": r["estado"]} for r in con.execute(
                                  "select id, estado from reembolso where empresa_id=? and estado<>'quitado' order by id", (e["id"],))]})
            return {"empresas": saida}
        return executar("reembolsos_listar", f)

    @srv.tool()
    def pessoas_dado(pessoa_id: str, campo: str) -> dict:
        """Dado sensível de uma pessoa (cpf, nascimento ou documento). Só sai depois de uma liberação ÚNICA do Ricardo; sem ela devolve aguardando_liberacao."""
        def f(con, agora):
            if campo not in CAMPOS_SENSIVEIS:
                raise ValueError(f"campo deve ser um de {CAMPOS_SENSIVEIS}")
            lib = con.execute("select id from liberacao_sensivel where pessoa_id=? and campo=? and usada_em is null order by id limit 1", (pessoa_id, campo)).fetchone()
            if lib is None:
                return {"status": "aguardando_liberacao", "pessoa_id": pessoa_id, "campo": campo}
            p = con.execute("select dados from pessoa where id=?", (pessoa_id,)).fetchone()
            dados = json.loads((p["dados"] if p else None) or "{}")
            docs = dados.get("documentos") or []
            valor = (next((d["numero"] for d in docs if d.get("tipo", "").upper() == "CPF"), None) if campo == "cpf"
                     else dados.get("nascimento") if campo == "nascimento"
                     else next((d["numero"] for d in docs if d.get("tipo", "").upper() != "CPF"), None))
            con.execute("update liberacao_sensivel set usada_em=? where id=?", (agora.isoformat(), lib["id"]))
            return {"status": "liberado", "pessoa_id": pessoa_id, "campo": campo, "valor": valor}
        return executar("pessoas_dado", f)
