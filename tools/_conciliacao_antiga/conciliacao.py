"""Conciliacao: marca cada compromisso como pago/aberto/atrasado/a conferir casando com o extrato.

Função pura `conciliar`; a gravação vive em dinheiro/repositorio.py. Portado do gabi-fin/conciliacao.py SEM alterar a lógica. Todos os numeros vem de Parametros da planilha.

Regras, na ordem:
  0. Vinculo persistido (`conciliacao` no fin.db) vale primeiro: o compromisso fica pago e o lancamento sai do jogo.
     Vinculo `manual:` nao e honrado daqui: a baixa manual e refeita a cada rodada pela planilha (regra 8).
  1. Janela: debito (valor < 0) de conta BANK nao PJ (`pj`=1 em estado_contas; conta sem linha = nao PJ), com data de
     vencimento_util - janela_antes_dias ate `hoje`. Fora: transferencia propria (natureza 'neutro' gravada na captura,
     ou recalculada com `donos` = caixa.dono_tokens(...) quando passado) e lancamento ja vinculado.
     Pagamento antes do mes do compromisso conta se estiver na janela.
  2. Por favorecido: a descricao contem alguma `extrato_chaves` ("favorecido"); compromisso de fatura tambem casa
     pelo nome do cartao num pagamento de fatura ("emissor", ver `_casa_emissor`).
       fixo: |dif| <= tolerancia_fixo * valor; acima ate tolerancia_juros * valor = pago com juros;
             fora disso = a conferir (pago a menor / acima) — nao vira vinculo persistente.
       variavel: qualquer valor, menos pagamento abaixo do valor confirmado (Valores do mes, documento, fatura)
             alem da tolerancia_fixo: a conferir ("pago a menor"; fatura: "pago a menor (mínimo?)"). Sem valor: pago.
       Emissor ambiguo (a descricao casa mais de um nome de cartao, dos compromissos ou das contas CREDIT):
             so paga com o valor dentro da tolerancia_fixo (sem margem de juros); senao a conferir.
     Faixa de juros (acima de tolerancia_fixo * valor ate tolerancia_juros * valor) conta como encaixe para qualquer
     valor, inclusive estimativa de variavel; o valor dos juros so e registrado com valor fixo ou confirmado.
     Estimativa x valor conhecido e decidido na regra 4 (certeza), nao no encaixe.
  3. Por valor, so para o que sobrou e so com lancamento que nao casa favorecido de NENHUM compromisso:
     |dif| <= tolerancia_valor ("valor"). Pagamento de fatura (caixa.FATURA_RE) so paga compromisso de fatura.
  4. Empate: cada lancamento paga no maximo um compromisso e cada compromisso recebe no maximo um lancamento.
     Atribuicao gulosa por (encaixe do valor, certeza da linha, ja vencido na data do lancamento antes de ainda nao
     vencido, distancia da data ao vencimento_util, |dif|): o valor que encaixa ganha (favorecido ambiguo); entre
     linhas diferentes, valor conhecido (fixo ou confirmado) ganha de estimativa (ver `_ordenar`); pagamento
     atrasado fica com o mes vencido, nao com o seguinte. O compromisso que ficou sem lancamento por ter perdido
     um candidato vai para a conferir (lancamento no motivo) so se ja venceu (vencimento_util < hoje) e o
     vencedor nao ganhou por encaixe estritamente melhor; senao segue o estado por data.
  5. Pago a menor: a conferir (regra 2).
  6. Fatura: payment_status PAID = pago ("banco"); ou debito da corrente ao emissor (regras 2/3).
  7. Debito automatico (forma debito_automatico): estado 'debito_automatico' ate o debito aparecer; nunca atrasado.
  8. Baixa manual: Valor tipo 'pago' da linha no mes = pago ("manual", tx_id "manual:<comp_id>"). O compromisso
     com baixa manual disputa lancamentos como os outros: achado no extrato, vale o extrato (vinculo persistido);
     a linha manual so vale sem lancamento (inclusive sobre a conferir). Assim o Pix atrasado do mes pago a mao
     nao sobra para o mes seguinte. Mas so tem a prioridade de "ja vencido" (regra 4) com lancamento do mesmo
     mes do vencimento_util; fora dele disputa so pelo vencimento mais proximo.

Estados do que nao foi pago:
  atrasado   hoje > vencimento_util (a partir do dia seguinte, sem tolerancia);
  aberto     vence hoje, ou vence depois com valor conhecido (fixo com valor, ou valor confirmado);
  previsto   vence depois e o valor e so estimativa (padrao de variavel, ultimo pagamento) ou nao ha valor.
Conta parada: o que seria atrasado vira a_conferir ("extrato parado desde dd/mm") se a ultima sincronizacao ok
(`ult_sync_ok`) das contas pagadoras e mais velha que horas_conta_parada (em relacao a `agora`). Contas pagadoras:
a conta do compromisso se for BANK; senao as correntes nao PJ cujo banco/nome contem a coluna `conta` da linha;
senao todas as correntes nao PJ. Parada so se TODAS as pagadoras estao paradas. Sem nenhuma corrente conhecida: nao parada.
"""
import datetime as dt
import json
import re

from gabi.dinheiro import caixa
from tools._conciliacao_antiga.compromissos import _contem, _norm, _serie


CONFIRMADO = {"valores_do_mes", "documento", "fatura"}
_EPS = 1e-9
_VAZIO = {"estado": None, "metodo": None, "tx_id": None, "pago_em": None, "diferenca": None, "juros": None, "motivo": None}


def _dia(s):
    return dt.date.fromisoformat(str(s)[:10])


def _ddmm(s):
    return _dia(s).strftime("%d/%m")


def _brl(x):
    return "R$ " + f"{x:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _r2(x):
    return round(x, 2) + 0.0  # sem -0.0


def _ym(comp):
    m = re.search(r":(\d{4}-\d{2})$", comp["id"])
    return m.group(1) if m else comp["vencimento"][:7]


def _eh_fatura(comp):
    return comp.get("origem") == "fatura" or comp.get("forma") in ("fatura", "cartão") or bool(comp.get("cartao_account_id"))


def _nome_cartao(comp):
    return (comp.get("linha") or {}).get("cartao") or (comp.get("nome") if comp.get("origem") == "fatura" else "") or ""


def _casa_emissor(nome, desc):
    """Pagamento de fatura (caixa.FATURA_RE) cuja descricao traz o nome do cartao, aceitando o corte do banco:
    a partir de um inicio de palavra, o texto coincide com o comeco do nome por >= min(len(nome), 10) caracteres,
    terminando em fim de palavra ou no fim da descricao."""
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
    if comp.get("extrato_chaves") and _contem(comp["extrato_chaves"], tx.get("descricao")):
        return "favorecido"
    if _eh_fatura(comp) and _casa_emissor(_nome_cartao(comp), tx.get("descricao")):
        return "emissor"
    return None


def _avalia(comp, pago, p):
    """(encaixe, estado, diferenca, juros, motivo). encaixe 0 = valor dentro da tolerancia (ou da faixa de juros),
    1 = aceito sem encaixe (variavel ou sem valor), 2 = a conferir. Se o valor e conhecido ou so estimado e
    decidido em `_certeza`, entre linhas diferentes."""
    v = comp.get("valor")
    if v is None:
        return 1, "pago", None, None, None
    d = _r2(pago - v)
    tol, jur = p["tolerancia_fixo"] * v, p["tolerancia_juros"] * v
    confirmado = comp.get("valor_tipo") == "fixo" or comp.get("valor_fonte") in CONFIRMADO
    if abs(d) <= tol + _EPS:
        return 0, "pago", d, None, None
    if 0 < d <= jur + _EPS:  # acima da tolerancia ate a de juros
        return 0, "pago", d, (d if confirmado else None), None
    if d < 0 and confirmado:  # fixo, ou valor confirmado (documento, fatura, Valores do mes)
        menor = "pago a menor (mínimo?)" if _eh_fatura(comp) else "pago a menor"
        return 2, "a_conferir", d, None, f"{menor}: {_brl(pago)} de {_brl(v)}"
    if comp.get("valor_tipo") != "fixo":
        return 1, "pago", d, None, None
    return 2, "a_conferir", d, None, f"pago acima da tolerância de juros: {_brl(pago)} de {_brl(v)}"


def _certeza(comp):
    """0 = valor conhecido (fixo com valor, ou confirmado por Valores do mes/documento/fatura); 1 = so estimativa
    (variavel por valor_padrao/ultimo pagamento) ou sem valor."""
    if comp.get("valor") is None:
        return 1
    return 0 if comp.get("valor_tipo") == "fixo" or comp.get("valor_fonte") in CONFIRMADO else 1


def _ordenar(pares):
    """Chave de cada par: (encaixe, certeza da LINHA para o lancamento, ja vencido, distancia, |dif|, ids).
    A certeza da linha e a melhor certeza entre os compromissos da mesma serie (planilha._serie: a linha e a
    sucessora do --a-partir sao uma so) candidatos ao mesmo lancamento COM O MESMO encaixe. Entre linhas diferentes
    o valor conhecido ganha da estimativa; entre meses da mesma linha a certeza e igual e vale a ordem por data
    (o atraso fica com o mes vencido). Um mes cujo valor nao encaixa nao empresta certeza ao mes que encaixa."""
    def chave(par):
        return par["tx"]["id"], _serie(par["comp"].get("linha_id") or par["comp"]["id"]), par["encaixe"]
    melhor = {}
    for par in pares:
        melhor[chave(par)] = min(melhor.get(chave(par), 1), _certeza(par["comp"]))
    for par in pares:
        par["ordem"] = (par["ordem"][0], melhor[chave(par)]) + par["ordem"][1:]


def _corrente(e):
    return (e.get("tipo") or "BANK") == "BANK" and not e.get("pj")


def _neutro(tx, donos):
    if tx.get("natureza") == "neutro":
        return True
    return bool(donos) and caixa.natureza(tx.get("tipo_conta"), tx.get("descricao"), tx.get("categoria"),
                                           tx["valor"], donos) == "neutro"


def _ts(s, agora):
    t = dt.datetime.fromisoformat(s)
    if (t.tzinfo is None) != (agora.tzinfo is None):
        t = t.replace(tzinfo=agora.tzinfo)
    return t


def _parada(comp, estado_contas, p, agora):
    """Motivo 'extrato parado desde dd/mm' se as contas pagadoras estao todas paradas, senao None."""
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


def _atribui(pares, tx_usados, comp_tx):
    """Gulosa: cada lancamento e cada compromisso uma vez so."""
    for par in sorted(pares, key=lambda x: x["ordem"]):
        if par["tx"]["id"] in tx_usados or par["comp"]["id"] in comp_tx:
            continue
        tx_usados.add(par["tx"]["id"])
        comp_tx[par["comp"]["id"]] = par


def conciliar(comps, txs, vinculos, estado_contas, pagos, params, hoje, agora, donos=None):
    """-> ({comp_id: {estado, metodo, tx_id, pago_em, diferenca, juros, motivo}}, [(tx_id, comp_id, metodo, diferenca)]).
    `vinculos`: {tx_id: comp_id} ja gravados. `donos`: opcional, caixa.dono_tokens dos titulares (transferencia
    propria alem da natureza gravada na captura)."""
    p = params
    por_id = {t["id"]: t for t in txs}
    res = {c["id"]: dict(_VAZIO) for c in comps}
    novos = []

    # 0. vinculo persistido
    ligados = {t for t in vinculos if not str(t).startswith("manual:")}
    pago_vinculo = {}
    for t in sorted(ligados):
        pago_vinculo.setdefault(vinculos[t], t)
    for comp in comps:
        t = pago_vinculo.get(comp["id"])
        if not t:
            continue
        r = res[comp["id"]]
        r.update(estado="pago", tx_id=t, metodo="vinculo")
        tx = por_id.get(t)
        if tx:
            _, _, d, juros, _ = _avalia(comp, abs(tx["valor"]), p)
            r.update(metodo=_metodo_chave(comp, tx) or "valor", pago_em=tx["data"][:10], diferenca=d, juros=juros)

    # 1. janela
    pool = [t for t in txs if t.get("tipo_conta") == "BANK" and t["valor"] < 0 and t["id"] not in ligados
            and t["data"][:10] <= hoje.isoformat() and not (estado_contas.get(t["account_id"]) or {}).get("pj")
            and not _neutro(t, donos)]
    manuais = {}
    for v in pagos:
        if v.get("tipo") == "pago":
            manuais[(v["compromisso"], v["mes"])] = v

    def manual(comp):
        return manuais.get((comp.get("linha_id"), _ym(comp))) if comp.get("linha_id") else None

    abertos = [c for c in comps if res[c["id"]]["estado"] is None]  # com baixa manual tambem disputa: o extrato prevalece
    cartoes = {k for k in (_norm(_nome_cartao(c)) for c in comps if _eh_fatura(c)) if k}
    cartoes |= {k for k in (_norm(e.get("nome")) for e in estado_contas.values() if e.get("tipo") == "CREDIT") if k}

    def na_janela(comp, tx):
        vu = _dia(comp["vencimento_util"])
        return vu - dt.timedelta(days=p["janela_antes_dias"]) <= _dia(tx["data"]) <= hoje

    def ordem(enc, comp, tx, d):
        """Encaixe; depois o compromisso ja vencido na data do lancamento antes do que ainda nao venceu
        (pagamento atrasado nao vai para o mes seguinte); depois o vencimento mais proximo; depois |dif|.
        Compromisso com baixa manual so tem a prioridade de "ja vencido" se o lancamento e do mesmo mes do seu
        vencimento_util (senao pago por outra conta roubaria o lancamento do mes seguinte)."""
        vu, data = _dia(comp["vencimento_util"]), _dia(tx["data"])
        vencido = vu <= data and (not manual(comp) or (vu.year, vu.month) == (data.year, data.month))
        return (enc, 0 if vencido else 1, abs((data - vu).days), abs(d or 0), tx["id"], comp["id"])

    tx_usados, comp_tx, candidatos = set(), {}, {}

    # 2. por favorecido (e emissor do cartao)
    pares = []
    for comp in abertos:
        for tx in pool:
            met = _metodo_chave(comp, tx) if na_janela(comp, tx) else None
            if not met:
                continue
            enc, est, d, juros, mot = _avalia(comp, abs(tx["valor"]), p)
            if met == "emissor":
                n = sum(1 for k in cartoes if _casa_emissor(k, tx.get("descricao")))
                dentro = d is not None and abs(d) <= p["tolerancia_fixo"] * comp["valor"] + _EPS
                if n > 1 and not dentro:  # nome de cartao ambiguo: so com o valor dentro da tolerancia_fixo (sem juros)
                    enc, est, juros = 2, "a_conferir", None
                    mot = f"pagamento de fatura casa {n} cartões e o valor não confere; conferir"
            pares.append({"comp": comp, "tx": tx, "metodo": met, "estado": est, "diferenca": d, "juros": juros,
                          "motivo": mot, "encaixe": enc,
                          "ordem": ordem(enc, comp, tx, d)})
    _ordenar(pares)
    _atribui(pares, tx_usados, comp_tx)
    for par in pares:
        candidatos.setdefault(par["comp"]["id"], []).append(par)

    # 3. por valor
    com_chave = {tx["id"] for tx in pool for comp in comps if _metodo_chave(comp, tx)}
    pares = []
    for comp in abertos:
        if comp["id"] in comp_tx or comp.get("valor") is None:
            continue
        for tx in pool:
            if tx["id"] in tx_usados or tx["id"] in com_chave or not na_janela(comp, tx):
                continue
            if caixa.FATURA_RE.search(tx.get("descricao") or "") and not _eh_fatura(comp):
                continue
            d = _r2(abs(tx["valor"]) - comp["valor"])
            if abs(d) > p["tolerancia_valor"] + _EPS:
                continue
            pares.append({"comp": comp, "tx": tx, "metodo": "valor", "estado": "pago", "diferenca": d, "juros": None,
                          "motivo": None, "encaixe": 0, "ordem": ordem(0, comp, tx, d)})
    _ordenar(pares)
    _atribui(pares, tx_usados, comp_tx)
    for par in pares:
        candidatos.setdefault(par["comp"]["id"], []).append(par)

    nomes = {c["id"]: c.get("nome") or c["id"] for c in comps}
    dono_tx = {par["tx"]["id"]: par["comp"]["id"] for par in comp_tx.values()}

    for comp in [c for c in comps if res[c["id"]]["estado"] is None]:
        r, cid = res[comp["id"]], comp["id"]
        par = comp_tx.get(cid)
        if par and par["estado"] == "pago":
            r.update(estado="pago", metodo=par["metodo"], tx_id=par["tx"]["id"], pago_em=par["tx"]["data"][:10],
                     diferenca=par["diferenca"], juros=par["juros"])
            novos.append((par["tx"]["id"], cid, par["metodo"], par["diferenca"]))
            continue
        # 6. fatura PAID
        if _eh_fatura(comp) and str(comp.get("payment_status") or "").upper() == "PAID":
            r.update(estado="pago", metodo="banco")
            continue
        # 8. baixa manual
        v = manual(comp)
        if v:
            d = _r2(v["valor"] - comp["valor"]) if v.get("valor") is not None and comp.get("valor") is not None else None
            r.update(estado="pago", metodo="manual", tx_id=f"manual:{cid}", pago_em=v.get("data_pagamento"), diferenca=d)
            novos.append((f"manual:{cid}", cid, "manual", d))
            continue
        # 5. pago a menor / acima
        if par:
            r.update(estado="a_conferir", metodo=par["metodo"], tx_id=par["tx"]["id"], pago_em=par["tx"]["data"][:10],
                     diferenca=par["diferenca"], motivo=par["motivo"])
            continue
        # 4. perdeu o lancamento no empate: so se ja venceu (vencimento_util < hoje) e o vencedor nao ganhou por
        #    encaixe estritamente melhor; senao segue aberto/previsto/atrasado
        perdido = next((x for x in sorted(candidatos.get(cid, []), key=lambda x: x["ordem"])
                        if x["encaixe"] < 2 and x["tx"]["id"] in dono_tx
                        and comp_tx[dono_tx[x["tx"]["id"]]]["encaixe"] >= x["encaixe"]
                        and _dia(comp["vencimento_util"]) < hoje), None)
        if perdido:
            tx = perdido["tx"]
            r.update(estado="a_conferir", motivo=f"lançamento de {_ddmm(tx['data'])} ({_brl(abs(tx['valor']))}) "
                     f"ficou com {nomes[dono_tx[tx['id']]]}; conferir")
            continue
        # 7. debito automatico
        if comp.get("forma") == "debito_automatico":
            r["estado"] = "debito_automatico"
            continue
        vu = _dia(comp["vencimento_util"])
        if hoje > vu:
            mot = _parada(comp, estado_contas, p, agora)
            r.update(estado="a_conferir", motivo=mot) if mot else r.update(estado="atrasado")
        elif vu == hoje or (comp.get("valor") is not None and
                            (comp.get("valor_tipo") == "fixo" or comp.get("valor_fonte") in CONFIRMADO)):
            r["estado"] = "aberto"
        else:
            r["estado"] = "previsto"
    return res, novos
