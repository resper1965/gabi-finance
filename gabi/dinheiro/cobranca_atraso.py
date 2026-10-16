"""Rascunho de cobrança de entrada atrasada (AR2, opção A): só texto para o Ricardo ler e, se quiser, enviar ele mesmo.
R1/R2: nada é enviado daqui; sem destinatário, sem e-mail, sem canal. O texto usa só o que o extrato mostra (pagador, valor típico,
dia costumeiro) e não inventa contrato, nota nem data. Consome: esperados."""
import datetime as dt

from gabi.dinheiro.agenda_financeira import _brl
from gabi.dinheiro.esperados import entradas_esperadas


def rascunhos(con, hoje: dt.date, pagador: str | None = None) -> list[dict]:
    """Um rascunho por entrada atrasada (a de maior valor primeiro). `pagador` filtra por trecho do nome, sem diferenciar caixa."""
    out = []
    for e in entradas_esperadas(con, hoje):
        if not e["atrasada"] or (pagador and pagador.casefold() not in e["pagador"].casefold()):
            continue
        valor = _brl(e["valor_centavos"])
        out.append({
            "pagador": e["pagador"], "valor": valor, "dia_limite": e["dia_limite"], "dias_atraso": e["dias_atraso"], "confianca": e["confianca"],
            "rascunho": (f"Olá! Tudo bem? Aqui é o Ricardo. O pagamento de cerca de {valor} que costuma entrar até o dia {e['dia_limite']} "
                         f"ainda não apareceu neste mês. Você consegue me confirmar a previsão? Obrigado!"),
            "aviso": "Rascunho: nada foi enviado. Confira se o pagador e o valor estão certos antes de usar."
                     + (" Contrato novo (poucos meses de histórico): confirme que o pagador é este." if e["confianca"] == "nova" else ""),
        })
    return out
