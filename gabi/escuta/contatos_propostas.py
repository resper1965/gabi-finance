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


def _digitos(t: str) -> str:
    return re.sub(r"\D", "", t or "").lstrip("0")


def _muda_digitos(original: str, e164: str) -> bool:
    """Correção = a normalização muda os DÍGITOS do celular (ex.: celular antigo de 8 dígitos que ganhou o 9), nunca só a formatação
    (espaço, hífen, parênteses, +55, zero de discagem). Compara os dígitos do texto original sem DDI 55 com os do E.164 sem +55."""
    if not e164.startswith("+55"):
        return False
    d = _digitos(original)
    if len(d) > 11 and d.startswith("55"):
        d = d[2:].lstrip("0")
    return d != e164[3:].lstrip("0")


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
        for r in con.execute("select conta, graph_id, nome, telefone_original, telefone from contato_graph where campo='mobile' and telefone is not null "
                             "order by conta, graph_id, telefone_original").fetchall():
            nome, novo = _nome(r["nome"]), r["telefone"]
            if nome is None or not _E164.match(novo) or not _muda_digitos(r["telefone_original"], novo):
                continue
            if con.execute("select 1 from contato_graph where telefone=? and not (conta=? and graph_id=? and telefone_original=?)",
                           (novo, r["conta"], r["graph_id"], r["telefone_original"])).fetchone():
                continue  # outro contato (ou outro campo deste) já tem o número: corrigir criaria duplicata
            corrigir += _inserir(con, agora, "corrigir", r["conta"], r["graph_id"], r["nome"], r["telefone_original"], nome, novo, "telefone_invalido")
    return {"criar": criar, "corrigir": corrigir}


def listar(con, estado: str | None = None) -> list[dict]:
    if estado is None:
        linhas = con.execute("select * from contato_proposta order by id")
    else:
        linhas = con.execute("select * from contato_proposta where estado=? order by id", (estado,))
    return [dict(r) for r in linhas]


MAX_IDS = 2000


def ids_validos(ids) -> list[int]:
    """Lista não vazia de inteiros (bool não conta), no máximo MAX_IDS; senão ErroProposta (400)."""
    if not isinstance(ids, list) or not ids or len(ids) > MAX_IDS or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        raise ErroProposta(f"ids deve ser uma lista de 1 a {MAX_IDS} inteiros")
    return list(dict.fromkeys(ids))


def decidir(con, proposta_id: int, estado: str, login: str, agora: str, auditar=None) -> None:
    """pendente -> aprovada|recusada; aprovada -> recusada (o dono desfaz a aprovação antes da gravação). O resto é terminal (409)."""
    if estado not in ESTADOS_DECISAO:
        raise ErroProposta("Decisão inválida.")
    de = ("pendente",) if estado == "aprovada" else ("pendente", "aprovada")
    with transacao(con):
        r = con.execute("select estado from contato_proposta where id=?", (proposta_id,)).fetchone()
        if r is None:
            raise ErroProposta("Proposta não encontrada.", nao_encontrado=True)
        if r["estado"] not in de:
            raise ErroProposta("A proposta já foi decidida.", conflito=True)
        n = con.execute(f"update contato_proposta set estado=?, decidida_em=?, decidida_por=? where id=? and estado in ({','.join('?' * len(de))})",
                        (estado, agora, login, proposta_id, *de)).rowcount
        if not n:
            raise ErroProposta("A proposta já foi decidida.", conflito=True)
        if auditar is not None:
            auditar()  # dentro da transação: se falhar, a decisão não fica


def aprovar_correcoes(con, login: str, agora: str, ids, auditar=None) -> int:
    """Aprova só as correções pendentes cujos ids o painel mostrou (nunca o que o dono não viu); criar e não pendentes ficam como estão."""
    ids = ids_validos(ids)
    with transacao(con):
        n = con.execute(f"update contato_proposta set estado='aprovada', decidida_em=?, decidida_por=? "
                        f"where id in ({','.join('?' * len(ids))}) and tipo='corrigir' and estado='pendente'", (agora, login, *ids)).rowcount
        if auditar is not None and n:
            auditar(n)  # dentro da transação: se falhar, nada fica aprovado
        return n
