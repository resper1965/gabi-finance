"""Regras por emissor (quem paga cada conta): chaves normalizadas. Portado do gabi-fin/emissores.py SEM alterar a lógica.

Só a parte pura (o arquivo emissores.json deixa de existir: as regras passam a viver no banco). Consome: dinheiro.caixa.
"""
import re
import unicodedata

from gabi.dinheiro import caixa

GENERICAS = {"BOLETO", "FATURA", "CONTA", "CONTAS", "SCAN", "VIA", "DOCUMENTO", "DOC", "PAGAMENTO", "COBRANCA",
             "RECIBO", "NOTA", "IMG", "IMAGE", "FOTO", "ARQUIVO", "PDF", "WHATSAPP"}

CONECTIVOS = {"DE", "DA", "DO", "DAS", "DOS", "EM", "NA", "NO"}

def _palavras(k):
    """Palavras que contam (sem letra solta nem conectivo: "CONTA DE LUZ" -> [CONTA, LUZ])."""
    return [w for w in (k or "").split() if len(w) > 1 and w not in CONECTIVOS]

def chave_extrato(nome):
    """Nome normalizado, sem filtro (descricao do extrato / nome de regra); None se vazio."""
    if not nome:
        return None
    sem = "".join(c for c in unicodedata.normalize("NFKD", nome) if not unicodedata.combining(c))
    return caixa.norm(sem) or None

def generica(k):
    """Chave que nao identifica emissor: vazia ou so com palavras genericas (BOLETO, FATURA, IMG...)."""
    if k and re.fullmatch(r"\d{14}", k):
        return False
    return all(w in GENERICAS for w in _palavras(k))

def chave_forte(k):
    """CNPJ ou nome com 2+ palavras: forte o bastante para descartar documento automaticamente."""
    return bool(k) and (bool(re.fullmatch(r"\d{14}", k)) or len(_palavras(k)) >= 2)

def chave(cnpj, nome):
    """Chave de documento: CNPJ (14 digitos) se houver, senao o titulo normalizado.

    None para titulo generico (uma palavra so, ou so palavras genericas: "boleto_123456" -> None)."""
    d = re.sub(r"\D", "", cnpj or "")
    if len(d) == 14:
        return d
    k = chave_extrato(nome)
    if len(_palavras(k)) < 2 or generica(k):
        return None
    return k

def regra(emis, chave):
    """Regra do emissor pela chave ou por um dos apelidos."""
    if chave in emis:
        return emis[chave]
    for r in emis.values():
        if chave in (r.get("apelidos") or []):
            return r
    return None
