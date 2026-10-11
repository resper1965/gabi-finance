"""Sincronização do correio (spec 2026-10-11-email-design, §3.4). Só lê; quem fala com o Gmail é a ponte (`listar`).
Uma transação por fonte: o `history_id` só troca depois que a leitura inteira terminou e as mensagens foram gravadas; falha deixa tudo como estava.
Reler uma mensagem nunca a reabre nem a reclassifica (`insert or ignore`). Nenhum texto de e-mail em exceção, log ou aviso."""
import datetime as dt
import re
from typing import Callable

from gabi.avisos import _novo
from gabi.correio.regras import endereco
from gabi.db import transacao
from gabi.fontes.google_oauth import ErroGoogleOAuth

RECARGA_DIAS = 7
JANELA_PADRAO = 14
CREDENCIAL = re.compile(r"-> (401|403)\b|invalid_grant|não autorizada|token recusado")
SENTINELA = ""  # linha de `email_respondido` que marca "já conferi quem o dono respondeu nesta conta" (lista vazia também vale)


def _parametro(con, chave: str, padrao):
    import json
    r = con.execute("select valor from parametro where chave=?", (chave,)).fetchone()
    try:
        return json.loads(r[0]) if r else padrao
    except (ValueError, TypeError):
        return padrao


def _agora(agora: str) -> dt.datetime:
    d = dt.datetime.fromisoformat(agora)
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def _janela_dias(con) -> int:
    v = _parametro(con, "email.janela_dias", JANELA_PADRAO)
    return v if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 60 else JANELA_PADRAO


def _precisa_recarga(f, agora: dt.datetime) -> bool:
    if not f["history_id"] or not f["recarga_em"]:
        return True
    try:
        return agora - _agora(f["recarga_em"]) > dt.timedelta(days=RECARGA_DIAS)
    except ValueError:
        return True


def _valida(m) -> bool:
    return (isinstance(m, dict) and isinstance(m.get("externo_id"), str) and bool(m["externo_id"])
            and isinstance(m.get("recebida_em"), str) and bool(m["recebida_em"]))


def sincronizar_fonte(con, fonte_id: int, listar: Callable, agora: str) -> dict:
    """{lidos, novos, pulados, recarga}; levanta o erro tipado do cliente sem tocar nas linhas da fonte."""
    f = con.execute("select * from email_fonte where id=?", (fonte_id,)).fetchone()
    now = _agora(agora)
    completa = _precisa_recarga(f, now)
    res = listar(f["conta"], None if completa else f["history_id"], _janela_dias(con))
    completa = completa or bool(res.recarga_completa)
    validas = [m for m in res.mensagens if _valida(m)]
    novos = 0
    with transacao(con, imediata=True):
        for m in validas:
            novos += con.execute(
                "insert or ignore into email_msg(fonte_id, externo_id, thread_id, remetente, assunto, recebida_em, trecho, lista, atualizado_em)"
                " values (?,?,?,?,?,?,?,?,?)",
                (fonte_id, m["externo_id"], m.get("thread_id") or m["externo_id"], m.get("remetente") or "", m.get("assunto") or "",
                 m["recebida_em"], m.get("trecho") or "", int(bool(m.get("lista"))), agora)).rowcount
        con.execute("update email_fonte set history_id=?, sincronizada_em=?, recarga_em=?, ultimo_erro=null where id=?",
                    (res.novo_history_id or f["history_id"], agora, agora if completa else f["recarga_em"], fonte_id))
    return {"lidos": len(res.mensagens), "novos": novos, "pulados": len(res.mensagens) - len(validas), "recarga": completa}


def _fechar_aviso(con, conta: str, agora: str) -> None:
    con.execute("update aviso set entregue_em=? where tipo='email_reconectar' and entregue_em is null and json_extract(payload,'$.chave')=?",
                (_agora(agora).astimezone(dt.timezone.utc).isoformat(), conta))


def sincronizar(con, listar: Callable, agora: str) -> dict:
    """Por fonte com estado='sim': {fonte_id: resultado | {"erro": msg}}. Uma fonte que falha não derruba as outras nem muda suas linhas.
    Credencial recusada → aviso `email_reconectar` (1 por dia, fecha sozinho quando a conta volta)."""
    saida = {}
    for f in con.execute("select id, conta, provedor from email_fonte where estado='sim' order by id").fetchall():
        if f["provedor"] != "google":
            saida[f["id"]] = {"erro": "provedor sem cliente ainda"}
            continue
        try:
            saida[f["id"]] = sincronizar_fonte(con, f["id"], listar, agora)
        except Exception as ex:  # noqa: BLE001 - uma fonte nunca derruba as outras; só texto tipado do cliente entra no erro, de resto só o nome da classe
            msg = str(ex) if isinstance(ex, ErroGoogleOAuth) else type(ex).__name__
            saida[f["id"]] = {"erro": msg}
            con.execute("update email_fonte set ultimo_erro=? where id=?", (msg, f["id"]))
            if CREDENCIAL.search(msg):
                _novo(con, _agora(agora), "email_reconectar", f["conta"], {"conta": f["conta"]})
            continue
        _fechar_aviso(con, f["conta"], agora)
    return saida


def atualizar_respondidos(con, fonte_id: int, enviados: list, agora: str) -> int:
    """Grava os endereços que o dono já respondeu (To/Cc dos enviados) e a marca de conferência. Devolve quantos endereços válidos entraram."""
    enderecos = {a for x in enviados if (a := endereco(x))}
    with transacao(con, imediata=True):
        for a in sorted(enderecos) + [SENTINELA]:
            con.execute("insert into email_respondido(fonte_id, endereco, em) values (?,?,?) on conflict(fonte_id, endereco) do update set em=excluded.em",
                        (fonte_id, a, agora))
    return len(enderecos)


def respondidos_prontos(con, fonte_id: int) -> bool:
    """Já conferi quem o dono respondeu nesta conta? Sem isso nada é movido para a lixeira (a proteção de 'já respondi' não existiria)."""
    return con.execute("select 1 from email_respondido where fonte_id=? and endereco=?", (fonte_id, SENTINELA)).fetchone() is not None
