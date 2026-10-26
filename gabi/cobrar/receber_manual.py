"""A receber manual: valor que o Ricardo diz no chat (ou no painel) que vai receber, fora das notas. Consome: dinheiro.valor, db, cobrar.util."""
import datetime as dt
import re

from gabi.db import transacao
from gabi.dinheiro.valor import para_centavos

LIMITE_CENTAVOS = 10_000_000 * 100


class ErroReceber(Exception):
    """Falha de regra com código estável: valor_invalido, nao_encontrado ou conflito."""

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


def _utc(agora: dt.datetime) -> str:
    return (agora if agora.tzinfo else agora.replace(tzinfo=dt.timezone.utc)).astimezone(dt.timezone.utc).isoformat()


def valor_ditado(v: str) -> int:
    """Centavos de um valor ditado. "1.500" (um ponto e 3 dígitos) é ambíguo (para_centavos leria R$ 1,50): valor_invalido.
    Zero e módulo acima de R$ 10.000.000,00 também. Negativo vale (desconto ou adiantamento)."""
    s = re.sub(r"^(R\$|BRL)\s*", "", str(v or "").strip(), flags=re.I).strip()
    if re.fullmatch(r"-?\d{1,3}\.\d{3}", s):
        raise ErroReceber("valor_invalido", "valor ambíguo: use vírgula nos centavos (1500,00)")
    try:
        c = para_centavos(v)
    except ValueError as e:
        raise ErroReceber("valor_invalido", str(e)) from e
    if not c or abs(c) > LIMITE_CENTAVOS:
        raise ErroReceber("valor_invalido", "valor zero, vazio ou acima de R$ 10.000.000,00")
    return c


def _vencimento(v: str) -> str | None:
    v = (v or "").strip()
    if not v:
        return None
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError(v)
        return dt.date.fromisoformat(v).isoformat()
    except ValueError as e:
        raise ErroReceber("valor_invalido", "vencimento deve ser AAAA-MM-DD") from e


def registrar(con, *, pagador: str, valor: str, vencimento: str = "", conta: str = "", observacao: str = "",
              quem: str, origem: str, agora: dt.datetime) -> dict:
    """Grava um a receber aberto e uma decisao só com o id. Vencimento, conta e observação vazios viram NULL."""
    pagador = (pagador or "").strip()
    if not pagador:
        raise ErroReceber("valor_invalido", "pagador vazio")
    centavos = valor_ditado(valor)
    venc = _vencimento(vencimento)
    t = _utc(agora)
    with transacao(con, imediata=True):
        rid = con.execute(
            "insert into receber_manual(pagador, valor_centavos, vencimento, conta, observacao, criado_em, quem, atualizado_em) values (?,?,?,?,?,?,?,?)",
            (pagador, centavos, venc, (conta or "").strip() or None, (observacao or "").strip() or None, t, quem, t)).lastrowid
        con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?,?)", (t, quem, f"a receber manual {rid} registrado", origem))
    return dict(con.execute("select * from receber_manual where id=?", (rid,)).fetchone())


def cancelar(con, rid: int, *, quem: str, origem: str, agora: dt.datetime) -> dict:
    """aberto vira cancelado e as propostas 'proposto' dele viram 'rejeitado'. Outro estado: conflito; id inexistente: nao_encontrado."""
    t = _utc(agora)
    with transacao(con, imediata=True):
        r = con.execute("select estado from receber_manual where id=?", (rid,)).fetchone()
        if r is None:
            raise ErroReceber("nao_encontrado", f"a receber {rid} não existe")
        if r["estado"] != "aberto":
            raise ErroReceber("conflito", f"a receber {rid} está {r['estado']}")
        con.execute("update receber_manual set estado='cancelado', atualizado_em=? where id=?", (t, rid))
        con.execute("update receber_manual_proposta set estado='rejeitado' where receber_id=? and estado='proposto'", (rid,))
        con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?,?)", (t, quem, f"a receber manual {rid} cancelado", origem))
    return dict(con.execute("select * from receber_manual where id=?", (rid,)).fetchone())
