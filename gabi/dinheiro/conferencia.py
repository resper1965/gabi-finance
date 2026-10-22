"""Conferência de uma rodada de captura (ADR-023, substitui as heurísticas do ADR-009): SÓ INFORMA, não trava o `dados_ate`.
A rodada vale (`conferida=1`) quando terminou ok e sem aviso. Por conta bancária fica uma linha `saldo_final`: a variação do saldo entre o último
fechamento de dia e o atual comparada à soma dos lançamentos postados. Divergência vira o aviso `saldo_divergente` (avisos.py), nunca bloqueio."""
from dataclasses import dataclass

TOLERANCIA_SALDO = 1  # centavos: rendimento/arredondamento do banco move o saldo sem lançamento (Bradesco, 21/10/2026)


@dataclass(frozen=True)
class Conferencia:
    tipo: str
    conta_id: int
    ok: bool
    detalhe: str


def _saldo_final(con, conta_id: int, tipo: str) -> tuple[bool, str]:
    if tipo == "CREDIT":
        return True, "cartão: sem conferência de saldo"
    snaps = con.execute("select em, saldo_centavos from saldo where conta_id=? order by em", (conta_id,)).fetchall()
    if not snaps:
        return True, "sem base (nenhum saldo registrado)"
    atual = snaps[-1]
    dia = atual["em"][:10]
    anteriores = [s for s in snaps if s["em"][:10] < dia]
    if not anteriores:
        return True, "sem base (menos de 2 dias de saldo)"
    base = anteriores[-1]
    esperado = con.execute(
        "select coalesce(sum(valor_centavos),0) from lancamento where conta_id=? and status='posted' and data>? and data<=?",
        (conta_id, base["em"][:10], dia)).fetchone()[0]
    variacao = atual["saldo_centavos"] - base["saldo_centavos"]
    dif = variacao - esperado
    if dif == 0:
        return True, f"variação do saldo {variacao} = lançamentos {esperado} (centavos)"
    if abs(dif) <= TOLERANCIA_SALDO:
        return True, f"diferença de {dif} centavo(s) tratada como arredondamento"
    return False, f"variação do saldo {variacao} ≠ lançamentos {esperado}: diferença de {dif} centavos"


def conferir(con, rodada_id: int, conta_id: int, hoje) -> list[Conferencia]:
    """`hoje` fica na assinatura por compatibilidade com quem chama (rodar.py)."""
    tipo = con.execute("select tipo from conta where id=?", (conta_id,)).fetchone()["tipo"]
    ok, detalhe = _saldo_final(con, conta_id, tipo)
    con.execute("delete from conferencia where rodada_id=? and conta_id=?", (rodada_id, conta_id))
    con.execute("insert into conferencia(rodada_id, tipo, conta_id, ok, detalhe, criado_em) values (?, 'saldo_final', ?, ?, ?, datetime('now'))",
                (rodada_id, conta_id, int(ok), detalhe))
    return [Conferencia("saldo_final", conta_id, ok, detalhe)]


def marcar_conferida(con, rodada_id: int) -> bool:
    """True (e `conferida=1`) quando a rodada terminou ok e sem aviso; as conferências não decidem (ADR-023)."""
    r = con.execute("select status, erro from rodada where id=?", (rodada_id,)).fetchone()
    if r is None or r["status"] != "ok" or r["erro"]:
        return False
    con.execute("update rodada set conferida=1 where id=?", (rodada_id,))
    return True
