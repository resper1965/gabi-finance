"""Compromissos do mes corrente e do seguinte: linhas da planilha + documentos abertos + faturas de cartao.

Portado do gabi-fin/compromissos.py SEM alterar a lógica. O acesso a banco virou `fontes` (debitos, faturas, anterior).

Documento (entrada `docs`, dicts; a Task 8 adapta o que vem do Paperless):
  {"id": int, "titulo": str, "tipo_documento": str|None, "cnpj": str|None,
   "valor": float|None, "vencimento": "AAAA-MM-DD"|None, "texto": str}
Um documento pertence a uma linha se `tipo_documento` == `documento` da linha, ou se o CNPJ/titulo
(normalizado) casa com `extrato`/`apelidos`. O mes do documento e o do seu vencimento (sem vencimento: mes corrente).
Documento de mes fora da janela, ou o segundo da mesma linha/mes, vira avulso (nao some).

Vencimento: o dia vem da regra da linha. Datas explicitas mandam sobre a regra, na ordem
`Valores do mes` (vencimento) > documento (vencimento no mes) > regra.
"""
import calendar
import json
import re
import unicodedata
from datetime import date

from gabi.dinheiro import emissores, previstas


def _serie(id_):
    """Base do id: `x`, `x-202611` (mudanca --a-partir) e `x-202611-202703` sao a mesma serie. So dentro da serie
    a sobreposicao de meses e conflito; ids diferentes com o mesmo extrato sao compromissos distintos."""
    return re.sub(r"(-\d{6})+$", "", id_)


def vencimento_do_mes(regra, ano, mes):
    """'5du' = 5o dia util do mes; 'dia:N' = dia N (limitado ao tamanho do mes). Ainda sem ajuste de dia nao util."""
    r = "".join(str(regra or "").lower().split())
    m = re.fullmatch(r"(\d+)du", r)
    if m:
        n = int(m.group(1))
        uteis = sum(1 for k in range(1, calendar.monthrange(ano, mes)[1] + 1)
                    if date(ano, mes, k).weekday() < 5 and date(ano, mes, k) not in previstas.feriados(ano))
        if not 1 <= n <= uteis:
            raise ValueError(f"{n}du fora do mes (1 a {uteis} dias uteis)")
        return previstas.dia_util(ano, mes, n)
    m = re.fullmatch(r"dia:(\d+)", r)
    if m:
        return date(ano, mes, min(int(m.group(1)), calendar.monthrange(ano, mes)[1]))
    raise ValueError(f"regra de vencimento invalida: {regra!r}")


def vencimento_util(d, ajuste="adia"):
    """Fim de semana ou feriado nacional: 'adia' vai ao proximo dia util, 'antecipa' ao anterior."""
    passo = -1 if ajuste == "antecipa" else 1
    while d.weekday() >= 5 or d in previstas.feriados(d.year):
        d = date.fromordinal(d.toordinal() + passo)
    return d


def _norm(x):
    """Sem acento, maiusculas, pontuacao vira espaco, digitos mantidos, sem truncar."""
    s = "".join(c for c in unicodedata.normalize("NFKD", x or "") if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", s.upper()).split())


def _chave_txt(x):
    d = re.sub(r"\D", "", x or "")
    return d if len(d) == 14 and not re.search(r"[A-Za-z]", x or "") else _norm(x)  # CNPJ puro guarda os digitos


def _contem(chaves, texto):
    """Alguma chave aparece no texto (chave de 14 digitos: compara so os digitos do texto)."""
    n, dig = _norm(texto), re.sub(r"\D", "", texto or "")
    return any((k in dig) if re.fullmatch(r"\d{14}", k) else (k in n) for k in chaves)


def _chaves(linha):
    return [k for k in (_chave_txt(x) for x in [linha["extrato"]] + list(linha["apelidos"])) if k]


def ultimos_pagamentos(debitos, linhas):
    """Ultimo debito BANK (conta nao PJ) cuja descricao contem o extrato/apelido da linha. Varios no ultimo dia
    (ex.: dois Pix ao mesmo favorecido): fica o valor que mais se repete nos debitos da linha; empate, o maior.
    Linha que divide chave com outra linha ativa de outra serie (uma contem a outra; a linha e a sucessora do
    --a-partir sao a mesma serie, planilha._serie) fica sem ultimo pagamento: o debito pode ser
    da outra (pensao x reembolso ao mesmo favorecido); vale o valor_padrao ou nada."""
    rows = debitos  # [(descricao, valor, data, account_id, id)] de débitos BANK não-PJ até hoje, mais recentes primeiro
    out = {}
    chaves = {ln["id"]: _chaves(ln) for ln in linhas}
    for ln in linhas:
        ch = chaves[ln["id"]]
        if any(k in o or o in k for i, ks in chaves.items() if _serie(i) != _serie(ln["id"]) for k in ch for o in ks):
            continue  # favorecido com mais de uma linha: o ultimo debito pode ser da outra; sem estimativa
        achados = [r for r in rows if ch and _contem(ch, r[0])]
        if not achados:
            continue
        vezes = {}
        for r in achados:
            vezes[round(r[1], 2)] = vezes.get(round(r[1], 2), 0) + 1
        dia = achados[0][2][:10]
        r = max((r for r in achados if r[2][:10] == dia), key=lambda r: (vezes[round(r[1], 2)], abs(r[1])))
        out[ln["id"]] = {"valor": abs(r[1]), "data": r[2][:10], "account_id": r[3]}
    return out


def _mes_ok(linha, ym):
    return linha["ativo"] and (not linha["valido_de"] or linha["valido_de"] <= ym) \
        and (not linha["valido_ate"] or ym <= linha["valido_ate"])


def _pertence(doc, linha):
    if linha["documento"] and doc.get("tipo_documento") == linha["documento"]:
        return True
    ch = _chaves(linha)
    cnpj = re.sub(r"\D", "", doc.get("cnpj") or "")
    if len(cnpj) == 14 and cnpj in ch:
        return True
    if emissores.chave(doc.get("cnpj"), doc.get("titulo")) and _contem(ch, doc.get("titulo")):
        return True
    return False


def _casa_cartao(linha, fat):
    """Tamanho da chave do cartao se casa com o nome da conta (para preferir a mais longa), senao 0."""
    k = _norm(linha["cartao"])
    return len(k) if k and k in _norm(fat["nome"]) else 0


def gerar(fontes, leitura, docs, hoje, invalidas=None):
    """`invalidas` (lista opcional) recebe {"linha_id", "mes", "motivo"} das instancias puladas por regra invalida."""
    linhas = leitura["linhas"]
    meses = [(hoje.year, hoje.month), (hoje.year + (hoje.month == 12), hoje.month % 12 + 1)]
    yms = [f"{a}-{m:02d}" for a, m in meses]
    ult = ultimos_pagamentos(fontes.debitos(hoje), [ln for ln in linhas if ln["ativo"]])
    valores = {}
    for v in sorted(leitura["valores"], key=lambda v: v["linha_planilha"]):
        if v["tipo"] == "valor":
            valores[(v["compromisso"], v["mes"])] = v
    faturas = {}
    for f in fontes.faturas():
        if f["vencimento"][:7] in yms:
            faturas.setdefault((f["account_id"], f["vencimento"][:7]), f)
    anterior = fontes.anterior()
    usadas = set()
    dono = {}  # (account_id, ym) -> linha que reivindica a fatura (chave de cartao mais longa)
    for key, f in faturas.items():
        melhor = max(((_casa_cartao(ln, f), -i, ln["id"]) for i, ln in enumerate(linhas) if _mes_ok(ln, key[1])), default=(0,))
        if melhor[0]:
            dono[key] = melhor[2]
    docs_linha = {}  # (linha_id, ym) -> doc
    avulsos = []
    for d in sorted(docs, key=lambda d: d["id"]):
        ym = (d.get("vencimento") or hoje.isoformat())[:7]
        alvo = next((ln for ln in linhas if ym in yms and _mes_ok(ln, ym) and _pertence(d, ln)), None)
        if alvo:
            docs_linha.setdefault((alvo["id"], ym), []).append(d)
        else:
            avulsos.append(d)

    def comp(**kw):
        base = {"id": None, "origem": None, "linha_id": None, "nome": None, "vencimento": None, "vencimento_util": None,
                "valor": None, "valor_fonte": None, "valor_tipo": "variavel", "forma": "", "account_id": None,
                "extrato_chaves": [], "cartao_account_id": None, "doc_id": None, "doc_ids": [], "aviso": None, "linha": None, "pix": "",
                "payment_status": None}
        base.update(kw)
        return base

    out = []
    for ano, mes in meses:
        ym = f"{ano}-{mes:02d}"
        for ln in linhas:
            if not _mes_ok(ln, ym):
                continue
            try:
                ven = vencimento_do_mes(ln["vencimento"], ano, mes)
            except ValueError as e:
                if invalidas is not None:
                    invalidas.append({"linha_id": ln["id"], "mes": ym, "motivo": str(e)})
                continue
            val, fonte, doc_id, status, cartao, aviso = None, None, None, None, None, None
            vm = valores.get((ln["id"], ym))
            dl = sorted(docs_linha.get((ln["id"], ym), []), key=lambda d: d["id"], reverse=True)
            doc = dl[0] if dl else None
            if len(dl) > 1:
                aviso = f"{len(dl)} documentos para o mesmo compromisso; conferir"
            fat = next((f for key, f in faturas.items() if key[1] == ym and dono.get(key) == ln["id"]), None)
            if fat:
                usadas.add((fat["account_id"], ym))
                cartao, status = fat["account_id"], fat["status"]
            if doc:
                doc_id = doc["id"]
                if doc.get("vencimento") and doc["vencimento"][:7] == ym:
                    ven = date.fromisoformat(doc["vencimento"][:10])
            if vm and vm["vencimento"]:
                ven = date.fromisoformat(vm["vencimento"])
            if vm and vm["valor"] is not None:
                val, fonte = vm["valor"], "valores_do_mes"
            elif next((d for d in dl if d.get("valor") is not None), None):
                val, fonte = next(d for d in dl if d.get("valor") is not None)["valor"], "documento"
            elif fat and fat["total"] is not None:
                val, fonte = fat["total"], "fatura"
            elif ln["valor_padrao"] is not None:
                val, fonte = ln["valor_padrao"], "padrao"
            elif ln["id"] in ult:
                val, fonte = ult[ln["id"]]["valor"], "ultimo"
            ant = anterior.get(f"{ln['id']}:{ym}")
            if ant and ant[1] in ("valores_do_mes", "documento", "fatura") and fonte in (None, "padrao", "ultimo"):
                val, fonte = ant  # valor ja confirmado nao volta a ser previsto
            out.append(comp(id=f"{ln['id']}:{ym}", origem="planilha", linha_id=ln["id"], nome=ln["nome"],
                            vencimento=ven.isoformat(), vencimento_util=vencimento_util(ven, ln["ajuste_dia_util"]).isoformat(),
                            valor=val, valor_fonte=fonte, valor_tipo=ln["valor_tipo"], forma=ln["forma"],
                            extrato_chaves=_chaves(ln), cartao_account_id=cartao, doc_id=doc_id, doc_ids=[d["id"] for d in dl], aviso=aviso, linha=ln,
                            pix=ln["pix"], payment_status=status))
    for (aid, ym), f in sorted(faturas.items()):
        if (aid, ym) in usadas:
            continue
        ven = date.fromisoformat(f["vencimento"])
        out.append(comp(id=f"fatura:{aid}:{ym}", origem="fatura", nome=f["nome"] or f"Fatura {aid}",
                        vencimento=ven.isoformat(), vencimento_util=vencimento_util(ven).isoformat(),
                        valor=f["total"], valor_fonte="fatura" if f["total"] is not None else None, forma="cartão",
                        account_id=aid, cartao_account_id=aid, payment_status=f["status"]))
    for d in avulsos:
        ven = date.fromisoformat((d.get("vencimento") or hoje.isoformat())[:10])
        k = emissores.chave(d.get("cnpj"), d.get("titulo")) and _chave_txt(re.sub(r"\D", "", d.get("cnpj") or "") if len(re.sub(r"\D", "", d.get("cnpj") or "")) == 14 else d.get("titulo"))
        out.append(comp(id=f"doc:{d['id']}:{ven:%Y-%m}", origem="documento", nome=d.get("titulo") or f"Documento {d['id']}",
                        vencimento=ven.isoformat(), vencimento_util=vencimento_util(ven).isoformat(),
                        valor=d.get("valor"), valor_fonte="documento" if d.get("valor") is not None else None,
                        extrato_chaves=[k] if k else [], doc_id=d["id"], doc_ids=[d["id"]]))
    out.sort(key=lambda x: (x["vencimento_util"], x["id"]))
    return out
