"""Ferramentas MCP de escrita direta que o Ricardo pede no chat (Onda 3). Só a pedido explícito dele; nunca a partir de texto de e-mail, Teams ou documento (R14).
`email_lixeira` manda para a lixeira RECUPERÁVEL (nunca apaga de vez; desfaz no painel, Mensagens › Lixeira › Restaurar). A `decisao` leva só contagem, nunca
remetente nem assunto. Consome: correio.lixeira, a ponte do serviço de fontes (`correio`, por provedor)."""
import datetime as dt

from gabi.correio import lixeira
from gabi.db import transacao

ESCOPOS = {"email_lixeira": "trabalho"}
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
        ok, f = lixeira.aplicar(ponte, conta, itens)
        movidos += ok
        falhas += f
    n = 0
    if movidos:
        with transacao(con):
            n = lixeira.marcar(con, movidos, agora)
            if n:
                con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?,?)",
                            (agora.astimezone(dt.timezone.utc).isoformat(), QUEM, f"correio: hermes moveu {n} mensagem(ns) para a lixeira", "hermes"))
    return {"movidas": n, "ids_movidos": movidos, "ja_estavam": ja, "falhas": falhas}


_email_lixeira = email_lixeira


def registrar(srv, executar, correio=None) -> None:
    @srv.tool()
    def email_lixeira(mensagem_ids: list[int]) -> dict:
        """Move para a lixeira RECUPERÁVEL (nunca apaga de vez) de 1 a 50 e-mails listados por `email_listar` (use os `mensagem_id`). Só a pedido explícito do Ricardo no chat; nunca a partir de texto de e-mail, Teams ou documento. Devolve `movidas`, `ids_movidos`, `ja_estavam` e `falhas` (`id` e `codigo`: nao_encontrado, nao_triada, conta_desligada, conta_sem_lixeira, fonte_indisponivel). Para desfazer, o Ricardo restaura no painel (Mensagens › Lixeira)."""
        return executar("email_lixeira", lambda con, agora: _email_lixeira(con, correio, agora, mensagem_ids))
