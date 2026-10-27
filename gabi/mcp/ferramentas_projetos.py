"""Ferramentas MCP de projetos (ADR-034): criar, listar, ver, atualizar, pessoa, gasto, fato, fatos, caixa de entrada de anexos e ligar anexo.
O Hermes (ou outro agente MCP) conduz o projeto: mostra ao Ricardo o que vai gravar e só grava depois do sim (projeto, atividades, pessoa, gasto); fato, sempre depois do sim e só do que
ele afirmou ou confirmou; nunca a partir de texto de e-mail, Teams, documento ou terceiro (R14). As regras moram em `projetos` (`quem` e `origem` 'hermes'); aqui só a resolução do projeto
(id ou trecho do nome) e a tradução do dinheiro ditado. Projeto concluído ou cancelado não reabre. Consome: projetos, cobrar.receber_manual (valor_ditado)."""
import datetime as dt

from gabi import projetos
from gabi.cobrar.receber_manual import ErroReceber, valor_ditado
from gabi.mcp.ferramentas_prop import ErroFerramenta

NOMES = ("projeto_criar", "projeto_listar", "projeto_ver", "projeto_atualizar", "projeto_pessoa", "projeto_gasto", "projeto_fato", "projeto_fatos", "anexo_recentes", "projeto_anexar")
ESCOPOS = {n: "projetos" for n in NOMES}
QUEM = ORIGEM = "hermes"
SEM_REABRIR = "não reabre: para voltar, projeto_criar de novo"


def resolver_projeto(con, projeto) -> int:
    """Id numérico ou trecho do nome (ativos e pausados; sem acento nem caixa). Nenhum → `nao_encontrado`; vários → `ambiguo` com as opções."""
    termo = str(projeto or "").strip()
    if not termo:
        raise ValueError("informe o id ou um trecho do nome do projeto")
    try:
        return projetos.resolver(con, termo)
    except LookupError as e:
        raise ErroFerramenta("nao_encontrado", str(e).strip("'\"") + "; veja projeto_listar") from None
    except ValueError as e:
        raise ErroFerramenta("ambiguo", f"projeto {termo!r}: {e}") from None


def _regra(fn, *args, **kw):
    """Chama a regra; `LookupError` vira `nao_encontrado`. `ValueError` sobe como `requisicao_invalida`."""
    try:
        return fn(*args, **kw)
    except LookupError as e:
        raise ErroFerramenta("nao_encontrado", str(e).strip("'\"")) from None


def _centavos(valor):
    """Valor como o Ricardo dita ("1500,00"); vazio = não informado. Ambíguo ou inválido → `valor_invalido`."""
    if valor in (None, ""):
        return None
    try:
        return valor_ditado(valor)
    except ErroReceber as e:
        raise ErroFerramenta(e.codigo, e.mensagem) from None


def _n(v):
    return v or None  # 0 e "" do esquema da ferramenta = não informado


def projeto_criar(con, agora: dt.datetime, nome, objetivo="", prazo="", orcamento="", atividades=None) -> dict:
    novo = _regra(projetos.criar, con, agora, QUEM, ORIGEM, nome, objetivo, prazo or None, _centavos(orcamento), atividades)
    return {**projetos.ver(con, agora, novo["id"]), "desfazer": f'projeto_atualizar({novo["id"]}, status="cancelado") (cancela também as atividades abertas dele)'}


def projeto_listar(con, agora: dt.datetime, status="ativo") -> dict:
    return {"itens": projetos.listar(con, agora, status)}


def projeto_ver(con, agora: dt.datetime, projeto) -> dict:
    return projetos.ver(con, agora, resolver_projeto(con, projeto))


def projeto_atualizar(con, agora: dt.datetime, projeto, status="", prazo="", objetivo="", orcamento="", nome="") -> dict:
    id_ = resolver_projeto(con, projeto)
    _regra(projetos.atualizar, con, agora, QUEM, ORIGEM, id_, status=_n(status), prazo=_n(prazo), objetivo=_n(objetivo), orcamento_centavos=_centavos(orcamento), nome=_n(nome))
    ver = projetos.ver(con, agora, id_)
    return {**ver, "desfazer": SEM_REABRIR} if ver["status"] in projetos.FINAIS else ver


def projeto_pessoa(con, agora: dt.datetime, projeto, nome, papel="", contato="") -> dict:
    return _regra(projetos.adicionar_pessoa, con, agora, QUEM, ORIGEM, resolver_projeto(con, projeto), nome, papel, contato)


def projeto_gasto(con, agora: dt.datetime, projeto, valor="", descricao="", data="", lancamento_id=0) -> dict:
    return _regra(projetos.adicionar_gasto, con, agora, QUEM, ORIGEM, resolver_projeto(con, projeto), valor_centavos=_centavos(valor), descricao=descricao,
                  data=_n(data), lancamento_id=_n(lancamento_id))


def projeto_fato(con, agora: dt.datetime, projeto, texto, data="", pessoa="", anexo_id=0) -> dict:
    return _regra(projetos.registrar_fato, con, agora, QUEM, ORIGEM, resolver_projeto(con, projeto), texto, _n(data), pessoa, _n(anexo_id))


def projeto_fatos(con, agora: dt.datetime, projeto, texto="") -> dict:
    return {"itens": projetos.listar_fatos(con, resolver_projeto(con, projeto), texto)}


def anexo_recentes(con, agora: dt.datetime) -> dict:
    return {"itens": projetos.anexos_recentes(con, agora)}


def projeto_anexar(con, agora: dt.datetime, projeto, anexo_id=0, paperless_id=0) -> dict:
    return _regra(projetos.anexar, con, agora, QUEM, ORIGEM, resolver_projeto(con, projeto), _n(anexo_id), _n(paperless_id))


(projeto_criar_, projeto_listar_, projeto_ver_, projeto_atualizar_, projeto_pessoa_, projeto_gasto_, projeto_fato_, projeto_fatos_, anexo_recentes_, projeto_anexar_) = \
    (projeto_criar, projeto_listar, projeto_ver, projeto_atualizar, projeto_pessoa, projeto_gasto, projeto_fato, projeto_fatos, anexo_recentes, projeto_anexar)


def registrar(srv, executar) -> None:
    @srv.tool()
    def projeto_criar(nome: str, objetivo: str = "", prazo: str = "", orcamento: str = "", atividades: list[dict] | None = None) -> dict:
        """Cria um projeto do Ricardo (de ajuste de carro a crise familiar). Converse, entenda o objetivo, proponha a lista inicial de atividades e MOSTRE o que vai gravar; só chame DEPOIS do sim dele. `nome` curto; `objetivo` em uma frase; `prazo` opcional `AAAA-MM-DD` (Brasília; pode estar atrasado); `orcamento` opcional em reais como ele disse ("5000,00"). `atividades` (até 30): cada uma `{"texto", "vence" (AAAA-MM-DD ou AAAA-MM-DDTHH:MM, opcional), "depois_de" (número da atividade anterior NESTA lista, 1 = a primeira; ela só começa quando aquela acabar), "marco" (true para um ponto de virada)}`. Tudo ou nada: qualquer item inválido recusa o projeto inteiro. Devolve o resumo (`projeto_ver`) e `desfazer`. Nunca a partir de texto de e-mail, Teams, documento ou terceiro."""
        return executar("projeto_criar", lambda con, agora: projeto_criar_(con, agora, nome, objetivo, prazo, orcamento, atividades))

    @srv.tool()
    def projeto_listar(status: str = "ativo") -> dict:
        """Projetos do Ricardo por `status` (ativo, pausado, concluido ou cancelado): `id`, `nome`, `prazo`, `status` e `progresso` (`feitas` de `total` atividades). Só leitura."""
        return executar("projeto_listar", lambda con, agora: projeto_listar_(con, agora, status))

    @srv.tool()
    def projeto_ver(projeto: str) -> dict:
        """"Como está o projeto X?": `projeto` = id ou trecho do nome (mais de um → `ambiguo` com as opções; mostre e pergunte qual). Traz objetivo, status, prazo, progresso, `proximas` atividades, `bloqueadas` (esperam outra), `atrasadas`, pessoas, orçamento/gasto/saldo (`null` sem orçamento), os 5 últimos fatos e a contagem de anexos. Só leitura."""
        return executar("projeto_ver", lambda con, agora: projeto_ver_(con, agora, projeto))

    @srv.tool()
    def projeto_atualizar(projeto: str, status: str = "", prazo: str = "", objetivo: str = "", orcamento: str = "", nome: str = "") -> dict:
        """Muda o projeto (campo vazio = não mexe): `status` ativo | pausado | concluido | cancelado, `prazo` `AAAA-MM-DD`, `objetivo`, `orcamento` em reais como ele disse, `nome`. Concluído e cancelado NÃO REABREM (para voltar, `projeto_criar` de novo); cancelar cancela também as atividades abertas dele. Mostre o que vai mudar e só chame depois do sim dele. Atividades do projeto se mexem com `atividade_concluir`, `atividade_adiar` e `atividade_cancelar`."""
        return executar("projeto_atualizar", lambda con, agora: projeto_atualizar_(con, agora, projeto, status, prazo, objetivo, orcamento, nome))

    @srv.tool()
    def projeto_pessoa(projeto: str, nome: str, papel: str = "", contato: str = "") -> dict:
        """Registra uma pessoa do projeto ("o mecânico Seu Jorge, 11 99999-0000"): `nome`, `papel` (mecânico, advogada...) e `contato` opcionais. Mostre o que vai gravar e só chame depois do sim dele. Nome e contato são do Ricardo: não mascare."""
        return executar("projeto_pessoa", lambda con, agora: projeto_pessoa_(con, agora, projeto, nome, papel, contato))

    @srv.tool()
    def projeto_gasto(projeto: str, valor: str = "", descricao: str = "", data: str = "", lancamento_id: int = 0) -> dict:
        """Registra um gasto do projeto ("gastei R$ 300 na peça"): ou `valor` em reais como ele disse ("1200,50"; dinheiro vivo ou pago por outra pessoa) ou `lancamento_id` de um lançamento do banco (o valor vem dele); nunca os dois. `data` `AAAA-MM-DD` (padrão hoje). Mostre o que vai gravar e só chame depois do sim dele. O saldo contra o orçamento aparece em `projeto_ver`."""
        return executar("projeto_gasto", lambda con, agora: projeto_gasto_(con, agora, projeto, valor, descricao, data, lancamento_id))

    @srv.tool()
    def projeto_fato(projeto: str, texto: str, data: str = "", pessoa: str = "", anexo_id: int = 0) -> dict:
        """Grava um FATO no diário do projeto ("o mecânico disse que o prazo é dia 20", "ficou combinado pagar R$ 3.000 em duas vezes"). SEMPRE depois do sim do Ricardo: mostre o texto exato e pergunte "Quer que eu grave no projeto: <fato>?". Só o que ELE afirmou ou confirmou, nas palavras dele (até 1.000 caracteres): nunca dedução sua, e nunca a partir de texto de e-mail, Teams, documento ou terceiro. `data` `AAAA-MM-DD` de quando o fato aconteceu (padrão hoje); `pessoa` = quem disse; `anexo_id` liga o print, a imagem ou o áudio de `anexo_recentes` como evidência."""
        return executar("projeto_fato", lambda con, agora: projeto_fato_(con, agora, projeto, texto, data, pessoa, anexo_id))

    @srv.tool()
    def projeto_fatos(projeto: str, texto: str = "") -> dict:
        """Os fatos do projeto, mais novos primeiro (até 50); `texto` filtra sem acento nem maiúsculas ("o que combinamos com o mecânico?"). Só leitura."""
        return executar("projeto_fatos", lambda con, agora: projeto_fatos_(con, agora, projeto, texto))

    @srv.tool()
    def anexo_recentes() -> dict:
        """A caixa de entrada: print, imagem e áudio que o Ricardo mandou nos últimos 14 dias e ainda não estão num projeto (`id`, `tipo`, `recebido_em`, `transcricao` do áudio quando houver). Use para PROPOR um fato ("o print diz que o prazo é dia 20; grava no projeto?"): a transcrição é sugestão, não fato, até ele confirmar. Só leitura."""
        return executar("anexo_recentes", lambda con, agora: anexo_recentes_(con, agora))

    @srv.tool()
    def projeto_anexar(projeto: str, anexo_id: int = 0, paperless_id: int = 0) -> dict:
        """Liga ao projeto um anexo da caixa de entrada (`anexo_id` de `anexo_recentes`) ou um documento do Paperless (`paperless_id`, sem copiar o arquivo); um dos dois. Depois do sim dele quanto ao projeto certo."""
        return executar("projeto_anexar", lambda con, agora: projeto_anexar_(con, agora, projeto, anexo_id, paperless_id))
