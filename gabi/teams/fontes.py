"""Cadastro das contas do Teams (`teams_fonte`): só decide QUAIS contas o coletor lê. Nenhum segredo e nenhum texto de mensagem aqui."""
import sqlite3

from gabi.fontes.google_oauth import ErroGoogleOAuth, conta_valida

ESTADOS = ("sim", "nao", "a_decidir")


class ErroFonte(ValueError):
    """Pedido inválido (400) ou inexistente (404), com a mensagem em pt-BR para o painel."""

    def __init__(self, mensagem: str, nao_encontrado: bool = False, conflito: bool = False):
        super().__init__(mensagem)
        self.nao_encontrado, self.conflito = nao_encontrado, conflito


def listar(con) -> list[dict]:
    return [dict(r) for r in con.execute(
        "select f.id, f.conta, f.estado, f.coletada_em, f.ultimo_erro,"
        " (select count(*) from teams_conversa c where c.conta=f.conta) as conversas from teams_fonte f order by f.conta, f.id")]


def criar(con, conta) -> int:
    """Nova conta, sempre `a_decidir`: nada é lido até o Ricardo liberar."""
    try:
        conta = conta_valida(conta).lower()
    except ErroGoogleOAuth:
        raise ErroFonte("conta deve ser um e-mail válido") from None
    try:
        return con.execute("insert into teams_fonte(conta) values (?)", (conta,)).lastrowid
    except sqlite3.IntegrityError:
        raise ErroFonte("essa conta já está cadastrada", conflito=True) from None


def definir_estado(con, fonte_id: int, estado) -> None:
    if estado not in ESTADOS:
        raise ErroFonte(f"estado deve ser um de {list(ESTADOS)}")
    if con.execute("select 1 from teams_fonte where id=?", (fonte_id,)).fetchone() is None:
        raise ErroFonte("fonte do Teams não existe", nao_encontrado=True)
    con.execute("update teams_fonte set estado=?, ultimo_erro=case when ?='sim' then ultimo_erro else null end where id=?", (estado, estado, fonte_id))
