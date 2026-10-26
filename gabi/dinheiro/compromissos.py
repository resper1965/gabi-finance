"""Compromissos do mes corrente e do seguinte: linhas da planilha + documentos abertos + faturas de cartao.

Em centavos (int): `fontes` (debitos, faturas, anterior) ja entrega centavos; os reais da leitura (valor_padrao,
Valores do mes, via `valores_em_centavos`) e dos documentos ({"id", "titulo", "tipo_documento", "cnpj", "valor",
"vencimento", "texto"}) viram centavos na entrada. O compromisso sai com `valor_centavos`.
Documento pertence a uma linha se `tipo_documento` == `documento` da linha, ou se o CNPJ/titulo casa com
`extrato`/`apelidos`; o mes e o do vencimento (sem vencimento: o corrente). Fora da janela, ou o segundo da mesma
linha/mes, vira avulso. Vencimento: Valores do mes > documento (no mes) > regra da linha.
"""
import calendar
import re
import unicodedata
from collections import Counter
from datetime import date

from gabi.dinheiro import emissores, previstas
from gabi.dinheiro.valor import para_centavos


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


def contem_chave(chaves, texto):
    """Alguma chave aparece no texto (chave de 14 digitos: compara so os digitos do texto)."""
    n, dig = _norm(texto), re.sub(r"\D", "", texto or "")
    return any((k in dig) if re.fullmatch(r"\d{14}", k) else (k in n) for k in chaves)


def _chaves(linha):
    return [k for k in (_chave_txt(x) for x in [linha["extrato"]] + list(linha["apelidos"])) if k]


def valores_em_centavos(valores):
    """Valores do mês da leitura (reais) com `valor_centavos` no lugar de `valor`: entrada de gerar e de conciliar."""
    return [{**{k: x for k, x in v.items() if k != "valor"}, "valor_centavos": para_centavos(v.get("valor"))}
            for v in valores]


def ultimos_pagamentos(debitos, linhas):
    """Ultimo debito (`debitos`: (descricao, valor_centavos, data, account_id, id), mais recentes primeiro) com a chave
    da linha. Varios no ultimo dia: o valor que mais se repete; empate, o maior. Linha que divide chave com outra serie
    fica sem: o debito pode ser da outra (pensao x reembolso ao mesmo favorecido)."""
    out = {}
    chaves = {ln["id"]: _chaves(ln) for ln in linhas}
    for ln in linhas:
        ch = chaves[ln["id"]]
        if any(k in o or o in k for i, ks in chaves.items() if _serie(i) != _serie(ln["id"]) for k in ch for o in ks):
            continue  # favorecido com mais de uma linha: o ultimo debito pode ser da outra; sem estimativa
        achados = [r for r in debitos if ch and contem_chave(ch, r[0])]
        if not achados:
            continue
        vezes = Counter(r[1] for r in achados)
        dia = achados[0][2][:10]
        r = max((r for r in achados if r[2][:10] == dia), key=lambda r: (vezes[r[1]], abs(r[1])))
        out[ln["id"]] = {"valor_centavos": abs(r[1]), "data": r[2][:10], "account_id": r[3]}
    return out


def _mes_ok(linha, ym):
    return linha["ativo"] and (not linha["valido_de"] or linha["valido_de"] <= ym) \
        and (not linha["valido_ate"] or ym <= linha["valido_ate"])


def _pertence(doc, linha):
    ch = _chaves(linha)
    cnpj = re.sub(r"\D", "", doc.get("cnpj") or "")
    return bool(linha["documento"] and doc.get("tipo_documento") == linha["documento"]) \
        or (len(cnpj) == 14 and cnpj in ch) \
        or bool(emissores.chave(doc.get("cnpj"), doc.get("titulo")) and contem_chave(ch, doc.get("titulo")))


def _dono_fatura(linhas, fat, ym):
    """Linha que reivindica a fatura: `cartao` contido no nome da conta; a chave mais longa, empate a primeira."""
    nome = _norm(fat["nome"])
    casam = [(len(k), -i, ln["id"]) for i, ln in enumerate(linhas)
             if _mes_ok(ln, ym) and (k := _norm(ln["cartao"])) and k in nome]
    return max(casam)[2] if casam else None


def _comp(ven, ajuste="adia", **kw):
    return {"id": None, "origem": None, "linha_id": None, "nome": None, "vencimento": ven.isoformat(),
            "vencimento_util": vencimento_util(ven, ajuste).isoformat(), "valor_centavos": None, "valor_fonte": None,
            "valor_tipo": "variavel", "forma": "", "account_id": None, "extrato_chaves": [], "cartao_account_id": None,
            "doc_id": None, "doc_ids": [], "aviso": None, "linha": None, "pix": "", "payment_status": None} | kw


def gerar(fontes, leitura, docs, hoje, invalidas=None):
    """`invalidas` (lista opcional) recebe {"linha_id", "mes", "motivo"} das instancias puladas por regra invalida."""
    linhas = leitura["linhas"]
    meses = [(hoje.year, hoje.month), (hoje.year + (hoje.month == 12), hoje.month % 12 + 1)]
    yms = [f"{a}-{m:02d}" for a, m in meses]
    ult = ultimos_pagamentos(fontes.debitos(hoje), [ln for ln in linhas if ln["ativo"]])
    valores = {(v["compromisso"], v["mes"]): v for v in sorted(valores_em_centavos(leitura["valores"]),
                                                              key=lambda v: v["linha_planilha"]) if v["tipo"] == "valor"}
    dispensados = {(d["compromisso"], d["mes"]) for d in leitura.get("dispensados", [])}
    faturas = {}
    for f in fontes.faturas():
        if f["vencimento"][:7] in yms:
            faturas.setdefault((f["account_id"], f["vencimento"][:7]), f)
    anterior = fontes.anterior()
    dono = {key: _dono_fatura(linhas, f, key[1]) for key, f in faturas.items()}  # (account_id, ym) -> linha_id
    docs_linha = {}  # (linha_id, ym) -> [doc]
    avulsos = []
    for d in sorted(docs, key=lambda d: d["id"]):
        ym = (d.get("vencimento") or hoje.isoformat())[:7]
        alvo = next((ln for ln in linhas if ym in yms and _mes_ok(ln, ym) and _pertence(d, ln)), None)
        if alvo:
            docs_linha.setdefault((alvo["id"], ym), []).append(d)
        else:
            avulsos.append(d)
    out = []
    for ano, mes in meses:
        ym = f"{ano}-{mes:02d}"
        for ln in linhas:
            if not _mes_ok(ln, ym) or (ln["id"], ym) in dispensados:
                continue
            try:
                ven = vencimento_do_mes(ln["vencimento"], ano, mes)
            except ValueError as e:
                if invalidas is not None:
                    invalidas.append({"linha_id": ln["id"], "mes": ym, "motivo": str(e)})
                continue
            vm = valores.get((ln["id"], ym))
            dl = sorted(docs_linha.get((ln["id"], ym), []), key=lambda d: d["id"], reverse=True)
            fat = next((f for key, f in faturas.items() if key[1] == ym and dono.get(key) == ln["id"]), None)
            if dl and (dl[0].get("vencimento") or "")[:7] == ym:
                ven = date.fromisoformat(dl[0]["vencimento"][:10])
            if vm and vm["vencimento"]:
                ven = date.fromisoformat(vm["vencimento"])
            # ordem do valor: Valores do mes > documento > fatura > valor_padrao > ultimo pagamento
            opcoes = [(vm and vm["valor_centavos"], "valores_do_mes"),
                      (para_centavos(next((d["valor"] for d in dl if d.get("valor") is not None), None)), "documento"),
                      (fat and fat["total_centavos"], "fatura"), (para_centavos(ln["valor_padrao"]), "padrao"),
                      ((ult.get(ln["id"]) or {}).get("valor_centavos"), "ultimo")]
            val, fonte = next(((v, f) for v, f in opcoes if v is not None), (None, None))
            ant = anterior.get(f"{ln['id']}:{ym}")
            if ant and ant[1] in ("valores_do_mes", "documento", "fatura") and fonte in (None, "padrao", "ultimo"):
                val, fonte = ant  # valor ja confirmado nao volta a ser estimativa
            out.append(_comp(ven, ln["ajuste_dia_util"], id=f"{ln['id']}:{ym}", origem="planilha", linha_id=ln["id"],
                             nome=ln["nome"], valor_centavos=val, valor_fonte=fonte, valor_tipo=ln["valor_tipo"],
                             forma=ln["forma"], extrato_chaves=_chaves(ln), cartao_account_id=fat and fat["account_id"],
                             doc_id=dl[0]["id"] if dl else None, doc_ids=[d["id"] for d in dl], linha=ln, pix=ln["pix"],
                             aviso=f"{len(dl)} documentos para o mesmo compromisso; conferir" if len(dl) > 1 else None,
                             payment_status=fat and fat["status"]))
    usadas = {(c["cartao_account_id"], c["id"][-7:]) for c in out if c["cartao_account_id"]}
    for (aid, ym), f in sorted(faturas.items()):
        if (aid, ym) not in usadas:
            out.append(_comp(date.fromisoformat(f["vencimento"]), id=f"fatura:{aid}:{ym}", origem="fatura",
                             nome=f["nome"] or f"Fatura {aid}", valor_centavos=f["total_centavos"], forma="cartão",
                             valor_fonte="fatura" if f["total_centavos"] is not None else None,
                             account_id=aid, cartao_account_id=aid, payment_status=f["status"]))
    for d in avulsos:
        ven = date.fromisoformat((d.get("vencimento") or hoje.isoformat())[:10])
        cnpj = re.sub(r"\D", "", d.get("cnpj") or "")
        k = emissores.chave(d.get("cnpj"), d.get("titulo")) and _chave_txt(cnpj if len(cnpj) == 14 else d.get("titulo"))
        out.append(_comp(ven, id=f"doc:{d['id']}:{ven:%Y-%m}", origem="documento",
                         nome=d.get("titulo") or f"Documento {d['id']}", valor_centavos=para_centavos(d.get("valor")),
                         valor_fonte="documento" if d.get("valor") is not None else None,
                         extrato_chaves=[k] if k else [], doc_id=d["id"], doc_ids=[d["id"]]))
    out.sort(key=lambda x: (x["vencimento_util"], x["id"]))
    return out
