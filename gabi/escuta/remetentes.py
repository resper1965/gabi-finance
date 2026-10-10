"""Lista de aprovados da escuta: quem pode ter mensagem lida. Candidato (tem canal whatsapp, sem escuta_aprovada) NUNCA vale como aprovado.
Aprovação mora em pessoa.dados (escuta_aprovada, papel_escuta); decisões vão para `decisao`. Avisos levam só número e nome, nunca texto."""
import datetime as dt
import hashlib
import json
from pathlib import Path

from gabi.cobrar.cadastro import dados
from gabi.db import transacao

PAPEIS = ("familia", "prestador", "cobranca")


def _agora() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _pessoa_aprovada(con, numero: str):
    canal = f"whatsapp:{numero}"
    for p in con.execute("select id, nome, dados from pessoa where excluido_em is null order by id"):
        d = dados(p)
        if d.get("escuta_aprovada") is True and canal in (d.get("canais") or []):
            return p
    return None


def estado_remetente(con, numero: str) -> tuple[str, str | None]:
    r = con.execute("select estado from escuta_remetente where numero=?", (numero,)).fetchone()
    if r and r["estado"] in ("ignorado", "bloqueado"):
        return r["estado"], None
    p = _pessoa_aprovada(con, numero)
    if p is not None:
        return "aprovado", p["id"]
    return "pendente", None


def _nome_contato(con, numero: str) -> str | None:
    r = con.execute("select nome from contato_google where telefone=? and nome is not null order by conta limit 1", (numero,)).fetchone()
    return r["nome"] if r else None


def fila(con) -> list[dict]:
    return [{"numero": r["numero"], "nome": r["nome"] or _nome_contato(con, r["numero"]), "qtd": r["qtd"]}
            for r in con.execute("select numero, nome, qtd from escuta_remetente where estado='pendente' order by vista_em, numero")]


def _auditar(con, por: str, o_que: str) -> None:
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'escuta')", (_agora(), por, o_que))


def aprovar(con, numero: str, papel: str, nome: str | None, por: str) -> str:
    if papel not in PAPEIS:
        raise ValueError(f"papel inválido: {papel!r}")
    canal = f"whatsapp:{numero}"
    with transacao(con):
        alvo = None
        for p in con.execute("select id, nome, dados from pessoa where excluido_em is null order by id"):
            if canal in (dados(p).get("canais") or []):
                alvo = p
                break
        if alvo is None:
            pid = "wa-" + hashlib.sha1(numero.encode()).hexdigest()[:10]
            nome_final = nome or _nome_contato(con, numero) or numero
            con.execute("insert into pessoa(id, nome, dados, origem) values (?,?,?, 'escuta')", (pid, nome_final, "{}"))
            d = {}
        else:
            pid, d = alvo["id"], dados(alvo)
        canais = list(d.get("canais") or [])
        if canal not in canais:
            canais.append(canal)
        d.update({"canais": canais, "escuta_aprovada": True, "papel_escuta": papel})
        con.execute("update pessoa set dados=? where id=?", (json.dumps(d, ensure_ascii=False), pid))
        con.execute(
            "insert into escuta_remetente(numero, nome, estado, vista_em, qtd) values (?,?, 'aprovado', ?, 0) "
            "on conflict(numero) do update set estado='aprovado', nome=coalesce(?, nome)", (numero, nome, _agora(), nome))
        _auditar(con, por, f"escuta: aprovou {numero} como {papel} (pessoa {pid})")
    return pid


def _descartar(con, numero: str, estado: str, por: str) -> None:
    with transacao(con):
        con.execute(
            "insert into escuta_remetente(numero, estado, vista_em, qtd) values (?,?,?,0) on conflict(numero) do update set estado=excluded.estado",
            (numero, estado, _agora()))
        anexos = [r[0] for r in con.execute("select anexo_caminho from escuta_msg where de=? and anexo_caminho is not null", (numero,))]
        con.execute("update escuta_msg set texto=null, anexo_caminho=null where de=? and estado='retida'", (numero,))
        con.execute("update escuta_msg set anexo_caminho=null where de=?", (numero,))
        _auditar(con, por, f"escuta: {estado} {numero}")
    for a in anexos:
        try:
            Path(a).unlink(missing_ok=True)
        except OSError:
            pass


def ignorar(con, numero: str, por: str) -> None:
    _descartar(con, numero, "ignorado", por)


def bloquear(con, numero: str, por: str) -> None:
    _descartar(con, numero, "bloqueado", por)


def avisar_novo(con, numero: str, agora: str) -> None:
    """Um aviso por número (o primeiro vale). Payload: só número e nome."""
    for r in con.execute("select payload from aviso where tipo='escuta_novo_remetente'"):
        if json.loads(r["payload"]).get("numero") == numero:
            return
    nome = (con.execute("select nome from escuta_remetente where numero=?", (numero,)).fetchone() or {"nome": None})["nome"] or _nome_contato(con, numero)
    con.execute("insert into aviso(tipo, payload, criado_em) values ('escuta_novo_remetente', ?, ?)",
                (json.dumps({"numero": numero, "nome": nome}, ensure_ascii=False), agora))
