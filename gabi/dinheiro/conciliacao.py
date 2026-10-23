"""Conciliação: marca cada compromisso como pago, aberto, atrasado ou a_conferir casando com o extrato.

Função pura `conciliar`, em centavos (int); a gravação vive em dinheiro/repositorio.py. Números vêm dos Parâmetros.
Ordem: 1. vínculo gravado; 2. candidatos (débito BANK não PJ até hoje, sem transferência própria, não vinculado);
3. por (vencimento_util, id), cada compromisso pega o candidato livre na janela mais próximo do vencimento, por
favorecido/emissor do cartão, senão por valor (só lançamento sem chave de ninguém; pagamento de fatura só paga fatura);
4. valor fixo ou confirmado fora da tolerancia_fixo = a_conferir, sem vínculo; 5. sem lançamento: fatura PAID, baixa
manual, débito automático (aberto), extrato parado (a_conferir), atrasado, aberto.
"""
import datetime as dt
import re

from gabi.dinheiro import caixa
from gabi.dinheiro.compromissos import _norm, contem_chave
from gabi.dinheiro.valor import para_centavos

CONFIRMADO = {"valores_do_mes", "documento", "fatura"}
_VAZIO = {"estado": None, "metodo": None, "tx_id": None, "pago_em": None, "diferenca_centavos": None, "motivo": None}


def _dia(s):
    return dt.date.fromisoformat(str(s)[:10])


def _ddmm(s):
    return _dia(s).strftime("%d/%m")


def _brl(centavos):
    return "R$ " + f"{centavos / 100:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _ym(comp):
    m = re.search(r":(\d{4}-\d{2})$", comp["id"])
    return m.group(1) if m else comp["vencimento"][:7]


def _eh_fatura(comp):
    return comp.get("origem") == "fatura" or comp.get("forma") in ("fatura", "cartão") or bool(comp.get("cartao_account_id"))


def _nome_cartao(comp):
    return (comp.get("linha") or {}).get("cartao") or (comp.get("nome") if comp.get("origem") == "fatura" else "") or ""


def _casa_emissor(nome, desc):
    """Pagamento de fatura (caixa.FATURA_RE) cuja descrição traz o nome do cartão, aceitando o corte do banco:
    a partir de um início de palavra, o texto coincide com o começo do nome por >= min(len(nome), 10) caracteres,
    terminando em fim de palavra ou no fim da descrição."""
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


def _avalia(comp, pago, p):
    """(estado, diferenca_centavos, motivo) do casamento de `pago` centavos com o compromisso."""
    v = comp.get("valor_centavos")
    if v is None:
        return "pago", None, None
    d = pago - v
    confirmado = comp.get("valor_tipo") == "fixo" or comp.get("valor_fonte") in CONFIRMADO
    if not confirmado or abs(d) <= round(p["tolerancia_fixo"] * v):
        return "pago", d, None
    if d > 0:
        return "a_conferir", d, f"pago acima: {_brl(pago)} de {_brl(v)}"
    menor = "pago a menor (mínimo?)" if _eh_fatura(comp) else "pago a menor"
    return "a_conferir", d, f"{menor}: {_brl(pago)} de {_brl(v)}"


def _corrente(e):
    return (e.get("tipo") or "BANK") == "BANK" and not e.get("pj")


def _neutro(tx, donos):
    if tx.get("natureza") == "neutro":
        return True
    return bool(donos) and caixa.natureza(tx.get("tipo_conta"), tx.get("descricao"), tx.get("categoria"),
                                           tx["valor_centavos"], donos) == "neutro"


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
    mês (reais, da leitura). `donos`: opcional, caixa.dono_tokens dos titulares."""
    p = params
    por_id = {t["id"]: t for t in txs}
    res = {c["id"]: dict(_VAZIO) for c in comps}
    novos = []

    # 1. vínculo gravado
    ligados = {t for t in vinculos if not str(t).startswith("manual:")}
    pago_vinculo = {}
    for t in sorted(ligados):
        pago_vinculo.setdefault(vinculos[t], t)
    for comp in comps:
        t = pago_vinculo.get(comp["id"])
        if t:
            tx = por_id.get(t)
            res[comp["id"]].update(estado="pago", tx_id=t, metodo="vinculo")
            if tx:
                _, d, _ = _avalia(comp, abs(tx["valor_centavos"]), p)
                res[comp["id"]].update(metodo=_metodo_chave(comp, tx) or "valor", pago_em=tx["data"][:10], diferenca_centavos=d)

    # 2. candidatos
    pool = [t for t in txs if t.get("tipo_conta") == "BANK" and t["valor_centavos"] < 0 and t["id"] not in ligados
            and t["data"][:10] <= hoje.isoformat() and not (estado_contas.get(t["account_id"]) or {}).get("pj")
            and not _neutro(t, donos)]
    com_chave = {t["id"] for t in pool for c in comps if _metodo_chave(c, t)}
    tol_valor = round(p["tolerancia_valor"] * 100)

    def na_janela(comp, tx):
        return _dia(comp["vencimento_util"]) - dt.timedelta(days=p["janela_antes_dias"]) <= _dia(tx["data"]) <= hoje

    # 3-4. casamento por favorecido, senão por valor
    usados = set()
    for comp in sorted((c for c in comps if res[c["id"]]["estado"] is None), key=lambda c: (c["vencimento_util"], c["id"])):
        livres = [t for t in pool if t["id"] not in usados and na_janela(comp, t)]
        cands = [(t, m) for t in livres for m in [_metodo_chave(comp, t)] if m]
        if not cands and comp.get("valor_centavos") is not None:
            cands = [(t, "valor") for t in livres if t["id"] not in com_chave
                     and abs(abs(t["valor_centavos"]) - comp["valor_centavos"]) <= tol_valor
                     and (_eh_fatura(comp) or not caixa.FATURA_RE.search(t.get("descricao") or ""))]
        if not cands:
            continue
        tx, metodo = min(cands, key=lambda x: (abs((_dia(x[0]["data"]) - _dia(comp["vencimento_util"])).days), x[0]["id"]))
        usados.add(tx["id"])
        estado, d, motivo = _avalia(comp, abs(tx["valor_centavos"]), p)
        res[comp["id"]].update(estado=estado, metodo=metodo, tx_id=tx["id"], pago_em=tx["data"][:10],
                               diferenca_centavos=d, motivo=motivo)
        if estado == "pago":
            novos.append((tx["id"], comp["id"], metodo, d))

    # 5. sem lançamento
    manuais = {(v["compromisso"], v["mes"]): v for v in pagos if v.get("tipo") == "pago"}
    for comp in comps:
        r, cid = res[comp["id"]], comp["id"]
        if r["estado"] is not None:
            continue
        v = manuais.get((comp.get("linha_id"), _ym(comp))) if comp.get("linha_id") else None
        if _eh_fatura(comp) and str(comp.get("payment_status") or "").upper() == "PAID":
            r.update(estado="pago", metodo="banco")
        elif v:
            pago = para_centavos(v.get("valor"))  # Valores do mês chegam em reais (leitura)
            d = pago - comp["valor_centavos"] if pago is not None and comp.get("valor_centavos") is not None else None
            r.update(estado="pago", metodo="manual", tx_id=f"manual:{cid}", pago_em=v.get("data_pagamento"), diferenca_centavos=d)
            novos.append((f"manual:{cid}", cid, "manual", d))
        elif comp.get("forma") == "debito_automatico":
            r["estado"] = "aberto"
        elif hoje > _dia(comp["vencimento_util"]):
            mot = _parada(comp, estado_contas, p, agora)
            r.update(estado="a_conferir", motivo=mot) if mot else r.update(estado="atrasado")
        else:
            r["estado"] = "aberto"
    return res, novos
