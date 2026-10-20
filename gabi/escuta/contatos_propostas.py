"""Propostas de criar/corrigir contato da ness (sem modelo, depois da sincronização). Nada é escrito aqui: só se gera, lista e decide.
`listar` devolve nome e telefone porque alimenta o painel; nada neste módulo imprime nem registra nome ou número."""
import re

from gabi.db import transacao
from gabi.escuta import contatos

_E164 = re.compile(r"^\+\d{10,15}$")
ESTADOS_DECISAO = ("aprovada", "recusada")


class ErroProposta(ValueError):
    """Pedido inválido (400), inexistente (404) ou em conflito (409), com a mensagem em pt-BR para o painel."""

    def __init__(self, mensagem: str, nao_encontrado: bool = False, conflito: bool = False):
        super().__init__(mensagem)
        self.nao_encontrado, self.conflito = nao_encontrado, conflito


def _nome(v) -> str | None:
    return v.strip()[:200] if isinstance(v, str) and v.strip() else None


def _ja_decidida(con, conta, tipo, graph_id, telefone, nome) -> bool:
    return con.execute("select 1 from contato_proposta where conta=? and tipo=? and graph_id is ? and telefone_depois=? and nome_depois=? "
                       "and estado in ('recusada','aplicada')", (conta, tipo, graph_id, telefone, nome)).fetchone() is not None


def _inserir(con, agora, tipo, conta, graph_id, antes_nome, antes_tel, nome, tel, origem) -> int:
    if _ja_decidida(con, conta, tipo, graph_id, tel, nome):
        return 0
    return con.execute("insert or ignore into contato_proposta(tipo, conta, graph_id, nome_antes, telefone_antes, nome_depois, telefone_depois, origem, criada_em) "
                       "values (?,?,?,?,?,?,?,?,?)", (tipo, conta, graph_id, antes_nome, antes_tel, nome, tel, origem, agora)).rowcount


def gerar(con, agora: str) -> dict:
    criar = corrigir = 0
    conta = contatos.conta_origem(con)
    with transacao(con):
        for r in con.execute("select numero, nome from escuta_remetente where estado='aprovado' and nome is not null and trim(nome)<>'' order by numero").fetchall():
            nome, numero = _nome(r["nome"]), r["numero"]
            if nome is None or not _E164.match(numero or ""):
                continue
            if con.execute("select 1 from contato_graph where telefone=?", (numero,)).fetchone() or \
                    con.execute("select 1 from contato_google where telefone=?", (numero,)).fetchone():
                continue
            criar += _inserir(con, agora, "criar", conta, None, None, None, nome, numero, "whatsapp")
        for r in con.execute("select conta, graph_id, nome, telefone_original from contato_graph where campo='mobile' and telefone is null "
                             "order by conta, graph_id, telefone_original").fetchall():
            nome = _nome(r["nome"])
            novo = contatos._telefone({"telefone": r["telefone_original"]})
            if nome is None or novo is None or not _E164.match(novo):
                continue
            if con.execute("select 1 from contato_graph where conta=? and graph_id=? and telefone=?", (r["conta"], r["graph_id"], novo)).fetchone():
                continue
            corrigir += _inserir(con, agora, "corrigir", r["conta"], r["graph_id"], r["nome"], r["telefone_original"], nome, novo, "telefone_invalido")
    return {"criar": criar, "corrigir": corrigir}


def listar(con, estado: str | None = None) -> list[dict]:
    if estado is None:
        linhas = con.execute("select * from contato_proposta order by id")
    else:
        linhas = con.execute("select * from contato_proposta where estado=? order by id", (estado,))
    return [dict(r) for r in linhas]


def decidir(con, proposta_id: int, estado: str, login: str, agora: str) -> None:
    if estado not in ESTADOS_DECISAO:
        raise ErroProposta("Decisão inválida.")
    with transacao(con):
        r = con.execute("select estado from contato_proposta where id=?", (proposta_id,)).fetchone()
        if r is None:
            raise ErroProposta("Proposta não encontrada.", nao_encontrado=True)
        if r["estado"] != "pendente":
            raise ErroProposta("A proposta já foi decidida.", conflito=True)
        con.execute("update contato_proposta set estado=?, decidida_em=?, decidida_por=? where id=? and estado='pendente'",
                    (estado, agora, login, proposta_id))


def aprovar_correcoes(con, login: str, agora: str) -> int:
    with transacao(con):
        return con.execute("update contato_proposta set estado='aprovada', decidida_em=?, decidida_por=? where tipo='corrigir' and estado='pendente'",
                           (agora, login)).rowcount
