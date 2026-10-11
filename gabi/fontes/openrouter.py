"""Cliente do OpenRouter (chat completions no formato OpenAI). Só o serviço `gabi-brain-fontes` tem rede e a chave (R5); o resto do
brain chega aqui pela ponte. A chave nunca entra em log, em erro nem em texto de exceção (nem se o corpo da resposta a ecoar).
Custo: `usage.cost` (USD) da resposta; ausente ou inválido = 0.0 (nunca levanta por isso). Modelos padrão: docs/fontes/openrouter.md."""
import json
import urllib.error
import urllib.request

URL = "https://openrouter.ai/api/v1/chat/completions"
MODELO_RAPIDO_PADRAO = "deepseek/deepseek-v4-flash"
MODELO_FORTE_PADRAO = "anthropic/claude-sonnet-5.5"


class ErroOpenRouter(Exception):
    pass


def _http_real(metodo, url, corpo=None, cabecalhos=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo, headers={"Content-Type": "application/json", **(cabecalhos or {})})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}  # o corpo do erro não é lido: pode ecoar a chave
    except (OSError, ValueError) as e:
        raise ErroOpenRouter(f"OpenRouter indisponível: {type(e).__name__}") from None


class OpenRouter:
    def __init__(self, chave: str, modelo_rapido: str, modelo_forte: str, http=_http_real):
        self._chave, self.modelo_rapido, self.modelo_forte, self._http = chave, modelo_rapido, modelo_forte, http

    def __repr__(self):
        return "OpenRouter(<chave oculta>)"

    def completar(self, prompt: str, *, forte: bool) -> tuple[str, float]:
        """Devolve (texto, custo em USD)."""
        if not self._chave:
            raise ErroOpenRouter("chave ausente")
        corpo = {"model": self.modelo_forte if forte else self.modelo_rapido, "usage": {"include": True},
                 "messages": [{"role": "user", "content": prompt}]}
        try:
            status, resp = self._http("POST", URL, corpo, {"Authorization": f"Bearer {self._chave}"})
        except ErroOpenRouter:
            raise
        except Exception as e:  # noqa: BLE001 - só o tipo, nunca a mensagem (pode conter a chave)
            raise ErroOpenRouter(f"OpenRouter falhou: {type(e).__name__}") from None
        if status >= 400:
            raise ErroOpenRouter(f"OpenRouter -> {status}")
        try:
            texto = resp["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ErroOpenRouter("resposta do OpenRouter sem texto") from None
        if not isinstance(texto, str):
            raise ErroOpenRouter("resposta do OpenRouter sem texto")
        custo = (resp.get("usage") or {}).get("cost") if isinstance(resp, dict) else None
        ok = isinstance(custo, (int, float)) and not isinstance(custo, bool) and custo >= 0
        return texto, float(custo) if ok else 0.0
