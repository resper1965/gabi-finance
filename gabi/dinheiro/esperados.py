"""Entradas esperadas: aprende o normal de cada pagador pelos últimos 5 meses (média, valor típico, dia costumeiro) e diz o que
já deveria ter caído e não caiu. Só lê; não grava nem envia (R1/R2). Nada de pagador chumbado: tudo vem do extrato.
Consome: lancamento, conta.

Regras (todas calculadas, nenhuma por nome):
- só crédito em conta BANK liberada, de pelo menos R$ 500, que não seja resgate, rendimento, estorno nem pagamento de cartão;
- o mesmo pagador com valores bem diferentes vira séries separadas ("camadas"): valores com razão maior que 1,3 entre vizinhos;
- vale como esperada a série presente em 3 dos últimos 5 meses fechados, ou em 2 meses fechados seguidos ("nova");
- só alerta se o mês anterior teve o pagamento (série ativa) e o mês atual ainda não (valor dentro de 30% do típico) e o dia de hoje já
  passou do dia mais tardio visto nos meses anteriores (mais uma folga pequena)."""
import datetime as dt
import re
import statistics as st
import unicodedata

MESES = 5
MINIMO_CENTAVOS = 50000
RAZAO_CAMADA = 1.3
TOLERANCIA_VALOR = 0.3
EXCLUIR = re.compile(r"RESGATE|RENDIMENTO|REMUNERA|INVESTBACK|ESTORNO|CREDITO REF|JUROS|DEB\.? ?AUTOM|PAGAMENTO RECEBIDO")
PREFIXOS = re.compile(r"^\d{11,14}-|\b(PIX RECEBIDO( DE)?|ENTRADA|RECEBIMENTOS?|TRANSFERENCIA|TED|DOC)\b|\bT\d{2}/\d{2}\b|\d{2}/\d{2}")


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").upper()


def _chave(descricao: str) -> str:
    d = PREFIXOS.sub(" ", _sem_acento(descricao))
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", d).split())[:40]


def _mes(d: dt.date, atras: int) -> str:
    n = d.year * 12 + d.month - 1 - atras
    return f"{n // 12:04d}-{n % 12 + 1:02d}"


def _series(creditos: list[tuple[str, int]]) -> list[list[tuple[str, int]]]:
    """Separa os créditos de um pagador em camadas por proximidade de valor."""
    ordenados = sorted(creditos, key=lambda c: c[1])
    grupos = [[ordenados[0]]]
    for c in ordenados[1:]:
        (grupos[-1].append(c) if c[1] <= grupos[-1][-1][1] * RAZAO_CAMADA else grupos.append([c]))
    return grupos


def _serie(chave: str, itens: list[tuple[str, int]], hoje: dt.date) -> dict | None:
    atual, anterior, antes = _mes(hoje, 0), _mes(hoje, 1), _mes(hoje, 2)
    fechados = [(d, v) for d, v in itens if d[:7] != atual]
    presentes = {d[:7] for d, _ in fechados}
    n = len(presentes)
    if anterior not in presentes or not (n >= 3 or (n >= 2 and antes in presentes)):
        return None
    valores = [v for _, v in fechados]
    media = st.mean(valores)
    cv = st.pstdev(valores) / media if len(valores) > 1 and media else 0
    dias = [int(d[8:10]) for d, _ in fechados]
    dia_limite = max(dias) + max(1, (max(dias) - min(dias)) // 4)
    veio = sorted((d, v) for d, v in itens if d[:7] == atual and abs(v - media) <= media * TOLERANCIA_VALOR)
    ocorreu = bool(veio)
    atrasada = not ocorreu and hoje.day > dia_limite
    return {"pagador": chave.title(), "valor_centavos": round(media), "dia_tipico": int(st.median(dias)), "dia_limite": dia_limite, "meses": n,
            "confianca": "alta" if n >= 4 and cv < 0.1 else ("media" if n >= 3 else "nova"),
            "ocorreu_este_mes": ocorreu, "recebido_em": veio[-1][0] if veio else None, "recebido_centavos": sum(v for _, v in veio) if veio else None, "atrasada": atrasada, "dias_atraso": hoje.day - dia_limite if atrasada else 0}


def entradas_esperadas(con, hoje: dt.date) -> list[dict]:
    """Séries de entrada que o extrato mostra como normais, a de maior valor primeiro. `atrasada` = já deveria ter caído este mês."""
    inicio = f"{_mes(hoje, MESES)}-01"
    grupos: dict[str, list[tuple[str, int]]] = {}
    for r in con.execute(
            "select l.data, l.valor_centavos, l.descricao_original from lancamento l join conta c on c.id=l.conta_id "
            "where c.tipo='BANK' and c.estado='sim' and c.excluido_em is null and l.valor_centavos>=? and l.data>=? and l.data<=? "
            "and (l.natureza is null or l.natureza like '%caixa%')", (MINIMO_CENTAVOS, inicio, hoje.isoformat())):
        if EXCLUIR.search(_sem_acento(r["descricao_original"])):
            continue
        chave = _chave(r["descricao_original"])
        if chave:
            grupos.setdefault(chave, []).append((r["data"][:10], r["valor_centavos"]))
    saida = []
    for chave, creditos in grupos.items():
        for camada in _series(creditos):
            serie = _serie(chave, camada, hoje)
            if serie:
                saida.append(serie)
    return sorted(saida, key=lambda e: -e["valor_centavos"])
