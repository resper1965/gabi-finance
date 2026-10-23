"""Conciliação: marca cada compromisso como pago, aberto, atrasado ou a_conferir casando com o extrato.

Função pura `conciliar`, em centavos (int); a gravação vive em dinheiro/repositorio.py. Números vêm dos Parâmetros.
Ordem: 1. vínculo gravado; 2. candidatos: débito BANK não PJ até hoje, sem transferência própria, não vinculado;
3. casamento por favorecido/emissor, senão por valor (|dif| <= tolerancia_valor = pago; só lançamento sem chave de
ninguém; pagamento de fatura só paga fatura), em duas passadas por (vencimento_util, id): primeiro só valor conhecido
(fixo ou confirmado) com lançamento que encaixa, depois o resto; o que encaixa, depois a data mais próxima, depois o id;
4. fixo ou confirmado fora da tolerancia_fixo = a_conferir, sem vínculo; 5. fatura PAID e baixa manual = pago, também
sobre o a_conferir; senão débito automático (aberto), extrato parado (a_conferir), atrasado, aberto.
"""
import datetime as dt
import re

from gabi.dinheiro import caixa
from gabi.dinheiro.compromissos import _norm, _serie, contem_chave

CONFIRMADO = {"valores_do_mes", "documento", "fatura"}
_VAZIO = {"estado": None, "metodo": None, "tx_id": None, "pago_em": None, "diferenca_centavos": None, "motivo": None}


def _dia(s):
    return dt.date.fromisoformat(str(s)[:10])


def _ddmm(s):
    return _dia(s).strftime("%d/%m")


def _brl(centavos):
    return "R$ " + f"{centavos / 100:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _eh_fatura(comp):
    return comp.get("origem") == "fatura" or comp.get("forma") in ("fatura", "cartão") \
        or bool(comp.get("cartao_account_id"))


def _nome_cartao(comp):
    return (comp.get("linha") or {}).get("cartao") or (comp.get("nome") if comp.get("origem") == "fatura" else "") or ""


def _casa_emissor(nome, desc):
    """Pagamento de fatura (caixa.FATURA_RE) com o nome do cartão, aceitando o corte do banco: de um início de palavra,
    coincide com o começo do nome por >= min(len(nome), 10) caracteres e termina em fim de palavra ou da descrição."""
    k, n = _norm(nome), _norm(desc)
    if not k or not caixa.FATURA_RE.search(desc or ""):
        return False
    alvo = min(len(k), 10)
    for i in [0] + [m.end() for m in re.finditer(" ", n)]:
        L = 0
        while L < len(k) and i + L < len(n) and n[i + L] == k[L]:
            L += 1
        if i + L < len(n) and n[i + L] != " ":  # parou no meio de uma palavra: recua ao fim da palavra anterior
            L = max(n.rfind(" ", i, i + L) - i, 0)
        if L >= alvo:
            return True
    return False


def _metodo_chave(comp, tx):
    if comp.get("extrato_chaves") and contem_chave(comp["extrato_chaves"], tx.get("descricao")):
        return "favorecido"
    if _eh_fatura(comp) and _casa_emissor(_nome_cartao(comp), tx.get("descricao")):
        return "emissor"
    return None


def _conhecido(comp):
    """Valor fixo, ou confirmado por Valores do mês/documento/fatura."""
    return comp.get("valor_centavos") is not None \
        and (comp.get("valor_tipo") == "fixo" or comp.get("valor_fonte") in CONFIRMADO)


def _avalia(comp, pago, p):
    """(estado, diferenca_centavos, motivo) do casamento de `pago` centavos com o compromisso."""
    v = comp.get("valor_centavos")
    if v is None:
        return "pago", None, None
    d = pago - v
    if not _conhecido(comp) or abs(d) <= round(p["tolerancia_fixo"] * v):
        return "pago", d, None
    if d > 0:
        return "a_conferir", d, f"pago acima: {_brl(pago)} de {_brl(v)}"
    menor = "pago a menor (mínimo?)" if _eh_fatura(comp) else "pago a menor"
    return "a_conferir", d, f"{menor}: {_brl(pago)} de {_brl(v)}"


def _corrente(e):
    return (e.get("tipo") or "BANK") == "BANK" and not e.get("pj")


def _neutro(tx, donos):
    return tx.get("natureza") == "neutro" or bool(donos) and caixa.natureza(
        tx.get("tipo_conta"), tx.get("descricao"), tx.get("categoria"), tx["valor_centavos"], donos) == "neutro"


def _ts(s, agora):
    t = dt.datetime.fromisoformat(s)
    if (t.tzinfo is None) != (agora.tzinfo is None):
        t = t.replace(tzinfo=agora.tzinfo)
    return t


def _parada(comp, estado_contas, p, agora):
    """Motivo 'extrato parado desde dd/mm' se as contas pagadoras estão todas paradas, senão None. Pagadoras: a conta
    do compromisso se for BANK; senão as correntes não PJ cujo banco/nome contém a `conta` da linha; senão todas."""
    bancos = {aid: e for aid, e in estado_contas.items() if _corrente(e)}
    conta = _norm((comp.get("linha") or {}).get("conta"))
    if comp.get("account_id") in bancos:
        alvo = [bancos[comp["account_id"]]]
    else:
        alvo = [e for e in bancos.values() if conta and conta in _norm(f"{e.get('banco') or ''} {e.get('nome') or ''}")]
        alvo = alvo or list(bancos.values())
    if not alvo:
        return None
    limite = dt.timedelta(hours=p["horas_conta_parada"])
    if any(e.get("ult_sync_ok") and agora - _ts(e["ult_sync_ok"], agora) <= limite for e in alvo):
        return None
    ult = max((e["ult_sync_ok"] for e in alvo if e.get("ult_sync_ok")), default=None) \
        or max((e["ult_tx_real"] for e in alvo if e.get("ult_tx_real")), default=None)
    return f"extrato parado desde {_ddmm(ult)}" if ult else "extrato parado (sem sincronização registrada)"


def conciliar(comps, txs, vinculos, estado_contas, pagos, params, hoje, agora, donos=None):
    """-> ({comp_id: {estado, metodo, tx_id, pago_em, diferenca_centavos, motivo}},
    [(tx_id, comp_id, metodo, diferenca_centavos)]). `vinculos`: {tx_id: comp_id} já gravados. `pagos`: Valores do
    mês em centavos (compromissos.valores_em_centavos). `donos`: opcional, caixa.dono_tokens dos titulares."""
    p = params
    por_id = {t["id"]: t for t in txs}
    res = {c["id"]: dict(_VAZIO) for c in comps}
    novos = []

    # 1. vínculo gravado
    ligados = {t for t in vinculos if not str(t).startswith("manual:")}
    pago_vinculo = {vinculos[t]: t for t in sorted(ligados, reverse=True)}  # o de menor id, se houver mais de um
    for comp in comps:
        if t := pago_vinculo.get(comp["id"]):
            tx = por_id.get(t)
            metodo = (_metodo_chave(comp, tx) or "valor") if tx else "vinculo"
            d = _avalia(comp, abs(tx["valor_centavos"]), p)[1] if tx else None
            res[comp["id"]].update(estado="pago", tx_id=t, metodo=metodo, pago_em=tx and tx["data"][:10],
                                   diferenca_centavos=d)

    # 2. candidatos
    pool = [t for t in txs if t.get("tipo_conta") == "BANK" and t["valor_centavos"] < 0 and t["id"] not in ligados
            and t["data"][:10] <= hoje.isoformat() and not (estado_contas.get(t["account_id"]) or {}).get("pj")
            and not _neutro(t, donos)]
    com_chave = {t["id"] for t in pool for c in comps if _metodo_chave(c, t)}
    tol_valor = round(p["tolerancia_valor"] * 100)

    def na_janela(comp, tx):
        return _dia(comp["vencimento_util"]) - dt.timedelta(days=p["janela_antes_dias"]) <= _dia(tx["data"]) <= hoje

    usados = set()

    def candidatos(comp):
        """[(tx, metodo, (estado, dif, motivo))]: por favorecido/emissor; sem nenhum, por valor (pago, sem conferência)."""
        livres = [t for t in pool if t["id"] not in usados and na_janela(comp, t)]
        cands = [(t, m, _avalia(comp, abs(t["valor_centavos"]), p))
                 for t in livres for m in [_metodo_chave(comp, t)] if m]
        if cands or comp.get("valor_centavos") is None:
            return cands
        v = comp["valor_centavos"]
        return [(t, "valor", ("pago", abs(t["valor_centavos"]) - v, None)) for t in livres
                if t["id"] not in com_chave and abs(abs(t["valor_centavos"]) - v) <= tol_valor
                and (_eh_fatura(comp) or not caixa.FATURA_RE.search(t.get("descricao") or ""))]

    def de_mes_anterior(comp, tx):
        """O lançamento está na janela de um mês anterior ainda sem casamento da mesma linha (Pix atrasado)."""
        serie = comp.get("linha_id") and _serie(comp["linha_id"])
        return bool(serie) and any(
            res[c["id"]]["estado"] is None and c.get("linha_id") and _serie(c["linha_id"]) == serie
            and c["vencimento_util"] < comp["vencimento_util"] and na_janela(c, tx) for c in comps)

    # 3-4. casamento em duas passadas, cada uma por (vencimento_util, id): primeiro só valor conhecido com lançamento
    # que encaixa e não é Pix atrasado de mês anterior da mesma linha (a estimativa e o valor que não encaixa não
    # roubam o lançamento certo); depois o resto
    for passada in (1, 2):
        for comp in sorted((c for c in comps if res[c["id"]]["estado"] is None),
                           key=lambda c: (c["vencimento_util"], c["id"])):
            if passada == 1 and not _conhecido(comp):
                continue
            venc = _dia(comp["vencimento_util"])
            cands = [c for c in candidatos(comp)
                     if passada == 2 or (c[2][0] == "pago" and not de_mes_anterior(comp, c[0]))]
            if not cands:
                continue
            # o que encaixa ganha da data mais próxima; empate, o id menor
            tx, metodo, (estado, d, motivo) = min(
                cands, key=lambda c: (c[2][0] != "pago", abs((_dia(c[0]["data"]) - venc).days), c[0]["id"]))
            usados.add(tx["id"])
            res[comp["id"]].update(estado=estado, metodo=metodo, tx_id=tx["id"], pago_em=tx["data"][:10],
                                   diferenca_centavos=d, motivo=motivo)
            if estado == "pago":
                novos.append((tx["id"], comp["id"], metodo, d))

    # 5. sem lançamento pago: fatura PAID e baixa manual valem também sobre o a_conferir; senão pelo vencimento
    manuais = {(v["compromisso"], v["mes"]): v for v in pagos if v.get("tipo") == "pago"}
    for comp in comps:
        r, cid = res[comp["id"]], comp["id"]
        if r["estado"] not in (None, "a_conferir"):
            continue
        # compromisso de linha tem id `linha:AAAA-MM`
        v = manuais.get((comp.get("linha_id"), cid[-7:])) if comp.get("linha_id") else None
        if _eh_fatura(comp) and str(comp.get("payment_status") or "").upper() == "PAID":
            # o banco diz que está paga: mantém o lançamento do casamento, sem vínculo nem diferença
            r.update(estado="pago", metodo="banco", motivo=None, diferenca_centavos=None)
        elif v:
            pago, valor = v.get("valor_centavos"), comp.get("valor_centavos")
            d = pago - valor if pago is not None and valor is not None else None
            r.update(estado="pago", metodo="manual", tx_id=f"manual:{cid}", pago_em=v.get("data_pagamento"),
                     diferenca_centavos=d, motivo=None)
            novos.append((f"manual:{cid}", cid, "manual", d))
        elif r["estado"]:
            continue  # a_conferir do casamento
        elif hoje > _dia(comp["vencimento_util"]) and comp.get("forma") != "debito_automatico":
            mot = _parada(comp, estado_contas, p, agora)
            if mot:
                r.update(estado="a_conferir", motivo=mot)
            else:
                r["estado"] = "atrasado"
        else:
            r["estado"] = "aberto"  # não venceu, ou débito automático ainda sem lançamento
    return res, novos
