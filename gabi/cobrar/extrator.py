"""Extrai de texto de documento: linha digitavel (boleto/arrecadacao), Pix copia-e-cola e CNPJ, sempre validados;
reconhece DAE do eSocial e le comprovante Pix.

Porte de /opt/gabi-fin/extrator.py (logica identica; so a origem de conferir_boleto mudou, agora gabi.dinheiro.caixa).
"""
import math
import re
import unicodedata
from datetime import date

from gabi.dinheiro.caixa import conferir_boleto
from gabi.hoje import hoje_brt

# ponytail: so o padrao 000201...6304+CRC; Pix com quebra de linha no meio do codigo nao e juntado
_PIX = re.compile(r"000201.*")
_LINHA = re.compile(r"\d[\d.\s-]{44,70}\d")  # arrecadacao vem como "83600000001-5 ..."
_CNPJ = re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)")


def _crc16(s):
    c = 0xFFFF
    for b in s.encode():
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return f"{c:04X}"


def pix_valido(s):
    """Copia-e-cola Pix: comeca em 000201, termina em 6304+CRC16 conferido."""
    return bool(re.fullmatch(r"000201.*6304[0-9A-F]{4}", s or "")) and _crc16(s[:-4]) == s[-4:]


def pix_valor(s):
    """Valor do campo TLV 54 (nivel raiz) ou None."""
    i = 0
    while i + 4 <= len(s):
        tag, n = s[i:i + 2], s[i + 2:i + 4]
        if not n.isdigit():
            return None
        v = s[i + 4:i + 4 + int(n)]
        if tag == "54":
            try:
                f = float(v)
            except ValueError:
                return None
            return f if math.isfinite(f) and f else None
        i += 4 + int(n)
    return None


def _achar_pix(texto):
    for m in _PIX.finditer(texto):
        t = m.group()
        for f in re.finditer(r"6304[0-9A-Fa-f]{4}", t):
            c = t[:f.end()]
            if pix_valido(c):
                return c
    return None


def _achar_linha(texto, hoje):
    for m in _LINHA.finditer(texto):
        # ponytail: so sequencias de tokens inteiros (separados por espaco); nunca corta dentro de um token
        toks = [re.sub(r"\D", "", t) for t in m.group().split()]
        toks = [t for t in toks if t]
        for tam in range(len(toks), 0, -1):
            for i in range(len(toks) - tam + 1):
                d = "".join(toks[i:i + tam])
                n = len(d)
                if n not in (47, 48) or (n == 48 and d[0] != "8"):
                    continue
                r = conferir_boleto(d, hoje)
                if r.get("digitos_ok"):
                    return {"tipo": "bancario" if n == 47 else "arrecadacao", "codigo": d,
                            "valor": r.get("valor") or None, "vencimento": r.get("vencimento")}
    return None


def achar_codigo(texto, hoje):
    """Pix valido ganha da linha digitavel; None se nada passar nos digitos verificadores."""
    texto = texto or ""
    p = _achar_pix(texto)
    if p:
        return {"tipo": "pix", "codigo": p, "valor": pix_valor(p), "vencimento": None}
    return _achar_linha(texto, hoje)


def _dv_cnpj(d):
    for n in (12, 13):
        pesos = ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] if n == 12 else [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
        r = sum(int(a) * b for a, b in zip(d[:n], pesos)) % 11
        if int(d[n]) != (0 if r < 2 else 11 - r):
            return False
    return True


def achar_cnpj(texto):
    """Primeiro CNPJ com digitos verificadores certos (14 digitos) ou None."""
    for m in _CNPJ.finditer(texto or ""):
        d = re.sub(r"\D", "", m.group())
        if len(set(d)) > 1 and _dv_cnpj(d):
            return d
    return None


def _sem_acento(s):
    """Maiusculas sem acento, mesmo tamanho do original (indices valem para o texto original)."""
    return "".join(unicodedata.normalize("NFD", c)[0] for c in s).upper()


def tipo_documento(texto, hoje=None):
    """'dae_esocial', 'comprovante_pix' (so sem linha digitavel valida) ou None."""
    t = _sem_acento(texto or "")
    if "DOCUMENTO DE ARRECADACAO DO ESOCIAL" in t or ("ESOCIAL" in t and re.search(r"\bDAE\b", t)):
        return "dae_esocial"
    if "COMPROVANTE" in t and re.search(r"\bPIX\b", t) and not _achar_linha(texto, hoje or hoje_brt()):
        return "comprovante_pix"
    return None


_PAGADOR = ("DADOS DE QUEM PAGOU", "QUEM PAGOU", "DE", "PAGADOR", "ORIGEM", "REMETENTE")
_RECEBEDOR = ("DADOS DE QUEM RECEBEU", "QUEM RECEBEU", "PAGO A", "BENEFICIARIO", "PARA", "RECEBEDOR", "DESTINO",
              "FAVORECIDO", "DESTINATARIO")
_SECAO = re.compile(r"\s*(" + "|".join(_PAGADOR + _RECEBEDOR) + r")\b\s*:?\s*(.*)$")
_ROTULOS = {
    "nome": r"NOME COMPLETO|NOME|RAZAO SOCIAL",
    "cpf_cnpj": r"CPF\s*/\s*CNPJ|CNPJ\s*/\s*CPF|CPF|CNPJ",
    "chave": r"CHAVE PIX|CHAVE",
    "banco": r"INSTITUICAO|BANCO",
    "agencia": r"AGENCIA",
    "conta": r"CONTA",
}
_TODOS = re.compile(r"\s*(?:" + "|".join(_ROTULOS.values()) + r"|VALOR|DATA(?:\s*/\s*HORA)?|TIPO DE CONTA)\b\s*:?\s*(.*)$")


_EH_ROTULO = re.compile(
    r"\s*(?:" + "|".join(_ROTULOS.values()) + r"|VALOR|DATA(?:\s*/\s*HORA)?|TIPO DE CONTA|"
    + "|".join(_PAGADOR + _RECEBEDOR) + r")\s*(?::.*)?$")  # rotulo sozinho ou "rotulo:"; "Banco Inter" nao


def _valor_br(s):
    m = re.search(r"\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d+(?:\.\d{2})?", s or "")
    if not m:
        return None
    return float(m.group().replace(".", "").replace(",", ".") if "," in m.group() else m.group())


def _campo(linhas, rotulo):
    """Valor depois do rotulo, na mesma linha ou na primeira linha nao vazia seguinte."""
    rx = re.compile(r"\s*(?:" + rotulo + r")\b\s*[:\-]?\s*(.*)$")
    for i, (orig, sa) in enumerate(linhas):
        m = rx.match(sa)
        if not m:
            continue
        v = orig[m.start(1):].strip()
        if v:
            return v
        for o2, s2 in linhas[i + 1:]:
            if o2.strip():
                # a linha seguinte ja e outro rotulo: este campo veio vazio
                return None if _EH_ROTULO.match(s2) else o2.strip()
    return None


def ler_comprovante_pix(texto):
    """Dados do RECEBEDOR de um comprovante Pix, ou None se nao achar nome nem chave."""
    linhas = [(l, _sem_acento(l)) for l in (texto or "").splitlines()]
    secoes, atual = [], None  # (papel, valor inline, linhas)
    for orig, sa in linhas:
        m = _SECAO.match(sa)
        if m and (not m.group(2) or sa.split(":")[0].strip() == m.group(1)) and not _TODOS.match(sa):
            atual = ("pagador" if m.group(1) in _PAGADOR else "recebedor", orig[m.start(2):].strip(), [])
            secoes.append(atual)
        elif atual is not None:
            atual[2].append((orig, sa))
    rec = [s for s in secoes if s[0] == "recebedor"]
    if rec:
        corpo = [l for s in rec for l in s[2]]
    elif secoes:
        corpo = [l for s in secoes if s[0] != "pagador" for l in s[2]]
    else:
        # sem secoes nao ha como saber quem e quem: rotulo repetido e ambiguo (pagador + recebedor)
        corpo = linhas
        for k in ("nome", "cpf_cnpj"):
            rx = re.compile(r"\s*(?:" + _ROTULOS[k] + r")\b")
            if sum(1 for _, sa in linhas if rx.match(sa)) > 1:
                return None
    r = {k: _campo(corpo, rx) for k, rx in _ROTULOS.items()}
    if not r["nome"] and rec:
        r["nome"] = rec[0][1] or next(
            (o.strip() for o, sa in rec[0][2] if o.strip() and not _TODOS.match(sa)), None)
    if not r["nome"] and not r["chave"]:
        return None
    r["valor"] = _valor_br(_campo(linhas, "VALOR"))
    d = re.search(r"(\d{2})/(\d{2})/(\d{4})", _campo(linhas, r"DATA(?:\s*/\s*HORA)?") or "")
    r["data"] = f"{d.group(3)}-{d.group(2)}-{d.group(1)}" if d else None
    return r
