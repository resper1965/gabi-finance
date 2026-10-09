"""Vínculo de comprovantes (Paperless) a lançamentos: o app PROPÕE com confiança e motivo; só o Ricardo confirma (R1).
Casa por valor idêntico (saída) e data em ±3 dias; CNPJ no descritivo e data exata aumentam a confiança. Consome: db (comprovante, lancamento)."""
import datetime as dt
import re
from dataclasses import dataclass

from gabi.db import transacao

JANELA_DIAS = 3
BASE, BONUS_DATA_EXATA, BONUS_CNPJ = 0.5, 0.3, 0.2


@dataclass(frozen=True)
class Vinculo:
    id: int
    comprovante_id: int
    lancamento_id: int
    confianca: float
    motivo: str
    estado: str


def _agora() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _brl(centavos: int) -> str:
    return f"R$ {centavos // 100:,}".replace(",", ".") + f",{centavos % 100:02d}"


def registrar_comprovante(con, *, paperless_id: int, tipo: str, valor_centavos: int, data: str, cnpj: str | None = None,
                          pessoa_id: str | None = None) -> int:
    """Grava o comprovante (idempotente por paperless_id) e devolve o id."""
    con.execute("insert or ignore into comprovante(paperless_id, tipo, valor_centavos, data, cnpj, pessoa_id) values (?,?,?,?,?,?)",
                (paperless_id, tipo, valor_centavos, data, cnpj, pessoa_id))
    return con.execute("select id from comprovante where paperless_id=?", (paperless_id,)).fetchone()[0]


def propor_vinculos(con, comprovante_id: int) -> list[Vinculo]:
    """Propõe (estado `proposto`) os lançamentos de saída com o mesmo valor, ±3 dias, sem comprovante já confirmado. Tudo ou nada."""
    with transacao(con):
        return _propor(con, comprovante_id)


def _propor(con, comprovante_id: int) -> list[Vinculo]:
    c = con.execute("select * from comprovante where id=?", (comprovante_id,)).fetchone()
    if c is None:
        raise LookupError(f"comprovante {comprovante_id} não existe")
    dia = dt.date.fromisoformat(c["data"][:10])
    de, ate = (dia - dt.timedelta(days=JANELA_DIAS)).isoformat(), (dia + dt.timedelta(days=JANELA_DIAS)).isoformat()
    for l in con.execute(
            "select * from lancamento l where l.valor_centavos=? and l.data>=? and l.data<=? and not exists ("
            "  select 1 from comprovante_vinculo v where v.lancamento_id=l.id and v.estado='confirmado') order by l.data, l.id",
            (-c["valor_centavos"], de, ate)).fetchall():
        dist = abs((dt.date.fromisoformat(l["data"][:10]) - dia).days)
        conf, partes = BASE, [f"valor igual {_brl(c['valor_centavos'])}", f"data {'exata' if dist == 0 else f'a {dist} dia(s)'}"]
        if dist == 0:
            conf += BONUS_DATA_EXATA
        if c["cnpj"] and c["cnpj"] in re.sub(r"\D", "", l["descricao_original"] or ""):
            conf += BONUS_CNPJ
            partes.append("CNPJ do comprovante no descritivo")
        con.execute("insert or ignore into comprovante_vinculo(comprovante_id, lancamento_id, confianca, motivo, criado_em) values (?,?,?,?,?)",
                    (comprovante_id, l["id"], round(min(conf, 1.0), 2), ", ".join(partes), _agora()))
    return [Vinculo(r["id"], r["comprovante_id"], r["lancamento_id"], r["confianca"], r["motivo"], r["estado"])
            for r in con.execute("select * from comprovante_vinculo where comprovante_id=? and estado='proposto' order by id", (comprovante_id,))]


def _decidir(con, vinculo_id: int, estado: str, por: str) -> None:
    with transacao(con):
        _decidir_tx(con, vinculo_id, estado, por)


def _decidir_tx(con, vinculo_id: int, estado: str, por: str) -> None:
    v = con.execute("select * from comprovante_vinculo where id=?", (vinculo_id,)).fetchone()
    if v is None:
        raise LookupError(f"vínculo {vinculo_id} não existe")
    if v["estado"] != "proposto":
        raise ValueError(f"vínculo {vinculo_id} já foi {v['estado']}")
    con.execute("update comprovante_vinculo set estado=?, decidido_em=?, decidido_por=? where id=?", (estado, _agora(), por, vinculo_id))
    if estado == "confirmado":  # um comprovante casa com um lançamento e um lançamento tem um comprovante: as outras propostas saem
        con.execute("update comprovante_vinculo set estado='rejeitado', decidido_em=?, decidido_por='auto: outro vínculo foi confirmado' "
                    "where estado='proposto' and id<>? and (comprovante_id=? or lancamento_id=?)", (_agora(), vinculo_id, v["comprovante_id"], v["lancamento_id"]))
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'cobrar')",
                (_agora(), por, f"vínculo {vinculo_id} (comprovante {v['comprovante_id']} ↔ lançamento {v['lancamento_id']}) {estado}"))


def confirmar(con, vinculo_id: int, por: str) -> None:
    _decidir(con, vinculo_id, "confirmado", por)


def rejeitar(con, vinculo_id: int, por: str) -> None:
    _decidir(con, vinculo_id, "rejeitado", por)


def sem_comprovante(con, desde: dt.date) -> list[dict]:
    """Saídas de empresa (empresa_id definido) desde `desde` que ainda não têm comprovante confirmado."""
    return [dict(r) for r in con.execute(
        "select l.id, l.data, l.valor_centavos, l.descricao_original, l.empresa_id from lancamento l "
        "where l.valor_centavos<0 and l.empresa_id is not null and l.data>=? and not exists ("
        "  select 1 from comprovante_vinculo v where v.lancamento_id=l.id and v.estado='confirmado') order by l.data, l.id", (desde.isoformat(),))]
