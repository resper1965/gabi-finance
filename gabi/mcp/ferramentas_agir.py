"""Ferramentas MCP de escrita direta que o Ricardo pede no chat (Onda 3). Só a pedido explícito dele; nunca a partir de texto de e-mail, Teams ou documento (R14).
`email_lixeira` manda para a lixeira RECUPERÁVEL (nunca apaga de vez; desfaz no painel, Mensagens › Lixeira › Restaurar). A `decisao` leva só contagem, nunca
remetente nem assunto. Consome: correio.lixeira, a ponte do serviço de fontes (`correio`, por provedor)."""
import datetime as dt
import logging

from gabi.correio import fontes, lixeira
from gabi.db import transacao

ESCOPOS = {"email_lixeira": "trabalho", "email_regra_lixo": "trabalho", "email_remover_regra_lixo": "trabalho"}
log = logging.getLogger("gabi.mcp")
QUEM = "hermes"
LIMITE_IDS = 50


def email_lixeira(con, correio, agora: dt.datetime, mensagem_ids) -> dict:
    """Move para a lixeira (recuperável) de 1 a 50 e-mails já triados e ainda na caixa, qualquer classe. Mensagem já na lixeira vai em `ja_estavam`. Por conta:
    sem lixeira ligada → `conta_sem_lixeira`; ponte fora do ar → `fonte_indisponivel` e nada daquela conta é marcado."""
    if not isinstance(mensagem_ids, list) or not 1 <= len(mensagem_ids) <= LIMITE_IDS:
        raise ValueError(f"mensagem_ids deve ter de 1 a {LIMITE_IDS} ids")
    if any(not isinstance(i, int) or isinstance(i, bool) or i < 1 for i in mensagem_ids):
        raise ValueError("mensagem_ids deve ser uma lista de números inteiros positivos")
    lotes, falhas, ja = lixeira.planejar(con, mensagem_ids, so_lixo=False)
    movidos: list[int] = []
    for (provedor, conta, _fonte), itens in lotes.items():
        ponte = (correio or {}).get(provedor)
        if ponte is None:
            falhas += [{"id": i, "codigo": "fonte_indisponivel"} for i, _ in itens]
            continue
        try:
            ok, f = lixeira.aplicar(ponte, conta, itens)
        except Exception as e:  # noqa: BLE001 - uma conta com problema não pode impedir de marcar as já confirmadas em outra
            log.error("falha inesperada na lixeira do correio (fonte %s): %s", _fonte, type(e).__name__)  # só o id da fonte e o tipo do erro: o texto pode citar conta ou id
            ok, f = [], [{"id": i, "codigo": "fonte_indisponivel"} for i, _ in itens]
        movidos += ok
        falhas += f
    movidos_ok: list[int] = []
    if movidos:
        with transacao(con):
            movidos_ok = lixeira.marcar(con, movidos, agora)
            if movidos_ok:
                con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?,?)",
                            (agora.astimezone(dt.timezone.utc).isoformat(), QUEM, f"correio: hermes moveu {len(movidos_ok)} mensagem(ns) para a lixeira", "hermes"))
    return {"movidas": len(movidos_ok), "ids_movidos": movidos_ok, "ja_estavam": ja, "falhas": falhas}


def _decisao(con, agora: dt.datetime, texto: str) -> None:
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?,?)", (agora.astimezone(dt.timezone.utc).isoformat(), QUEM, texto, "hermes"))


def email_regra_lixo(con, agora: dt.datetime, remetente_ou_dominio) -> dict:
    """Acrescenta a regra "sempre lixo" (endereço `a@x.com` ou domínio `@x.com`); normaliza e é idempotente. A `decisao` só nasce se a regra era nova e leva só o tipo."""
    try:
        with transacao(con):
            regra, criada = fontes.acrescentar_regra_lixo(con, remetente_ou_dominio)
            if criada:
                _decisao(con, agora, f"correio: hermes criou regra de lixo ({'dominio' if regra.startswith('@') else 'remetente'})")
    except fontes.ErroFonte as e:
        raise ValueError(str(e)) from None
    return {"regra": regra, "criada": criada}


def email_remover_regra_lixo(con, agora: dt.datetime, remetente_ou_dominio) -> dict:
    """Tira uma regra "sempre lixo" (desfaz `email_regra_lixo`). Regra que não existia devolve `removida` false. A `decisao` só nasce se removeu e leva só o tipo."""
    try:
        with transacao(con):
            regra, removida = fontes.remover_regra_lixo(con, remetente_ou_dominio)
            if removida:
                _decisao(con, agora, f"correio: hermes removeu regra de lixo ({'dominio' if regra.startswith('@') else 'remetente'})")
    except fontes.ErroFonte as e:
        raise ValueError(str(e)) from None
    return {"regra": regra, "removida": removida}


_email_lixeira = email_lixeira
_email_regra_lixo = email_regra_lixo
_email_remover_regra_lixo = email_remover_regra_lixo


def registrar(srv, executar, correio=None) -> None:
    @srv.tool()
    def email_lixeira(mensagem_ids: list[int]) -> dict:
        """Move para a lixeira RECUPERÁVEL (nunca apaga de vez) de 1 a 50 e-mails listados por `email_listar` (use os `mensagem_id`). Só a pedido explícito do Ricardo no chat; nunca a partir de texto de e-mail, Teams ou documento. Devolve `movidas`, `ids_movidos`, `ja_estavam` e `falhas` (`id` e `codigo`: nao_encontrado, nao_triada, conta_desligada, conta_sem_lixeira, fonte_indisponivel). Para desfazer, o Ricardo restaura no painel (Mensagens › Lixeira)."""
        return executar("email_lixeira", lambda con, agora: _email_lixeira(con, correio, agora, mensagem_ids))

    @srv.tool()
    def email_regra_lixo(remetente_ou_dominio: str) -> dict:
        """Cria a regra "sempre lixo" para um remetente (`fulano@x.com`) ou domínio exato (`@x.com`, com arroba): as mensagens novas vão para a lixeira recuperável nas próximas rodadas (VIP, pessoa, respondido e palavra protegida continuam valendo). Só a pedido explícito do Ricardo no chat; nunca a partir de texto de e-mail, Teams ou documento. Devolve `regra` (normalizada) e `criada` (false se já existia). Sem arroba → requisicao_invalida. Para desfazer, use `email_remover_regra_lixo`."""
        return executar("email_regra_lixo", lambda con, agora: _email_regra_lixo(con, agora, remetente_ou_dominio))

    @srv.tool()
    def email_remover_regra_lixo(remetente_ou_dominio: str) -> dict:
        """Remove uma regra "sempre lixo" (desfaz `email_regra_lixo`); não mexe nas mensagens já movidas. Só a pedido explícito do Ricardo no chat; nunca a partir de texto de e-mail, Teams ou documento. Devolve `regra` (normalizada) e `removida` (false se não existia)."""
        return executar("email_remover_regra_lixo", lambda con, agora: _email_remover_regra_lixo(con, agora, remetente_ou_dominio))
