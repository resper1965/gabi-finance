"""Máscara de CPF/documentos: mantém só os 2 últimos dígitos e a pontuação. Portado do repositório de migração (revisado)."""
import re

# 11 dígitos com separadores opcionais (ponto, espaço, hífen, barra, travessões) entre os grupos 3-3-3-2.
_CANDIDATO = re.compile(r"(?<!\d)\d{3}[.\s]?\d{3}[.\s]?\d{3}[-.\s/\u2013\u2014]?\d{2}(?!\d)")


def mascarar_documento(valor: str) -> str:
    digitos = [i for i, c in enumerate(valor) if c.isdigit()]
    manter = set(digitos[-2:])
    return "".join("*" if c.isdigit() and i not in manter else c for i, c in enumerate(valor))


def _cpf_valido(digitos: str) -> bool:
    if len(digitos) != 11 or len(set(digitos)) == 1:
        return False
    for n in (9, 10):
        soma = sum(int(digitos[i]) * (n + 1 - i) for i in range(n))
        if (soma * 10 % 11) % 10 != int(digitos[n]):
            return False
    return True


def _substituir(m: re.Match) -> str:
    bruto = m.group(0)
    digitos = re.sub(r"\D", "", bruto)
    tem_separador = digitos != bruto
    # Com pontuação, mascara sempre; sem pontuação, só se o dígito verificador fecha (poupa telefones e valores).
    return mascarar_documento(bruto) if tem_separador or _cpf_valido(digitos) else bruto


def mascarar_texto(texto: str) -> str:
    return _CANDIDATO.sub(_substituir, texto)
