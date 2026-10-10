"""Entrega dos avisos ao Telegram (G15): DESLIGADA por padrão. Só envia se TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID estiverem no ambiente
(/etc/gabi/telegram.env, colocado pelo Ricardo: é a exceção à R2). Envia o texto em pt-BR do aviso (só nome, valor e datas: nunca CPF, conta ou chave PIX),
no máximo 10 por rodada, só os dos últimos 2 dias e ainda não lidos; marca `telegram_em` somente depois do 200. O token nunca entra na mensagem nem no log.
Uso: python -m gabi.telegram (timer). Consome: aviso, rotas.avisos.descrever."""
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from gabi.db import conectar, migrar

MAX_POR_RODADA = 10
JANELA = dt.timedelta(days=2)


def _http_real(url: str, corpo: dict) -> int:
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return 0


def enviar_avisos(con, env, agora: dt.datetime, http=_http_real) -> int:
    from gabi.rotas.avisos import descrever
    token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return 0
    desde = (agora - JANELA).astimezone(dt.timezone.utc).isoformat()
    enviados = 0
    for r in con.execute("select id, tipo, payload from aviso where telegram_em is null and entregue_em is null and criado_em>=? order by id limit ?", (desde, MAX_POR_RODADA)).fetchall():
        titulo, texto = descrever(r["tipo"], json.loads(r["payload"]))
        if http(f"https://api.telegram.org/bot{token}/sendMessage", {"chat_id": chat, "text": f"{titulo}\n{texto}"}) == 200:
            con.execute("update aviso set telegram_em=? where id=?", (agora.astimezone(dt.timezone.utc).isoformat(), r["id"]))
            enviados += 1
    return enviados


if __name__ == "__main__":
    con = conectar(Path(os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db")))
    migrar(con, Path(__file__).resolve().parent.parent / "migrations")
    n = enviar_avisos(con, os.environ, dt.datetime.now(dt.timezone.utc))
    print("telegram: " + ("desligado (sem TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID)" if not os.environ.get("TELEGRAM_BOT_TOKEN") or not os.environ.get("TELEGRAM_CHAT_ID") else f"{n} aviso(s) enviado(s)"))
    sys.exit(0)
