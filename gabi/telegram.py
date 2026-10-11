"""Entrega dos avisos ao Telegram (G15): DESLIGADA por padrão. Só envia se TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID estiverem no ambiente
(/etc/gabi/telegram.env, colocado pelo Ricardo: é a exceção à R2). Envia o texto em pt-BR do aviso (só nome, valor e datas: nunca CPF, conta ou chave PIX),
no máximo 10 por rodada, só os dos últimos 2 dias e ainda não lidos (exceto `escuta_atencao`, que vai primeiro e não expira); marca `telegram_em` somente depois do 200. Aviso obsoleto (condição já resolvida) não é enviado: fecha sem mandar. O token nunca entra na mensagem nem no log.
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
    return enviar_avisos_contagem(con, env, agora, http)[0]


def relatorio(enviados: int, obsoletos: int) -> str:
    return f"{enviados} aviso(s) enviado(s), {obsoletos} obsoleto(s) descartado(s)"


def enviar_avisos_contagem(con, env, agora: dt.datetime, http=_http_real) -> tuple[int, int]:
    """-> (enviados, obsoletos descartados). Aviso cuja condição já não é verdade (avisos.ainda_vale) não é enviado: fecha com telegram_em+entregue_em.
    Descartados não contam no limite de 10 por rodada (só as tentativas de envio contam)."""
    from gabi.avisos import ainda_vale
    from gabi.rotas.avisos import descrever
    token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return 0, 0
    desde = (agora - JANELA).astimezone(dt.timezone.utc).isoformat()
    agora_utc = agora.astimezone(dt.timezone.utc).isoformat()
    enviados = obsoletos = tentativas = 0
    # escuta_atencao (possível crise) vai primeiro e nunca é descartada por idade enquanto não lida (I1c)
    for r in con.execute("select id, tipo, payload from aviso where telegram_em is null and entregue_em is null "
                         "and (criado_em>=? or tipo='escuta_atencao') order by tipo!='escuta_atencao', id", (desde,)).fetchall():
        if tentativas >= MAX_POR_RODADA:
            break
        payload = json.loads(r["payload"])
        if not ainda_vale(con, r["tipo"], payload):
            con.execute("update aviso set telegram_em=?, entregue_em=? where id=?", (agora_utc, agora_utc, r["id"]))
            obsoletos += 1
            continue
        tentativas += 1
        titulo, texto = descrever(r["tipo"], payload)
        if http(f"https://api.telegram.org/bot{token}/sendMessage", {"chat_id": chat, "text": f"{titulo}\n{texto}"}) == 200:
            con.execute("update aviso set telegram_em=? where id=?", (agora_utc, r["id"]))
            enviados += 1
    return enviados, obsoletos


if __name__ == "__main__":
    con = conectar(Path(os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db")))
    migrar(con, Path(__file__).resolve().parent.parent / "migrations")
    n, obs = enviar_avisos_contagem(con, os.environ, dt.datetime.now(dt.timezone.utc))
    print("telegram: " + ("desligado (sem TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID)" if not os.environ.get("TELEGRAM_BOT_TOKEN") or not os.environ.get("TELEGRAM_CHAT_ID") else relatorio(n, obs)))
    sys.exit(0)
