"""Ferramentas MCP de ENVIOS com anuência: só PROPÕEM evento de agenda e mensagem do Teams; nada sai daqui.

O envio só acontece quando o Ricardo clica Enviar no painel (rota de envios). Nenhuma ferramenta aprova, confirma ou envia.
Título, texto, nome e e-mail nunca vão para log; erro de provedor vira código fixo. Os candidatos de um nome ambíguo voltam ao agente na mensagem, para ele perguntar ao Ricardo.
Consome: envios.propostas (criar_*, contas_teams, normalizar_nome, ErroEnvio), PonteGraph.teams_equipes/teams_canais (lista viva), parametro painel.url;
recebe `executar` do servidor (escopo, registro e envelope)."""
import json

from gabi.envios import propostas
from gabi.envios.propostas import ErroEnvio
from gabi.fontes.graph_ness import ErroGraphNess
from gabi.mcp.ferramentas_prop import ErroFerramenta

ESCOPOS = {"propor_evento": "envios", "propor_teams": "envios"}
_MENSAGENS = {
    "requisicao_invalida": "entrada inválida (confira limites e formato)",
    "conta_nao_permitida": "conta não liberada para envios",
    "inicio_passado": "o início do evento já passou",
    "convidado_invalido": "convidado inválido (use e-mail ou nome de contato)",
    "convidado_ambiguo": "convidado não encontrado ou com mais de um e-mail; pergunte ao Ricardo qual é",
    "destino_ambiguo": "destino não encontrado ou com mais de uma opção; pergunte ao Ricardo qual é",
    "fonte_indisponivel": "o Teams da ness não está disponível agora",
}


def _candidato(c: dict) -> str:
    return f"{c['nome']} <{c['email']}>" if c.get("email") else str(c.get("nome", ""))


def _erro(e: ErroEnvio) -> ErroFerramenta:
    msg = e.mensagem if e.mensagem != e.codigo else _MENSAGENS.get(e.codigo, e.codigo)
    if e.candidatos is not None:
        msg += "; candidatos: " + ("; ".join(_candidato(c) for c in e.candidatos) if e.candidatos else "nenhum")
    return ErroFerramenta(e.codigo, msg)


def _com_link(con, r: dict) -> dict:
    """Acrescenta `link` = painel.url + "#envios" quando o parâmetro existe; sem ele, o agente cita só o id."""
    l = con.execute("select valor from parametro where chave='painel.url'").fetchone()
    if l is None:
        return r
    try:
        url = json.loads(l[0])
    except (ValueError, TypeError):
        url = l[0]  # texto cru também vale
    return {**r, "link": url.rstrip("#") + "#envios"} if isinstance(url, str) and url.strip() else r


def _unico(itens: list[dict], nome: str) -> dict:
    """Casa por igualdade do nome inteiro (sem caixa e acento); 0 ou mais de 1 dá destino_ambiguo só com os nomes."""
    alvo = propostas.normalizar_nome(nome)
    achados = [i for i in itens if alvo and propostas.normalizar_nome(i["nome"]) == alvo]
    if len(achados) != 1:
        raise ErroEnvio("destino_ambiguo", candidatos=[{"nome": i["nome"]} for i in achados])
    return achados[0]


def registrar(srv, executar, graph) -> None:
    @srv.tool()
    def propor_evento(conta: str, titulo: str, inicio: str, duracao_min: int, convidados: list[str], descricao: str = "", online: bool = True) -> dict:
        """PROPÕE um evento na agenda (conta liberada, `inicio` ISO de Brasília, duração 5 a 720 min, 1 a 30 convidados por e-mail ou nome de contato).
        Cria só proposta pendente: o envio só sai quando o Ricardo clica Enviar no painel. Nome ambíguo volta com os candidatos para você perguntar."""
        def f(con, agora):
            try:
                r = propostas.criar_evento(con, agora, conta=conta, titulo=titulo, inicio=inicio, duracao_min=duracao_min,
                                           convidados=convidados, descricao=descricao, online=online)
            except ErroEnvio as e:
                raise _erro(e) from None
            return _com_link(con, r)
        return executar("propor_evento", f)

    @srv.tool()
    def propor_teams(texto: str, chat_com: str = "", equipe: str = "", canal: str = "") -> dict:
        """PROPÕE uma mensagem no Teams da ness (texto simples, 1 a 4000 caracteres). Exatamente um destino: `chat_com` (nome da conversa) ou `equipe` + `canal`.
        Cria só proposta pendente: o envio só sai quando o Ricardo clica Enviar no painel. Destino ambíguo volta com os candidatos para você perguntar."""
        def f(con, agora):
            try:
                tem_chat, tem_equipe, tem_canal = (bool((x or "").strip()) for x in (chat_com, equipe, canal))
                if not ((tem_chat and not tem_equipe and not tem_canal) or (not tem_chat and tem_equipe and tem_canal)):
                    raise ErroEnvio("requisicao_invalida", "informe chat_com, ou equipe e canal (só um destino)")
                contas = propostas.contas_teams(con)
                if len(contas) != 1:
                    raise ErroEnvio("conta_nao_permitida")
                conta = contas[0]
                if tem_chat:
                    r = propostas.criar_teams_chat(con, agora, conta=conta, chat_com=chat_com, texto=texto)
                else:
                    if graph is None:
                        raise ErroEnvio("fonte_indisponivel")
                    try:
                        eq = _unico(graph.teams_equipes(conta), equipe)
                        ca = _unico(graph.teams_canais(conta, eq["id"]), canal)
                    except ErroGraphNess:
                        raise ErroEnvio("fonte_indisponivel") from None  # o texto do provedor nunca chega ao agente
                    r = propostas.criar_teams_canal(con, agora, conta=conta, equipe_id=eq["id"], canal_id=ca["id"],
                                                    equipe_nome=eq["nome"], canal_nome=ca["nome"], texto=texto)
            except ErroEnvio as e:
                raise _erro(e) from None
            return _com_link(con, r)
        return executar("propor_teams", f)
