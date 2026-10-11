"""Obtém o refresh token de UMA conta Google para a Gabi (cliente OAuth do tipo "Computador"), com os três escopos de uma vez:
contacts.readonly, calendar.readonly e gmail.modify. Roda no terminal do dono, não no servidor da Gabi: nada é gravado em arquivo e o
Client secret é pedido sem eco. Fluxo: mostra o link de consentimento; você abre no navegador, entra na conta, e o navegador termina numa página de erro
em localhost (esperado); copie a URL dessa página e cole aqui. A linha final vai para /etc/gabi/google.env (root:root 0600).
Uso: .venv/bin/python -m tools.obter_token_google resper@gmail.com"""
import base64
import getpass
import hashlib
import json
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request

from gabi.fontes.google_oauth import ErroGoogleOAuth, conta_valida, nome_da_variavel

ESCOPOS = ("https://www.googleapis.com/auth/contacts.readonly", "https://www.googleapis.com/auth/calendar.readonly", "https://www.googleapis.com/auth/gmail.modify")
REDIRECT = "http://localhost:8765"
AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"


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


def main(argv=None, *, entrada=input, segredo=getpass.getpass, http=_http_form) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        conta = conta_valida(argv[0]) if len(argv) == 1 else None
    except ErroGoogleOAuth:
        conta = None
    if conta is None:
        print("Uso: python -m tools.obter_token_google <e-mail da conta>", file=sys.stderr)
        return 2
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
    print(f"\nPronto. Acrescente esta linha em /etc/gabi/google.env:\n\n{nome_da_variavel(conta)}={token}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
