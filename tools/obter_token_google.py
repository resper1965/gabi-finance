"""Obtém o refresh token de UMA conta Google para a Gabi (cliente OAuth do tipo "Computador"), com os escopos de uma vez:
contacts.readonly, calendar.readonly, calendar.events (criar evento aprovado, ADR-024) e gmail.modify. Roda no terminal do dono, não no servidor da Gabi: nada é gravado em arquivo e o
Client secret é pedido sem eco. Fluxo: mostra o link de consentimento; você abre no navegador, entra na conta, e o navegador termina numa página de erro
em localhost (esperado); copie a URL dessa página e cole aqui. A linha final vai para /etc/gabi/google.env (root:root 0600).
Uso: sudo .venv/bin/python -m tools.obter_token_google resper@gmail.com --env /etc/gabi/google.env --gravar
(sem --env ele pede o Client ID e o secret; com --gravar o token vai direto para o google.env sem aparecer na tela)"""
import base64
import getpass
import hashlib
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from gabi.fontes.google_oauth import ErroGoogleOAuth, conta_valida, nome_da_variavel

ESCOPOS = ("https://www.googleapis.com/auth/contacts.readonly", "https://www.googleapis.com/auth/calendar.readonly",
          "https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/gmail.modify")
REDIRECT = "http://localhost:8765"
AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
ENV_PADRAO = "/etc/gabi/google.env"


def pkce() -> tuple[str, str]:
    """(verificador, desafio S256): o código da URL só serve para quem tem o verificador."""
    verificador = secrets.token_urlsafe(64)
    return verificador, base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()


def _estado() -> str:
    return secrets.token_urlsafe(16)


def url_de_consentimento(client_id: str, desafio: str, estado: str, redirect: str = REDIRECT) -> str:
    return AUTORIZAR + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code", "scope": " ".join(ESCOPOS), "access_type": "offline",
        "prompt": "consent", "code_challenge": desafio, "code_challenge_method": "S256", "state": estado})


def extrair_codigo(texto: str, estado: str) -> str:
    """Aceita a URL final inteira (confere o `state` e recusa erro) ou só o código."""
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("nada foi colado")
    if "code=" not in texto and "error=" not in texto and not texto.startswith("http"):
        return texto
    q = urllib.parse.parse_qs(urllib.parse.urlparse(texto).query)
    if q.get("error"):
        raise ValueError(f"o Google recusou: {q['error'][0]}")
    if q.get("state", [None])[0] != estado:
        raise ValueError("a URL não é deste pedido (state diferente): gere o link de novo")
    if not q.get("code"):
        raise ValueError("a URL não tem o parâmetro code")
    return q["code"][0]


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


def trocar(client_id: str, client_secret: str, codigo: str, verificador: str, http=_http_form, redirect: str = REDIRECT) -> dict:
    status, resp = http(TOKEN, {"grant_type": "authorization_code", "code": codigo, "client_id": client_id, "client_secret": client_secret,
                                "redirect_uri": redirect, "code_verifier": verificador})
    if status >= 400 or not isinstance(resp, dict):
        raise ValueError(f"o Google recusou a troca ({resp.get('error', status) if isinstance(resp, dict) else status})")
    return resp


def conferir(resp: dict) -> tuple[str, list[str]]:
    """(refresh token, escopos que faltaram). Sem refresh token (não veio offline) é erro."""
    token = resp.get("refresh_token")
    if not isinstance(token, str) or not token:
        raise ValueError("o Google não devolveu refresh token (use uma conta nova no consentimento e confira o link)")
    concedidos = set(str(resp.get("scope", "")).split())
    return token, sorted(set(ESCOPOS) - concedidos)


def cliente_do_arquivo(caminho) -> tuple[str, str] | None:
    """(Client ID, Client secret) de um google.env, ou None se o arquivo não existe, não é legível ou está incompleto."""
    try:
        linhas = Path(caminho).read_text().splitlines()
    except OSError:
        return None
    v = {k.strip(): val.strip() for k, _, val in (l.partition("=") for l in linhas if "=" in l and not l.lstrip().startswith("#"))}
    return (v["GOOGLE_CLIENT_ID"], v["GOOGLE_CLIENT_SECRET"]) if v.get("GOOGLE_CLIENT_ID") and v.get("GOOGLE_CLIENT_SECRET") else None


def gravar_token(caminho, conta: str, token: str) -> None:
    """Põe `GOOGLE_REFRESH_<CONTA>=<token>` no google.env (troca a linha da mesma conta, mantém o resto e o modo 0600), de forma atômica."""
    caminho = Path(caminho)
    nome = nome_da_variavel(conta)
    linhas = caminho.read_text().splitlines() if caminho.exists() else []
    novas = [l for l in linhas if not l.startswith(nome + "=")] + [f"{nome}={token}"]
    tmp = caminho.with_name(caminho.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(novas) + "\n")
    os.replace(tmp, caminho)


def main(argv=None, *, entrada=input, segredo=getpass.getpass, http=_http_form) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    gravar = "--gravar" in argv
    argv = [a for a in argv if a != "--gravar"]
    env = ENV_PADRAO
    if "--env" in argv:
        i = argv.index("--env")
        env = argv[i + 1] if i + 1 < len(argv) else None
        argv = argv[:i] + argv[i + 2:]
    try:
        conta = conta_valida(argv[0]) if len(argv) == 1 and env else None
    except ErroGoogleOAuth:
        conta = None
    if conta is None:
        print("Uso: python -m tools.obter_token_google <e-mail da conta> [--env /etc/gabi/google.env] [--gravar]", file=sys.stderr)
        return 2
    cliente = cliente_do_arquivo(env)
    if cliente:
        client_id, client_secret = cliente
        print(f"Usando o cliente OAuth de {env}.")
    else:
        client_id = entrada("Client ID: ").strip()
        client_secret = segredo("Client secret (não aparece na tela): ").strip()
    verificador, desafio = pkce()
    estado = _estado()
    print(f"\n1) Abra este link no navegador, entre com {conta} e aceite:\n\n{url_de_consentimento(client_id, desafio, estado)}\n")
    print("2) O navegador vai terminar numa página de erro em localhost. É normal. Copie a URL inteira dessa página.\n")
    try:
        codigo = extrair_codigo(entrada("3) Cole aqui a URL (ou só o code): "), estado)
        token, faltou = conferir(trocar(client_id, client_secret, codigo, verificador, http=http))
    except ValueError as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    if faltou:
        print("ERRO: faltou(aram) escopo(s) no consentimento: " + ", ".join(e.rsplit("/", 1)[1] for e in faltou) + ". Refaça marcando todas as permissões.", file=sys.stderr)
        return 1
    if gravar:
        try:
            gravar_token(env, conta, token)
        except OSError:
            print(f"ERRO: não consegui gravar em {env} (rode com sudo?). Guarde esta linha:\n\n{nome_da_variavel(conta)}={token}\n", file=sys.stdout)
            print(f"ERRO: não consegui gravar em {env}.", file=sys.stderr)
            return 1
        print(f"\nPronto. {nome_da_variavel(conta)} gravado em {env} (o token não é mostrado).")
        return 0
    print(f"\nPronto. Acrescente esta linha em /etc/gabi/google.env:\n\n{nome_da_variavel(conta)}={token}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
