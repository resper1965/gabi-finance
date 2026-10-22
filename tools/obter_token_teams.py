"""Obtém o refresh token DELEGADO do Teams (envio de mensagem aprovada, ADR-024) pelo fluxo de código de dispositivo da Microsoft.
Consome: gabi.fontes.graph_ness (LOGIN) e gabi.fontes.graph_ness_envios (ESCOPO_TEAMS); tenant e client id vêm do mesmo env (M365_TENANT_ID, M365_CLIENT_ID).
Cliente público: nenhum client secret é enviado. Roda no terminal do dono, não no servidor: mostra o endereço e o código, você entra no navegador com a conta da ness
e a ferramenta espera a aprovação. Nada é gravado sem --gravar; com --gravar a linha GRAPH_NESS_TEAMS_REFRESH= entra no env sem o token aparecer na tela.
Uso: sudo .venv/bin/python -m tools.obter_token_teams --env /etc/gabi/graph-ness.env [--gravar]
(sem --gravar imprime só a linha final para você acrescentar ao env)"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from gabi.fontes.graph_ness import LOGIN
from gabi.fontes.graph_ness_envios import ESCOPO_TEAMS

ENV_PADRAO = "/etc/gabi/graph-ness.env"
VARIAVEL = "GRAPH_NESS_TEAMS_REFRESH"
GRANT = "urn:ietf:params:oauth:grant-type:device_code"
_ID = re.compile(r"^[0-9A-Za-z._-]{1,100}$")  # tenant (GUID ou domínio) e client id: nunca "/" nem espaço (entram na URL)
_CODIGO = re.compile(r"^[a-z_]{1,40}$")  # código de erro do provedor que pode aparecer na mensagem; o resto vira "erro"
LIMITE_S = 900  # a Microsoft expira o código em 15 min; teto de segurança contra laço infinito


def _http_form(url: str, corpo: dict) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(corpo).encode(), method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def _codigo_de_erro(resp) -> str:
    c = resp.get("error") if isinstance(resp, dict) else None
    return c if isinstance(c, str) and _CODIGO.match(c) else "erro"


def pedir_codigo(http, tenant: str, client_id: str) -> dict:
    """Pede o código de dispositivo. Devolve device_code, user_code, verification_uri e interval."""
    status, resp = http(f"{LOGIN}/{tenant}/oauth2/v2.0/devicecode", {"client_id": client_id, "scope": ESCOPO_TEAMS})
    if status >= 400 or not isinstance(resp, dict) or not all(resp.get(k) for k in ("device_code", "user_code", "verification_uri")):
        raise SystemExit(f"ERRO: a Microsoft recusou o pedido de código ({_codigo_de_erro(resp) if status >= 400 else 'resposta incompleta'}).")
    return resp


def esperar_token(http, tenant: str, client_id: str, device_code: str, intervalo, dormir=time.sleep) -> str:
    """Faz polling em /token até aprovarem. `slow_down` soma 5 s ao intervalo; qualquer outro erro (expired_token, declined...) encerra com código fixo."""
    intervalo = max(int(intervalo or 5), 1)
    esperado = 0
    while True:
        dormir(intervalo)
        esperado += intervalo
        status, resp = http(f"{LOGIN}/{tenant}/oauth2/v2.0/token", {"grant_type": GRANT, "client_id": client_id, "device_code": device_code})
        if status < 400 and isinstance(resp, dict):
            token = resp.get("refresh_token")
            if not isinstance(token, str) or not token:
                raise SystemExit("ERRO: a Microsoft não devolveu refresh token (confira o escopo offline_access).")
            return token
        codigo = _codigo_de_erro(resp)
        if codigo == "slow_down":
            intervalo += 5
        elif codigo != "authorization_pending":
            raise SystemExit(f"ERRO: login não concluído ({codigo}). Rode a ferramenta de novo.")
        if esperado > LIMITE_S:
            raise SystemExit("ERRO: login não concluído (expired_token). Rode a ferramenta de novo.")


def ids_do_env(caminho) -> tuple[str, str] | None:
    """(tenant, client id) do env, ou None se faltam, não são legíveis ou têm formato estranho. Aceita espaços ao redor do '='."""
    try:
        linhas = Path(caminho).read_text().splitlines()
    except OSError:
        return None
    v = {k.strip(): val.strip() for k, _, val in (l.partition("=") for l in linhas if "=" in l and not l.lstrip().startswith("#"))}
    tenant, cliente = v.get("M365_TENANT_ID", ""), v.get("M365_CLIENT_ID", "")
    return (tenant, cliente) if _ID.match(tenant) and _ID.match(cliente) else None


def gravar_no_env(caminho, valor: str) -> None:
    """Põe `GRAPH_NESS_TEAMS_REFRESH=<valor>` no env (troca a linha existente, mantém o resto e o modo do arquivo), de forma atômica."""
    caminho = Path(caminho)
    linhas = caminho.read_text().splitlines() if caminho.exists() else []
    modo = (caminho.stat().st_mode & 0o777) if caminho.exists() else 0o600
    novas = [l for l in linhas if not re.match(rf"^\s*{VARIAVEL}\s*=", l)] + [f"{VARIAVEL}={valor}"]
    tmp = caminho.with_name(caminho.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(novas) + "\n")
    os.chmod(tmp, modo)
    if caminho.exists():
        try:
            os.chown(tmp, caminho.stat().st_uid, caminho.stat().st_gid)
        except PermissionError:
            pass
    os.replace(tmp, caminho)


def main(argv=None, *, http=_http_form, dormir=time.sleep) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    gravar = "--gravar" in argv
    argv = [a for a in argv if a != "--gravar"]
    env = ENV_PADRAO
    if "--env" in argv:
        i = argv.index("--env")
        env = argv[i + 1] if i + 1 < len(argv) else None
        argv = argv[:i] + argv[i + 2:]
    if argv or not env:
        print("Uso: python -m tools.obter_token_teams --env /etc/gabi/graph-ness.env [--gravar]", file=sys.stderr)
        return 2
    ids = ids_do_env(env)
    if ids is None:
        print(f"ERRO: {env} não tem M365_TENANT_ID e M365_CLIENT_ID válidos.", file=sys.stderr)
        return 2
    tenant, client_id = ids
    try:
        cod = pedir_codigo(http, tenant, client_id)
        print(f"\n1) Abra {cod['verification_uri']} no navegador.\n2) Digite o código: {cod['user_code']}\n3) Entre com a conta da ness e aceite as permissões.\n\nEsperando a aprovação...")
        token = esperar_token(http, tenant, client_id, cod["device_code"], cod.get("interval", 5), dormir)
    except SystemExit as e:
        print(e.code, file=sys.stderr)
        return 1
    if gravar:
        try:
            gravar_no_env(env, token)
        except OSError:
            print(f"ERRO: não consegui gravar em {env} (rode com sudo?). Rode de novo sem --gravar para receber a linha.", file=sys.stderr)
            return 1
        print(f"\nPronto. {VARIAVEL} gravado em {env} (o token não é mostrado).")
        return 0
    print(f"\nPronto. Acrescente esta linha em {env}:\n\n{VARIAVEL}={token}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
