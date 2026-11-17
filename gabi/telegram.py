"""Entrega dos avisos ao Telegram (G15): DESLIGADA por padrão. Só envia se TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID estiverem no ambiente
(/etc/gabi/telegram.env, colocado pelo Ricardo: é a exceção à R2). Envia o texto em pt-BR do aviso (só nome, valor e datas: nunca CPF, conta ou chave PIX),
no máximo 10 por rodada, só os dos últimos 2 dias e ainda não lidos, em ordem de criação; marca `telegram_em` somente depois do 200. Aviso obsoleto (condição já resolvida) não é enviado: fecha sem mandar. O token nunca entra na mensagem nem no log.
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
from gabi.avisos import JANELA_ENTREGA as JANELA  # noqa: E402  (mesma janela que o produtor usa)


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
    return enviar_avisos_contagem(con, env, agora, http)[0]


def relatorio(enviados: int, obsoletos: int, incertos: int = 0) -> str:
    return f"{enviados} aviso(s) enviado(s), {obsoletos} obsoleto(s) descartado(s), {incertos} incerto(s)"


def enviar_avisos_contagem(con, env, agora: dt.datetime, http=_http_real) -> tuple[int, int, int]:
    """-> (enviados, obsoletos descartados, incertos). Aviso cuja condição já não é verdade (avisos.triar) não é enviado: fecha com telegram_em+entregue_em
    (nesse caso telegram_em significa "fechado", não "enviado"). Incerto (a_conferir/compromisso ausente): não envia e não fecha; reavalia na próxima rodada.
    Descartados e incertos não contam no limite de 10 por rodada (só as tentativas de envio contam)."""
    from gabi.avisos import INCERTO, RESOLVIDO, consolidar_duplicados, triar
    from gabi.rotas.avisos import descrever
    token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return 0, 0, 0
    desde = (agora - JANELA).astimezone(dt.timezone.utc).isoformat()
    agora_utc = agora.astimezone(dt.timezone.utc).isoformat()
    consolidar_duplicados(con, agora)  # uma conta repetida vira um aviso só: o mais recente
    enviados = obsoletos = incertos = tentativas = 0
    for r in con.execute("select id, tipo, payload from aviso where telegram_em is null and entregue_em is null "
                         "and criado_em>=? order by id", (desde,)).fetchall():
        if tentativas >= MAX_POR_RODADA:
            break
        estado, payload = triar(con, r["id"], r["tipo"], json.loads(r["payload"]), agora)
        if estado == RESOLVIDO:
            obsoletos += 1
            continue
        if estado == INCERTO:
            incertos += 1
            continue
        tentativas += 1
        titulo, texto = descrever(r["tipo"], payload)
        if http(f"https://api.telegram.org/bot{token}/sendMessage", {"chat_id": chat, "text": f"{titulo}\n{texto}"}) == 200:
            con.execute("update aviso set telegram_em=? where id=?", (agora_utc, r["id"]))
            enviados += 1
    return enviados, obsoletos, incertos


if __name__ == "__main__":
    con = conectar(Path(os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db")))
    migrar(con, Path(__file__).resolve().parent.parent / "migrations")
    n, obs, inc = enviar_avisos_contagem(con, os.environ, dt.datetime.now(dt.timezone.utc))
    print("telegram: " + ("desligado (sem TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID)" if not os.environ.get("TELEGRAM_BOT_TOKEN") or not os.environ.get("TELEGRAM_CHAT_ID") else relatorio(n, obs, inc)))
    sys.exit(0)
