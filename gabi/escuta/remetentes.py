"""Lista de aprovados da escuta: quem pode ter mensagem lida. Candidato (tem canal whatsapp, sem escuta_aprovada) NUNCA vale como aprovado.
Aprovação mora em pessoa.dados (escuta_aprovada, papel_escuta); decisões vão para `decisao`. Avisos levam só número e nome, nunca texto."""
import datetime as dt
import hashlib
import json
from pathlib import Path

from gabi.cobrar.cadastro import dados
from gabi.db import transacao
from gabi.escuta import spool_seguro
from gabi.escuta.caixa import normalizar_telefone
from gabi.contatos.contatos import emails_do_numero, nome_do_numero
from gabi.contatos.pessoas import PAPEIS, _aprovada, _casa, _pessoas_do_numero, garantir_pessoa  # noqa: F401



def _agora() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _pessoa_aprovada(con, numero: str):
    for p in _pessoas_do_numero(con, numero):
        if _aprovada(dados(p)):
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
    return nome_do_numero(con, numero)


def fila(con) -> list[dict]:
    """Pendentes, mais os 'aprovado' cuja pessoa deixou de estar aprovada (volta para a fila: nada fica fora das listas)."""
    saida = []
    for r in con.execute("select numero, nome, qtd, estado from escuta_remetente where estado in ('pendente','aprovado') order by vista_em, numero"):
        if r["estado"] == "aprovado" and _pessoa_aprovada(con, r["numero"]) is not None:
            continue
        saida.append({"numero": r["numero"], "nome": r["nome"] or _nome_contato(con, r["numero"]), "qtd": r["qtd"]})
    return saida


def _auditar(con, por: str, o_que: str) -> None:
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'escuta')", (_agora(), por, o_que))


def _canal_email(con, pid: str, d: dict, numero: str) -> list[str]:
    """E-mail do contato do Google com este número (e-mail M4). Um só e-mail distinto: entra como canal `email:` em `d` (o chamador grava).
    Mais de um: devolve a lista para perguntar ao Ricardo (nada é gravado). Dentro da transação do chamador."""
    achados = emails_do_numero(con, numero)
    canais = d.get("canais") if isinstance(d.get("canais"), list) else []
    ja = {c.lower() for c in canais if isinstance(c, str)}
    if len(achados) == 1 and f"email:{achados[0]}" not in ja:
        d["canais"] = canais + [f"email:{achados[0]}"]
    if len(achados) > 1 and not any(f"email:{a}" in ja for a in achados):
        return achados
    return []


def _perguntar_email(con, pid: str, achados: list[str]) -> None:
    """Pergunta pelo canal de decisão qual e-mail vale (uma pergunta aberta por pessoa). Efeito `adicionar_canal_email` (validado em gabi/decisoes.py)."""
    from gabi import decisoes
    for p in con.execute("select opcoes from pergunta where estado='aberta' and tipo='canal_email'"):
        if any((o.get("parametros") or {}).get("pessoa_id") == pid for o in json.loads(p["opcoes"])):
            return
    nome = con.execute("select nome from pessoa where id=?", (pid,)).fetchone()["nome"]
    opcoes = [{"n": i, "rotulo": a, "efeito": "adicionar_canal_email", "parametros": {"pessoa_id": pid, "email": a}} for i, a in enumerate(achados, 1)]
    opcoes.append({"n": len(opcoes) + 1, "rotulo": "Nenhum deles (não ligar e-mail a essa pessoa)", "efeito": "registrar_nota"})
    decisoes.criar_pergunta(con, "canal_email", f"Qual e-mail é de {nome}?", "Os contatos do Google trazem mais de um e-mail para o telefone que você aprovou. O escolhido passa a identificar essa pessoa no e-mail (proteção contra lixeira e fila de contatos).",
                            opcoes, "escuta", _agora())


def aprovar(con, numero: str, papel: str, nome: str | None, por: str) -> str:
    """Decisão explícita do Ricardo: pode reverter ignorado/bloqueado. Reaproveita a pessoa que já tem o número (a aprovada primeiro)."""
    if papel not in PAPEIS:
        raise ValueError(f"papel inválido: {papel!r}")
    with transacao(con):
        pid, d, _ = garantir_pessoa(con, numero, nome)
        d.update({"escuta_aprovada": True, "papel_escuta": papel})
        a_perguntar = _canal_email(con, pid, d, numero)
        con.execute("update pessoa set dados=? where id=?", (json.dumps(d, ensure_ascii=False), pid))
        con.execute(
            "insert into escuta_remetente(numero, nome, estado, vista_em, qtd) values (?,?, 'aprovado', ?, 0) "
            "on conflict(numero) do update set estado='aprovado', nome=coalesce(?, nome)", (numero, nome, _agora(), nome))
        _auditar(con, por, f"escuta: aprovou {numero} como {papel} (pessoa {pid})")
    if a_perguntar:
        _perguntar_email(con, pid, a_perguntar)
    return pid


def _descartar(con, numero: str, estado: str, por: str, spool: Path | None) -> None:
    anexos: list[str] = []
    with transacao(con):
        atual = con.execute("select estado from escuta_remetente where numero=?", (numero,)).fetchone()
        if estado == "ignorado" and atual and atual["estado"] == "bloqueado":
            return  # ignorar nunca rebaixa um bloqueio
        con.execute(
            "insert into escuta_remetente(numero, estado, vista_em, qtd) values (?,?,?,0) on conflict(numero) do update set estado=excluded.estado",
            (numero, estado, _agora()))
        for p in _pessoas_do_numero(con, numero):  # quem lê `pessoa` direto não pode ver este número como aprovado
            d = dados(p)
            if d.get("escuta_aprovada") is not False:
                d["escuta_aprovada"] = False
                con.execute("update pessoa set dados=? where id=?", (json.dumps(d, ensure_ascii=False), p["id"]))
        anexos = [r[0] for r in con.execute("select anexo_caminho from escuta_msg where de=? and anexo_caminho is not null", (numero,))]
        con.execute("update escuta_msg set texto=null where de=? and (estado='retida' or tipo='crise')", (numero,))
        con.execute("update escuta_msg set anexo_caminho=null where de=?", (numero,))
        _auditar(con, por, f"escuta: {estado} {numero}")
    if spool is not None:  # só apaga arquivo dentro da pasta do spool; caminho vindo do banco não é confiável
        for a in anexos:
            spool_seguro.apagar_anexo(spool, a)  # só <spool>/anexos/<nome>, via descritor de diretório


def ignorar(con, numero: str, por: str, spool: Path | None = None) -> None:
    _descartar(con, numero, "ignorado", por, spool)


def bloquear(con, numero: str, por: str, spool: Path | None = None) -> None:
    _descartar(con, numero, "bloqueado", por, spool)


def avisar_novo(con, numero: str, agora: str) -> None:
    """Um aviso por número (o primeiro vale). Payload: só número e nome."""
    for r in con.execute("select payload from aviso where tipo='escuta_novo_remetente'"):
        if json.loads(r["payload"]).get("numero") == numero:
            return
    nome = (con.execute("select nome from escuta_remetente where numero=?", (numero,)).fetchone() or {"nome": None})["nome"] or _nome_contato(con, numero)
    con.execute("insert into aviso(tipo, payload, criado_em) values ('escuta_novo_remetente', ?, ?)",
                (json.dumps({"numero": numero, "nome": nome}, ensure_ascii=False), agora))
