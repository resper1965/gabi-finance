"""Cliente do OpenRouter (chat completions no formato OpenAI). Só o serviço `gabi-brain-fontes` tem rede e a chave (R5); o resto do
brain chega aqui pela ponte. A chave nunca entra em log, em erro nem em texto de exceção (nem se o corpo da resposta a ecoar).
Custo (USD): `usage.cost` da resposta; ausente/inválido/NaN/<=0 -> estimativa pessimista por tokens x preço por milhão; sem tokens -> valor fixo.
Nunca é 0 numa chamada bem-sucedida (o teto de gasto depende disso). Tetos no serviço: prompt, max_tokens, USD por dia (BRT), chamadas por minuto.
Modelos e variáveis padrão: docs/fontes/openrouter.md."""
import base64
import json
import math
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
import urllib.error
import urllib.request
from gabi.fontes._http import abrir

from gabi.visao_pdf import paginas as _paginas_pdf

URL = "https://openrouter.ai/api/v1/chat/completions"
MODELO_RAPIDO_PADRAO = "deepseek/deepseek-v4-flash"
MODELO_FORTE_PADRAO = "anthropic/claude-sonnet-5.5"


BRT = ZoneInfo("America/Sao_Paulo")
CHARS_POR_PAGINA = 4500       # reserva: ~1500 tokens de entrada por página de PDF (len/3 tokens, como no prompt)
OCR_USD_PAGINA = 0.002        # reserva: OCR do provedor (~US$ 2 por mil páginas), no pior caso
PDF_MOTOR_PADRAO = "mistral-ocr"  # único motor do plugin de arquivos que lê PDF digitalizado com qualquer modelo (o `pdf-text` só extrai texto)


class ErroOpenRouter(Exception):
    pass


_CUSTO_NA_MENSAGEM = re.compile(r"\(custo_usd=([0-9]+(?:\.[0-9]+)?)\)$")


def custo_da_falha(e: BaseException) -> float | None:
    """Custo que a OpenRouter informou numa resposta cobrada e sem texto. Vai no fim da mensagem porque a ponte só leva a mensagem."""
    m = _CUSTO_NA_MENSAGEM.search(str(e)) if isinstance(e, ErroOpenRouter) else None
    return float(m.group(1)) if m else None


def _num(env, nome, padrao, tipo, zero_ok=False):
    """Não numérico, NaN/inf e negativo caem no padrão; 0 só vale onde significa "bloquear tudo"."""
    try:
        v = tipo(env.get(nome, ""))
    except (TypeError, ValueError):
        return padrao
    return v if math.isfinite(v) and (v > 0 or (zero_ok and v == 0)) else padrao


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
    max_pdf_bytes: int = 8 * 1024 * 1024   # leitura de PDF por visão: tetos conservadores (a chamada pode baixá-los, nunca subi-los)
    max_pdf_paginas: int = 10

    @classmethod
    def do_ambiente(cls, env) -> "Limites":
        d = cls()
        return cls(_num(env, "OPENROUTER_PRECO_ENTRADA_USD_M", d.preco_entrada_usd_m, float),
                   _num(env, "OPENROUTER_PRECO_SAIDA_USD_M", d.preco_saida_usd_m, float),
                   _num(env, "OPENROUTER_CUSTO_PADRAO_USD", d.custo_padrao_usd, float),
                   _num(env, "OPENROUTER_MAX_TOKENS_FAST", d.max_tokens_rapido, int),
                   _num(env, "OPENROUTER_MAX_TOKENS_STRONG", d.max_tokens_forte, int),
                   _num(env, "OPENROUTER_MAX_PROMPT_CHARS", d.max_prompt_chars, int),
                   _num(env, "OPENROUTER_TETO_DIA_USD", d.teto_dia_usd, float, True),
                   _num(env, "OPENROUTER_MAX_CHAMADAS_MIN", d.max_chamadas_min, int, True),
                   _num(env, "OPENROUTER_MAX_PDF_BYTES", d.max_pdf_bytes, int),
                   _num(env, "OPENROUTER_MAX_PDF_PAGINAS", d.max_pdf_paginas, int))


def _valido(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= 0


def _http_real(metodo, url, corpo=None, cabecalhos=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo, headers={"Content-Type": "application/json", **(cabecalhos or {})})
    try:
        with abrir(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}  # o corpo do erro não é lido: pode ecoar a chave
    except (OSError, ValueError) as e:
        raise ErroOpenRouter(f"OpenRouter indisponível: {type(e).__name__}") from None


class OpenRouter:
    def __init__(self, chave: str, modelo_rapido: str, modelo_forte: str, http=_http_real, *, limites: Limites | None = None,
                 relogio=time.time, monotonico=time.monotonic):
        """relogio = hora de parede (fronteira do dia em BRT); monotonico = janela por minuto. Ambos injetáveis nos testes."""
        self._chave, self.modelo_rapido, self.modelo_forte, self._http = chave, modelo_rapido, modelo_forte, http
        self.limites, self._relogio, self._mono = limites or Limites(), relogio, monotonico
        self._trava, self._chamadas, self._dia, self._gasto = threading.Lock(), deque(), None, 0.0

    def __repr__(self):
        return "OpenRouter(<chave oculta>)"

    def _max_tokens(self, forte: bool) -> int:
        return self.limites.max_tokens_forte if forte else self.limites.max_tokens_rapido

    def _reserva(self, prompt: str, forte: bool, extra_chars: int = 0, extra_usd: float = 0.0) -> float:
        """Pior caso: max_tokens no preço de saída + prompt (len/3 tokens) no de entrada; nunca menos que o custo padrão."""
        lim = self.limites
        est = (self._max_tokens(forte) * lim.preco_saida_usd_m + ((len(prompt) + extra_chars) / 3) * lim.preco_entrada_usd_m) / 1_000_000 + extra_usd
        return max(lim.custo_padrao_usd, est)

    def _reservar(self, prompt: str, forte: bool, extra_chars: int = 0, extra_usd: float = 0.0) -> float:
        """Verifica os tetos antes de qualquer rede e reserva o custo pessimista (tudo sob a trava). Recusa não cobra nada."""
        lim = self.limites
        if len(prompt) > lim.max_prompt_chars:
            raise ErroOpenRouter("prompt grande demais")
        reserva = self._reserva(prompt, forte, extra_chars, extra_usd)
        with self._trava:
            dia = datetime.fromtimestamp(self._relogio(), BRT).date()
            if dia != self._dia:
                self._dia, self._gasto = dia, 0.0
            if self._gasto + reserva > lim.teto_dia_usd:
                raise ErroOpenRouter("teto diário")
            agora = self._mono()
            while self._chamadas and agora - self._chamadas[0] >= 60:
                self._chamadas.popleft()
            if len(self._chamadas) >= lim.max_chamadas_min:
                raise ErroOpenRouter("muitas chamadas")
            self._chamadas.append(agora)
            self._gasto += reserva
        return reserva

    def _custo(self, resp, forte: bool) -> float:
        return self._custo_informado(resp, forte) or self.limites.custo_padrao_usd

    def _custo_informado(self, resp, forte: bool) -> float | None:
        """Custo pela `usage` da resposta (o `cost` ou a estimativa pelos tokens); None quando a resposta não diz nada."""
        usage = resp.get("usage") if isinstance(resp, dict) else None
        usage = usage if isinstance(usage, dict) else {}
        c = usage.get("cost")
        if _valido(c) and c > 0:
            return float(c)
        ent, sai = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if _valido(ent) and not _valido(sai):
            sai = self._max_tokens(forte)  # sem a saída: pior caso
        if _valido(ent) or _valido(sai):
            est = ((ent if _valido(ent) else 0) * self.limites.preco_entrada_usd_m
                   + (sai if _valido(sai) else 0) * self.limites.preco_saida_usd_m) / 1_000_000
            if est > 0:
                return est
        return None

    def completar(self, prompt: str, *, forte: bool) -> tuple[str, float]:
        """Devolve (texto, custo real em USD, nunca 0). Falha depois do envio mantém a reserva cobrada (pode ter sido faturada)."""
        if not self._chave:
            raise ErroOpenRouter("chave ausente")
        reserva = self._reservar(prompt, forte)
        corpo = {"model": self.modelo_forte if forte else self.modelo_rapido, "usage": {"include": True},
                 "max_tokens": self._max_tokens(forte), "messages": [{"role": "user", "content": prompt}]}
        return self._enviar(corpo, reserva, forte)

    def completar_pdf(self, pdf: bytes, prompt: str, *, forte: bool = False, max_bytes: int | None = None,
                      max_paginas: int | None = None, motor: str = PDF_MOTOR_PADRAO) -> tuple[str, float]:
        """Lê um PDF (digitalizado) pelo suporte nativo de arquivos do OpenRouter: o PDF vai em base64 (`type: file`) e o plugin `file-parser` o lê
        (sem rasterizador no venv). Tetos de tamanho e de páginas vêm de `Limites`; a chamada só pode BAIXÁ-LOS. Recusa antes de qualquer rede
        (PDF inválido, grande demais, páginas demais, teto diário, chamadas por minuto) e não cobra nada. Falha depois do envio mantém a reserva.
        Páginas contadas por aproximação (índice comprimido = 0): vale então o teto de bytes."""
        if not self._chave:
            raise ErroOpenRouter("chave ausente")
        if not isinstance(pdf, (bytes, bytearray)) or not bytes(pdf[:5]) == b"%PDF-":
            raise ErroOpenRouter("pdf inválido")
        lim = self.limites
        teto_b = min(max_bytes, lim.max_pdf_bytes) if isinstance(max_bytes, int) and not isinstance(max_bytes, bool) and max_bytes > 0 else lim.max_pdf_bytes
        teto_p = min(max_paginas, lim.max_pdf_paginas) if isinstance(max_paginas, int) and not isinstance(max_paginas, bool) and max_paginas > 0 else lim.max_pdf_paginas
        if len(pdf) > teto_b:
            raise ErroOpenRouter("pdf grande demais")
        pag = _paginas_pdf(bytes(pdf))
        if pag > teto_p:
            raise ErroOpenRouter("pdf com páginas demais")
        n = max(pag, 1)
        reserva = self._reservar(prompt, forte, extra_chars=n * CHARS_POR_PAGINA, extra_usd=n * OCR_USD_PAGINA)
        dados = "data:application/pdf;base64," + base64.b64encode(bytes(pdf)).decode()
        corpo = {"model": self.modelo_forte if forte else self.modelo_rapido, "usage": {"include": True}, "max_tokens": self._max_tokens(forte),
                 "plugins": [{"id": "file-parser", "pdf": {"engine": motor}}],
                 "messages": [{"role": "user", "content": [{"type": "text", "text": prompt},
                                                           {"type": "file", "file": {"filename": "documento.pdf", "file_data": dados}}]}]}
        return self._enviar(corpo, reserva, forte)

    def _enviar(self, corpo: dict, reserva: float, forte: bool) -> tuple[str, float]:
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
            custo = self._custo_informado(resp, forte)
            if custo is None:  # sem `usage`: a reserva fica cobrada
                raise ErroOpenRouter("resposta do OpenRouter sem texto")
            with self._trava:
                self._gasto += custo - reserva
            raise ErroOpenRouter(f"resposta do OpenRouter sem texto (custo_usd={custo:.6f})")
        custo = self._custo(resp, forte)
        with self._trava:
            self._gasto += custo - reserva
        return texto, custo
