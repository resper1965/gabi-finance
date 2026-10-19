"""Motor de sincronização da agenda (spec 2026-10-11-agenda-design, §3.5 e §3.8). Só lê; quem fala com o Google é a ponte (`listar`).
Uma transação por fonte: o `syncToken` só troca depois que todas as páginas vieram e os eventos foram gravados; falha não altera linha nenhuma.
Nenhum texto de evento (título) entra em exceção, log ou aviso."""
import datetime as dt
import json
import re
from typing import Callable

from gabi.agenda import tempo
from gabi.avisos import _novo
from gabi.db import transacao
from gabi.fontes.google_oauth import ErroGoogleOAuth
from gabi.fontes.graph_ness import ErroGraphNess

RECARGA_DIAS = 7
CREDENCIAL = re.compile(r"-> 401\b|invalid_grant|não autorizada|token recusado")
SO_STATUS_403 = re.compile(r"-> 403$")  # 403 sem motivo também é cota/API desligada: só vira "reconectar" na 2ª falha seguida
PRIVADO = "Compromisso privado"


def _parametro(con, chave: str, padrao):
    r = con.execute("select valor from parametro where chave=?", (chave,)).fetchone()
    try:
        return json.loads(r[0]) if r else padrao
    except (ValueError, TypeError):
        return padrao


def _dias(con, chave: str, padrao: int) -> int:
    v = _parametro(con, chave, padrao)
    return v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 3650 else padrao


def _agora(agora: str) -> dt.datetime:
    d = dt.datetime.fromisoformat(agora)
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def _janela(con, agora: dt.datetime, fuso: str) -> dict:
    """{"de","ate"} em UTC: da meia-noite local de (hoje − passado) à de (hoje + futuro + 1)."""
    hoje = agora.astimezone(tempo._zona(fuso)).date()
    passado = _dias(con, "agenda.janela_passado_dias", 7)
    futuro = _dias(con, "agenda.janela_futuro_dias", 90)
    zona = tempo._zona(fuso)
    de = dt.datetime.combine(hoje - dt.timedelta(days=passado), dt.time(0, 0), zona)
    ate = dt.datetime.combine(hoje + dt.timedelta(days=futuro + 1), dt.time(0, 0), zona)
    return {"de": tempo._iso(de), "ate": tempo._iso(ate)}


def _precisa_recarga(f, agora: dt.datetime) -> bool:
    if not f["sync_token"] or not f["recarga_em"]:
        return True
    try:
        return agora - _agora(f["recarga_em"]) > dt.timedelta(days=RECARGA_DIAS)
    except ValueError:
        return True


def sincronizar_fonte(con, fonte_id: int, listar: Callable, agora: str) -> dict:
    """{lidos, gravados, apagados, pulados, recarga}; levanta o erro tipado do cliente sem tocar nas linhas da fonte."""
    f = con.execute("select * from agenda_fonte where id=?", (fonte_id,)).fetchone()
    now = _agora(agora)
    fuso = _parametro(con, "agenda.fuso", "America/Sao_Paulo")
    ocultar = _parametro(con, "agenda.privados", "mostrar") == "ocultar"
    completa = _precisa_recarga(f, now)
    res = listar(f["conta"], f["calendario_id"], None if completa else f["sync_token"], _janela(con, now, fuso))
    completa = completa or bool(res.recarga_completa)
    if completa and not res.eventos and not res.cancelados and con.execute("select 1 from agenda_evento where fonte_id=?", (fonte_id,)).fetchone():
        # recarga que volta vazia numa fonte com eventos é mais provável erro do que calendário esvaziado: nada é apagado, o token e a data da recarga ficam, tenta de novo na próxima
        con.execute("update agenda_fonte set ultimo_erro=? where id=?", ("recarga vazia: eventos mantidos", fonte_id))
        return {"lidos": 0, "gravados": 0, "apagados": 0, "pulados": 0, "recarga": False}
    linhas, pulados = [], 0
    for e in res.eventos:
        try:
            j = tempo.de_google(e.get("inicio"), e.get("fim"), fuso)
        except (ValueError, AttributeError):
            pulados += 1
            continue
        titulo = PRIVADO if (ocultar and e.get("privado")) else e.get("titulo")
        linhas.append((fonte_id, e["externo_id"], j.inicio_utc, j.fim_utc, j.dia_local, j.dia_fim_local, int(j.dia_inteiro), titulo,
                       e.get("link_reuniao"), int(e.get("participantes_qtd") or 0), e.get("status"), e.get("etag"),
                       e.get("atualizado_origem"), int(bool(e.get("privado"))), e.get("ical_uid"), int(bool(e.get("livre")))))
    apagados = 0
    with transacao(con, imediata=True):
        con.executemany(
            "insert into agenda_evento(fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local, dia_inteiro, titulo, link_reuniao,"
            " participantes_qtd, status, etag, atualizado_origem, privado, ical_uid, livre) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " on conflict(fonte_id, externo_id) do update set inicio_utc=excluded.inicio_utc, fim_utc=excluded.fim_utc,"
            " dia_local=excluded.dia_local, dia_fim_local=excluded.dia_fim_local, dia_inteiro=excluded.dia_inteiro, titulo=excluded.titulo,"
            " link_reuniao=excluded.link_reuniao, participantes_qtd=excluded.participantes_qtd, status=excluded.status, etag=excluded.etag,"
            " atualizado_origem=excluded.atualizado_origem, privado=excluded.privado, ical_uid=excluded.ical_uid, livre=excluded.livre", linhas)
        for ext in res.cancelados:
            apagados += con.execute("delete from agenda_evento where fonte_id=? and externo_id=?", (fonte_id, ext)).rowcount
        if completa:  # a janela desliza: o que não veio na recarga (sumiu, ou saiu da janela) é apagado
            vivos = {ln[1] for ln in linhas}
            for (ext,) in con.execute("select externo_id from agenda_evento where fonte_id=?", (fonte_id,)).fetchall():
                if ext not in vivos:
                    apagados += con.execute("delete from agenda_evento where fonte_id=? and externo_id=?", (fonte_id, ext)).rowcount
        token = res.novo_sync_token if (completa or res.novo_sync_token) else f["sync_token"]
        con.execute("update agenda_fonte set sync_token=?, sincronizada_em=?, recarga_em=?, ultimo_erro=null where id=?",
                    (token, agora, agora if completa else f["recarga_em"], fonte_id))
    return {"lidos": len(res.eventos) + len(res.cancelados), "gravados": len(linhas), "apagados": apagados, "pulados": pulados, "recarga": completa}


def _fechar_aviso(con, conta: str, agora: str) -> None:
    con.execute("update aviso set entregue_em=? where tipo='agenda_reconectar' and entregue_em is null and json_extract(payload,'$.chave')=?",
                (_agora(agora).astimezone(dt.timezone.utc).isoformat(), conta))


def sincronizar(con, listar: Callable, agora: str, *, listar_graph: Callable | None = None) -> dict:
    """Por fonte com estado='sim': {fonte_id: resultado | {"erro": msg}}. Uma fonte que falha não derruba as outras nem muda suas linhas.
    `listar` lê as fontes do Google; `listar_graph` (mesma assinatura) as da Microsoft (ness)."""
    saida = {}
    for f in con.execute("select id, conta, provedor, auth from agenda_fonte where estado='sim' order by id").fetchall():
        cliente = {"google": listar, "graph": listar_graph}.get(f["provedor"])
        if cliente is None:
            saida[f["id"]] = {"erro": "provedor sem cliente ainda"}
            continue
        if f["auth"] != "oauth":  # `delegacao` ainda não tem cliente: não tenta o OAuth da conta por engano
            saida[f["id"]] = {"erro": "autenticação por delegação sem cliente ainda"}
            continue
        try:
            saida[f["id"]] = sincronizar_fonte(con, f["id"], cliente, agora)
        except Exception as ex:  # noqa: BLE001 - uma fonte nunca derruba as outras; só texto tipado do cliente entra no erro, de resto só o nome da classe
            msg = str(ex) if isinstance(ex, (ErroGoogleOAuth, ErroGraphNess)) else type(ex).__name__
            anterior = con.execute("select ultimo_erro from agenda_fonte where id=?", (f["id"],)).fetchone()[0]
            saida[f["id"]] = {"erro": msg}
            con.execute("update agenda_fonte set ultimo_erro=? where id=?", (msg, f["id"]))
            if CREDENCIAL.search(msg) or (SO_STATUS_403.search(msg) and anterior == msg):
                _novo(con, _agora(agora), "agenda_reconectar", f["conta"], {"conta": f["conta"]})
            continue
        _fechar_aviso(con, f["conta"], agora)
    return saida
