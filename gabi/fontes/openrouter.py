"""Cliente do OpenRouter (chat completions no formato OpenAI). Só o serviço `gabi-brain-fontes` tem rede e a chave (R5); o resto do
brain chega aqui pela ponte. A chave nunca entra em log, em erro nem em texto de exceção (nem se o corpo da resposta a ecoar).
Custo (USD): `usage.cost` da resposta; ausente/inválido/NaN/<=0 -> estimativa pessimista por tokens x preço por milhão; sem tokens -> valor fixo.
Nunca é 0 numa chamada bem-sucedida (o teto de gasto depende disso). Tetos no serviço: prompt, max_tokens, USD por dia (BRT), chamadas por minuto.
Modelos e variáveis padrão: docs/fontes/openrouter.md."""
import json
import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
import urllib.error
import urllib.request

URL = "https://openrouter.ai/api/v1/chat/completions"
MODELO_RAPIDO_PADRAO = "deepseek/deepseek-v4-flash"
MODELO_FORTE_PADRAO = "anthropic/claude-sonnet-5.5"


BRT = ZoneInfo("America/Sao_Paulo")


class ErroOpenRouter(Exception):
    pass


def _num(env, nome, padrao, tipo):
    try:
        v = tipo(env.get(nome, ""))
    except (TypeError, ValueError):
        return padrao
    return v if math.isfinite(v) and v > 0 else padrao


@dataclass(frozen=True)
class Limites:
    preco_entrada_usd_m: float = 3.0   # deliberadamente pessimistas
    preco_saida_usd_m: float = 15.0
    custo_padrao_usd: float = 0.05
    max_tokens_rapido: int = 1024
    max_tokens_forte: int = 2048
    max_prompt_chars: int = 50000
    teto_dia_usd: float = 3.0
    max_chamadas_min: int = 30

    @classmethod
    def do_ambiente(cls, env) -> "Limites":
        d = cls()
        return cls(_num(env, "OPENROUTER_PRECO_ENTRADA_USD_M", d.preco_entrada_usd_m, float),
                   _num(env, "OPENROUTER_PRECO_SAIDA_USD_M", d.preco_saida_usd_m, float),
                   _num(env, "OPENROUTER_CUSTO_PADRAO_USD", d.custo_padrao_usd, float),
                   _num(env, "OPENROUTER_MAX_TOKENS_FAST", d.max_tokens_rapido, int),
                   _num(env, "OPENROUTER_MAX_TOKENS_STRONG", d.max_tokens_forte, int),
                   _num(env, "OPENROUTER_MAX_PROMPT_CHARS", d.max_prompt_chars, int),
                   _num(env, "OPENROUTER_TETO_DIA_USD", d.teto_dia_usd, float),
                   _num(env, "OPENROUTER_MAX_CHAMADAS_MIN", d.max_chamadas_min, int))


def _valido(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= 0


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
    def __init__(self, chave: str, modelo_rapido: str, modelo_forte: str, http=_http_real, *, limites: Limites | None = None, relogio=time.time):
        self._chave, self.modelo_rapido, self.modelo_forte, self._http = chave, modelo_rapido, modelo_forte, http
        self.limites, self._relogio = limites or Limites(), relogio
        self._trava, self._chamadas, self._dia, self._gasto = threading.Lock(), deque(), None, 0.0

    def __repr__(self):
        return "OpenRouter(<chave oculta>)"

    def _reservar(self, prompt: str) -> None:
        """Verifica os tetos antes de qualquer rede; registra a chamada no limite por minuto."""
        lim, agora = self.limites, self._relogio()
        if len(prompt) > lim.max_prompt_chars:
            raise ErroOpenRouter("prompt grande demais")
        with self._trava:
            dia = datetime.fromtimestamp(agora, BRT).date()
            if dia != self._dia:
                self._dia, self._gasto = dia, 0.0
            if self._gasto >= lim.teto_dia_usd:
                raise ErroOpenRouter("teto diário")
            while self._chamadas and agora - self._chamadas[0] >= 60:
                self._chamadas.popleft()
            if len(self._chamadas) >= lim.max_chamadas_min:
                raise ErroOpenRouter("muitas chamadas")
            self._chamadas.append(agora)

    def _custo(self, resp) -> float:
        usage = resp.get("usage") if isinstance(resp, dict) else None
        usage = usage if isinstance(usage, dict) else {}
        c = usage.get("cost")
        if _valido(c) and c > 0:
            return float(c)
        ent, sai = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if _valido(ent) or _valido(sai):
            est = ((ent if _valido(ent) else 0) * self.limites.preco_entrada_usd_m
                   + (sai if _valido(sai) else 0) * self.limites.preco_saida_usd_m) / 1_000_000
            if est > 0:
                return est
        return self.limites.custo_padrao_usd

    def completar(self, prompt: str, *, forte: bool) -> tuple[str, float]:
        """Devolve (texto, custo em USD, nunca 0)."""
        if not self._chave:
            raise ErroOpenRouter("chave ausente")
        self._reservar(prompt)
        corpo = {"model": self.modelo_forte if forte else self.modelo_rapido, "usage": {"include": True},
                 "max_tokens": self.limites.max_tokens_forte if forte else self.limites.max_tokens_rapido,
                 "messages": [{"role": "user", "content": prompt}]}
        falha = None
        try:
            status, resp = self._http("POST", URL, corpo, {"Authorization": f"Bearer {self._chave}"})
        except ErroOpenRouter as e:
            falha = str(e)
        except Exception as e:  # noqa: BLE001 - só o tipo, nunca a mensagem (pode conter a chave)
            falha = f"OpenRouter falhou: {type(e).__name__}"
        if falha is not None:  # fora do except: sem __context__ com a exceção original
            raise ErroOpenRouter(falha)
        if status >= 400:
            raise ErroOpenRouter(f"OpenRouter -> {status}")
        texto = None
        try:
            texto = resp["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            pass
        if not isinstance(texto, str):
            raise ErroOpenRouter("resposta do OpenRouter sem texto")
        custo = self._custo(resp)
        with self._trava:
            self._gasto += custo
        return texto, custo
