"""A receber manual: valor que o Ricardo diz no chat (ou no painel) que vai receber, fora das notas. Consome: dinheiro.valor, db, cobrar.util, cobrar.recebimentos (_norm).

Casamento com o extrato (`propor`): só propõe (estado `proposto`); confirmar ou rejeitar é do Ricardo. Mesmo pagador (até 2 primeiras palavras com 3+ letras no descritivo),
valor a ±1% do registrado, janela de 30 dias antes a 90 depois da base (vencimento, ou o dia de criação). Confiança 0,7; +0,3 se o valor bate ao centavo."""
import datetime as dt
import re

from gabi.cobrar.recebimentos import _norm
from gabi.cobrar.util import agora as _agora
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


JANELA_ANTES, JANELA_DEPOIS = 30, 90


def _confianca(valor: int, l) -> tuple[float, str]:
    if l["valor_centavos"] == valor:
        return 1.0, "valor igual ao a receber, pagador no descritivo"
    return 0.7, "valor a até 1% do a receber, pagador no descritivo"


def propor(con) -> int:
    """Quantas propostas novas. Não propõe para valor negativo, nem para a receber que não está aberto, nem com crédito já confirmado (nota ou manual)."""
    novas = 0
    abertos = con.execute("select * from receber_manual where estado='aberto' and valor_centavos>0").fetchall()
    with transacao(con):
        for r in abertos:
            toks = [t for t in _norm(r["pagador"]).split() if len(t) >= 3][:2]
            if not toks:
                continue
            base = dt.date.fromisoformat(r["vencimento"] or r["criado_em"][:10])
            ini, fim = (base - dt.timedelta(days=JANELA_ANTES)).isoformat(), (base + dt.timedelta(days=JANELA_DEPOIS)).isoformat()
            v = r["valor_centavos"]
            for l in con.execute(
                    "select l.* from lancamento l join conta c on c.id=l.conta_id where c.tipo='BANK' and c.estado='sim' and c.excluido_em is null "
                    "and l.valor_centavos>0 and l.data>=? and l.data<=? "
                    "and not exists (select 1 from recebimento_nota n where n.lancamento_id=l.id and n.estado='confirmado') "
                    "and not exists (select 1 from receber_manual_proposta p where p.lancamento_id=l.id and p.estado='confirmado') "
                    "and not exists (select 1 from receber_manual m where m.lancamento_id=l.id)", (ini, fim)).fetchall():
                if abs(l["valor_centavos"] - v) * 100 > v:
                    continue
                desc = _norm(l["descricao_original"])
                if not all(t in desc for t in toks):
                    continue
                conf, motivo = _confianca(v, l)
                novas += con.execute("insert or ignore into receber_manual_proposta(receber_id, lancamento_id, confianca, motivo, criado_em) values (?,?,?,?,?)",
                                     (r["id"], l["id"], conf, motivo, _agora())).rowcount
    return novas


def _proposta(con, pid: int):
    p = con.execute("select * from receber_manual_proposta where id=?", (pid,)).fetchone()
    if p is None:
        raise LookupError(f"proposta {pid} não existe")
    if p["estado"] != "proposto":
        raise ValueError(f"proposta {pid} já foi {p['estado']}")
    return p


def confirmar(con, pid: int, por: str) -> None:
    """Confirma: o a receber vira `recebido` com o lançamento; as outras propostas do mesmo a receber ou do mesmo crédito viram `rejeitado`."""
    with transacao(con):
        p = _proposta(con, pid)
        con.execute("update receber_manual_proposta set estado='confirmado' where id=?", (pid,))
        con.execute("update receber_manual_proposta set estado='rejeitado' where estado='proposto' and id<>? and (receber_id=? or lancamento_id=?)",
                    (pid, p["receber_id"], p["lancamento_id"]))
        con.execute("update receber_manual set estado='recebido', lancamento_id=?, atualizado_em=? where id=?", (p["lancamento_id"], _agora(), p["receber_id"]))
        con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'cobrar')",
                    (_agora(), por, f"a receber manual: proposta {pid} confirmada (receber {p['receber_id']}, lançamento {p['lancamento_id']})"))


def rejeitar(con, pid: int, por: str) -> None:
    with transacao(con):
        _proposta(con, pid)
        con.execute("update receber_manual_proposta set estado='rejeitado' where id=?", (pid,))
        con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'cobrar')", (_agora(), por, f"a receber manual: proposta {pid} rejeitada"))
