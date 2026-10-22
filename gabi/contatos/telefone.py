"""Telefone em E.164 brasileiro, para casar contato, pessoa e remetente (veio de gabi/escuta/caixa.py; ADR-023)."""
import re


def normalizar_telefone(bruto: str) -> str | None:
    """E.164 brasileiro (+55...). Sem DDI assume +55. None se inválido. JID só vale com sufixo de telefone (@s.whatsapp.net,
    @c.us): `@lid`, `@g.us` e outros são ids opacos, nunca telefone. Celular antigo (+55 DD + 8 dígitos começando em 6–9) ganha
    o 9 na frente; fixo (2–5) não muda."""
    if not isinstance(bruto, str):
        return None
    if "@" in bruto and bruto.split("@", 1)[1].strip().lower() not in ("s.whatsapp.net", "c.us"):
        return None
    digitos = re.sub(r"\D", "", bruto.split("@")[0])
    if len(digitos) in (10, 11):
        digitos = "55" + digitos
    if digitos.startswith("55") and len(digitos) == 12 and digitos[4] in "6789":
        digitos = digitos[:4] + "9" + digitos[4:]
    if digitos.startswith("55") and len(digitos) in (12, 13):
        return "+" + digitos
    return None
