"""Captura do Open Finance (mcp.ai): contas, saldos, lançamentos e faturas -> banco. Leitura incremental (R11).

Porte de gabi-fin/ingest.py: `sincronizar`, `unificar_pending` e as regras de sinal mantêm a lógica; o SQL é novo.
Grava o bruto ANTES de processar (spec §13.2) e nunca sobrescreve decisão do Ricardo (R1/R9).
Consome: db, rodada, bruto, dinheiro.caixa, dinheiro.valor.
"""
import datetime as dt
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from gabi.bruto import gravar_bruto
from gabi.db import transacao
from gabi.dinheiro import caixa, gastador, nao_gasto
from gabi.dinheiro.moeda import valor_lancamento
from gabi.dinheiro.valor import para_centavos
from gabi.rodada import registrar_rodada

JANELA_DIAS = 10   # gabi-fin: última transação real menos 10 dias (cobre PENDING que vira POSTED depois)
SEM_HISTORICO_DIAS = 400
ERRO_SYNC = {"LOGIN_ERROR", "OUTDATED", "WAITING_USER_INPUT", "ERROR", "USER_AUTHORIZATION_PENDING"}


@dataclass
class ResumoCaptura:
    contas: int
    lidos: int
    novos: int
    falhas: list[str] = field(default_factory=list)
    sync_problemas: dict = field(default_factory=dict)
    rodada_id: int = 0


def lista(d):
    if not isinstance(d, dict):
        return []
    for k in ("results", "bills", "items", "data", "connections"):
        if isinstance(d.get(k), list):
            return d[k]
    return []


def g(o, *ks):
    for k in ks:
        if isinstance(o, dict) and o.get(k) not in (None, ""):
            return o[k]
    return None


# --- sincronização forçada: o banco só aparece no Open Finance depois que sincroniza ---
# status fica UPDATED mesmo sem atualizar: terminou = lastUpdatedAt depois do pedido.
def sincronizar(chamar, dorme=time.sleep, agora=time.monotonic, limite=300, passo=30, inicio=None, ultimas=None):
    """Força a sincronização de todas as conexões e espera cada uma atualizar (até `limite` s).
    Devolve ({banco: executionStatus}, {banco: problema}). Não imprime valores. Se `ultimas` for um dict, recebe {banco: lastUpdatedAt do provedor}."""
    inicio = inicio or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    nomes = {}
    for x in lista(chamar("openfinance_list_connections", {})):
        i = g(x, "item_id", "id", "itemId")
        if i:
            nomes[str(i)] = str(g(x, "connector_name", "name", "connector") or i)
    if not nomes:
        return {}, {}
    chamar("openfinance_force_sync", {"items": list(nomes)}, tent=2)
    estados, ultimo, pendentes, problemas, fim = {}, {}, set(nomes), {}, agora() + limite
    while pendentes:
        for it in lista(chamar("openfinance_get_item_status", {}, tent=2)):
            i = str(g(it, "id", "item_id") or "")
            if i not in pendentes:
                continue
            st, ex, lu = str(it.get("status") or "").upper(), str(it.get("executionStatus") or "").upper(), str(it.get("lastUpdatedAt") or "")
            estados[nomes[i]], ultimo[i] = ex or st, lu
            if st in ERRO_SYNC or ex in ERRO_SYNC:
                problemas[nomes[i]] = st if st in ERRO_SYNC else ex
                pendentes.discard(i)
            elif st != "UPDATING" and lu[:19] > inicio[:19]:
                pendentes.discard(i)
        if not pendentes or agora() + passo > fim:
            break
        dorme(passo)
    if ultimas is not None:
        ultimas.update({nomes[i]: lu for i, lu in ultimo.items() if lu})
    for i in pendentes:
        lu = ultimo.get(i, "")
        quando = f"{lu[8:10]}/{lu[5:7]} {lu[11:16]} UTC" if len(lu) >= 16 else "desconhecida"
        problemas[nomes[i]] = f"não atualizou em {limite // 60} min (última atualização {quando})"
    return estados, problemas


def hora_de_sincronizar(horas, hora):
    return hora in {int(h) for h in str(horas).split(",") if h.strip()}


# --- banco ---
def janela_inicio(con, conta_id: int, hoje: dt.date) -> str:
    """Última transação REAL (data <= hoje; parcela futura não conta) menos 10 dias. Sem histórico: 400 dias."""
    ult = con.execute("select max(data) from lancamento where conta_id=? and data<=?", (conta_id, hoje.isoformat())).fetchone()[0]
    return ((dt.date.fromisoformat(ult[:10]) - dt.timedelta(days=JANELA_DIAS)) if ult
            else (hoje - dt.timedelta(days=SEM_HISTORICO_DIAS))).isoformat()


def _dia(s):
    try:
        return dt.date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


def _mesma_descricao(a, b):
    """Descrição do PENDING e do POSTED costumam diferir um pouco: igual depois de normalizar, ou pelo menos 2/3 das
    palavras da menor presentes na outra."""
    na, nb = caixa.norm(a), caixa.norm(b)
    if na == nb:
        return 2
    ta, tb = set(na.split()), set(nb.split())
    menor = min(len(ta), len(tb))
    return 1 if menor and len(ta & tb) * 3 >= menor * 2 else 0


def unificar_pending(con, conta_id: int) -> int:
    """O POSTED substitui o PENDING equivalente (mesmo valor, descrição equivalente, +-3 dias), 1 para 1: cada POSTED
    absorve no máximo um PENDING (o de data mais próxima). O vínculo de conciliação do PENDING passa para o POSTED.
    Devolve quantos PENDING apagou."""
    # Chave de valor: em moeda estrangeira o valor em reais muda entre PENDING e POSTED, então vale (moeda, valor original); BRL: o valor.
    rows = [(r["id"], _dia(r["data"]), r["descricao_original"], (r["moeda"], r["valor_original_centavos"]) if r["moeda"] else (None, r["valor_centavos"]),
             r["status"] == "pending", r["externo_id"])
            for r in con.execute("select id, data, descricao_original, valor_centavos, moeda, valor_original_centavos, status, externo_id from lancamento where conta_id=?", (conta_id,))]
    pend = sorted((r for r in rows if r[4] and r[1]), key=lambda r: (r[1], r[0]))
    post = [r for r in rows if not r[4] and r[1]]
    usados, n = set(), 0
    for p in pend:
        cand = []
        for q in post:
            if q[0] in usados or p[3] != q[3]:
                continue
            gap, nivel = abs((p[1] - q[1]).days), _mesma_descricao(p[2], q[2])
            if gap <= 3 and nivel:
                cand.append((-nivel, gap, q[0], q[5]))
        if not cand:
            continue
        _, _, qid, qext = min(cand)
        usados.add(qid)
        if con.execute("select 1 from conciliacao where tx_id=?", (qext,)).fetchone():
            con.execute("delete from conciliacao where tx_id=?", (p[5],))
        else:
            con.execute("update conciliacao set tx_id=? where tx_id=?", (qext, p[5]))
        con.execute("delete from lancamento where id=?", (p[0],))
        n += 1
    return n


def registrar_estado(con, contas, ids, sync, bancos_pj, hoje, agora, falhas=None):
    """Uma linha por conta em conta_estado. `sync` = {estados, problemas} por conector (o banco da conta é o nome do
    conector). ult_sync_ok só avança quando houve sincronização desse banco sem problema; senão mantém o anterior."""
    falhas = falhas or {}
    estados, problemas = (sync or {}).get("estados") or {}, (sync or {}).get("problemas") or {}
    for a in contas:
        aid, banco = a["account_id"], a.get("bank")
        ult = con.execute("select max(data) from lancamento where conta_id=? and data<=?", (ids[aid], hoje.isoformat())).fetchone()[0]
        ant = con.execute("select ult_sync_ok, status_conexao from conta_estado where account_id=?", (aid,)).fetchone()
        sync_ok = ant["ult_sync_ok"] if ant else None
        if banco in problemas:
            status = problemas[banco]
        elif banco in estados and aid not in falhas:
            status, sync_ok = estados[banco] or "OK", agora.isoformat(timespec="seconds")
        else:
            status = ant["status_conexao"] if ant and ant["status_conexao"] and not ant["status_conexao"].startswith("ERRO_LEITURA") else "OK"
        if aid in falhas:
            status = "ERRO_LEITURA: " + falhas[aid]
        con.execute("insert or replace into conta_estado(account_id, banco, nome, tipo, pj, ult_tx_real, ult_sync_ok, status_conexao, "
                    "saldo_centavos, atualizado_em) values (?,?,?,?,?,?,?,?,?,?)",
                    (aid, banco, a.get("name"), a.get("type"), 1 if banco in bancos_pj else 0, ult, sync_ok, status,
                     para_centavos(caixa.num(a.get("balance"))), agora.isoformat(timespec="seconds")))


def _gravar_contas(con, contas, ts, bancos_pj) -> dict[str, int]:
    ids = {}
    for a in contas:
        cd = a.get("creditData") or {}
        con.execute(
            "insert into conta(externo_id, instituicao, tipo, apelido, pj, titular, limite_centavos, disponivel_centavos, vencimento_fatura) "
            "values (?,?,?,?,?,?,?,?,?) on conflict(externo_id) do update set instituicao=excluded.instituicao, tipo=excluded.tipo, "
            "pj=excluded.pj, titular=excluded.titular, limite_centavos=excluded.limite_centavos, "
            "disponivel_centavos=excluded.disponivel_centavos, vencimento_fatura=excluded.vencimento_fatura",
            (a["account_id"], a.get("bank"), a["type"], a.get("name"), 1 if a.get("bank") in bancos_pj else 0, a.get("owner"),
             para_centavos(caixa.num(cd.get("creditLimit"))), para_centavos(caixa.num(cd.get("availableCreditLimit"))),
             (cd.get("balanceDueDate") or "")[:10] or None))
        ids[a["account_id"]] = con.execute("select id from conta where externo_id=?", (a["account_id"],)).fetchone()[0]
        con.execute("insert or replace into saldo(conta_id, em, saldo_centavos) values (?,?,?)",
                    (ids[a["account_id"]], ts, para_centavos(caixa.num(a.get("balance"))) or 0))
    return ids


def _purgar_futuro(con, hoje):
    """Parcela futura não é lançamento: apaga o que um estado antigo tenha deixado com data depois de hoje."""
    futuros = [r[0] for r in con.execute("select externo_id from lancamento where data>?", (hoje.isoformat(),))]
    for x in futuros:
        con.execute("delete from conciliacao where tx_id=?", (x,))
        con.execute("delete from lancamento where externo_id=?", (x,))


def _buscar_conta(con, a, conta_id, cliente, hoje):
    aid, de, page, itens = a["account_id"], janela_inicio(con, conta_id, hoje), 1, []
    while True:
        d = cliente("openfinance_list_transactions", {"account_id": aid, "from": de, "page": page, "page_size": 500})
        if d is None:
            raise ConnectionError("sem resposta")
        itens += lista(d)
        if page >= (d.get("totalPages") or 1):
            break
        page += 1
    faturas = []
    if a["type"] == "CREDIT":
        d = cliente("openfinance_list_credit_card_bills", {"account_id": aid, "page_size": 12, "include_open_bill": True}) or \
            cliente("openfinance_list_credit_card_bills", {"account_id": aid, "page_size": 12})
        faturas = lista(d)
    return itens, faturas


def _processar_conta(con, a, conta_id, itens, faturas, hoje, donos, bruto_ref) -> tuple[int, int]:
    aid, tipo, lidos, novos = a["account_id"], a["type"], 0, 0
    for t in itens:
        data = (t.get("date") or "")[:10]
        if not data or data > hoje.isoformat():  # sem data ou parcela futura: não é lançamento
            continue
        val = valor_lancamento(t, tipo)
        cc = t.get("creditCardMetadata") or {}
        nat = caixa.natureza(tipo, t.get("description"), t.get("category"), val.reais, donos)
        existia = con.execute("select 1 from lancamento where externo_id=?", (t["id"],)).fetchone() is not None
        con.execute(
            "insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, estabelecimento, forma, fatura_id, "
            "parcela, parcelas, data_compra, status, natureza, operacao, bruto_ref, categoria_banco, moeda, valor_original_centavos, convertido) "
            "values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "on conflict(externo_id) do update set conta_id=excluded.conta_id, data=excluded.data, valor_centavos=excluded.valor_centavos, "
            "descricao_original=excluded.descricao_original, estabelecimento=excluded.estabelecimento, forma=excluded.forma, "
            "fatura_id=excluded.fatura_id, parcela=excluded.parcela, parcelas=excluded.parcelas, data_compra=excluded.data_compra, "
            "status=excluded.status, natureza=excluded.natureza, operacao=excluded.operacao, "
            "categoria_banco=excluded.categoria_banco, moeda=excluded.moeda, valor_original_centavos=excluded.valor_original_centavos, "
            "convertido=excluded.convertido",  # bruto_ref: onde foi visto pela 1ª vez
            (conta_id, t["id"], data, val.centavos, t.get("description"), caixa.norm(t.get("description")) or None,
             (t.get("paymentData") or {}).get("paymentMethod"), cc.get("billId"), cc.get("installmentNumber"),
             cc.get("totalInstallments"), (cc.get("purchaseDate") or "")[:10] or None,
             "pending" if str(t.get("status") or "").upper() == "PENDING" else "posted", nat, t.get("operationType"), bruto_ref,
             t.get("category"), val.moeda, val.original_centavos, 1 if val.convertido else 0))
        lidos += 1
        novos += 0 if existia else 1
    for f in faturas:
        fid = g(f, "id", "bill_id")
        if not fid:
            continue
        con.execute(
            "insert into fatura(id, account_id, vencimento, total_centavos, minimo_centavos, pagamento_status, conta_id) values (?,?,?,?,?,?,?) "
            "on conflict(id) do update set vencimento=excluded.vencimento, total_centavos=excluded.total_centavos, "
            "minimo_centavos=excluded.minimo_centavos, pagamento_status=excluded.pagamento_status, conta_id=excluded.conta_id",
            (fid, aid, (g(f, "dueDate", "due_date") or "")[:10], para_centavos(caixa.num(g(f, "totalAmount", "total_amount", "amount"))),
             para_centavos(caixa.num(g(f, "minimumPaymentAmount", "minimum_payment"))), g(f, "paymentStatus", "payment_status"), conta_id))
    unificar_pending(con, conta_id)
    return lidos, novos


JANELA_RETOMADA = dt.timedelta(hours=3)


def _retomar(con, hoje: dt.date, agora: dt.datetime) -> dict[str, tuple[int, int]]:
    """EV2. Quem chama `capturar` já tem o lock exclusivo, então qualquer rodada 'rodando' é de um processo morto: vira erro 'interrompida'.
    Devolve account_id -> (lidos, novos) das contas que a última rodada não concluída do mesmo dia já gravou, se foi há menos de 3 h
    e nenhuma rodada ok veio depois dela."""
    agora_utc = agora.astimezone(dt.timezone.utc)
    con.execute("update rodada set status='erro', erro='interrompida', fim=? where fonte='open-finance' and status='rodando'", (agora_utc.isoformat(),))
    ultima = con.execute("select id, status, inicio from rodada where fonte='open-finance' order by id desc limit 1").fetchone()
    if ultima is None or ultima["status"] == "ok":
        return {}
    try:
        inicio = dt.datetime.fromisoformat(ultima["inicio"])
    except ValueError:
        return {}
    if agora_utc - inicio > JANELA_RETOMADA:
        return {}
    return {r["account_id"]: (r["lidos"], r["novos"]) for r in con.execute(
        "select account_id, lidos, novos from captura_conta where rodada_id=? and dia=?", (ultima["id"], hoje.isoformat()))}


def _guardar_sync_banco(con, ultimas: dict) -> None:
    """Guarda a última atualização que o PROVEDOR declarou para cada banco (`dinheiro.sync_banco`): é a idade dos dados, não a da nossa leitura.
    Quem não veio nesta sincronização mantém o valor anterior."""
    if not ultimas:
        return
    r = con.execute("select valor from parametro where chave='dinheiro.sync_banco'").fetchone()
    try:
        atual = json.loads(r[0]) if r else {}
    except (ValueError, TypeError):
        atual = {}
    atual = {**(atual if isinstance(atual, dict) else {}), **ultimas}
    con.execute("insert into parametro(chave, valor) values ('dinheiro.sync_banco', ?) on conflict(chave) do update set valor=excluded.valor", (json.dumps(atual, ensure_ascii=False),))


def capturar(con, cliente, hoje: dt.date, agora: dt.datetime, bruto_base: Path, *, bancos_pj=frozenset(),
             sincronizar_antes: bool = False, dorme=time.sleep) -> ResumoCaptura:
    """Uma rodada de captura. Erro numa conta entra em `falhas` e as outras seguem (rodada ok, com aviso)."""
    prontas = _retomar(con, hoje, agora)
    with registrar_rodada(con, "open-finance") as rodada:
        sync, problemas = None, {}
        if sincronizar_antes:
            ultimas: dict = {}
            estados, problemas = sincronizar(cliente, dorme=dorme, ultimas=ultimas)
            _guardar_sync_banco(con, ultimas)
            sync = {"estados": estados, "problemas": problemas}
        ts = agora.replace(tzinfo=None).isoformat(timespec="seconds")
        contas = lista(cliente("openfinance_list_accounts", {}))
        ids = _gravar_contas(con, contas, ts, bancos_pj)
        donos = caixa.dono_tokens([a["owner"] for a in contas if a.get("owner") and a["type"] != "CREDIT"])
        _purgar_futuro(con, hoje)
        lidos = novos = 0
        falhas: dict[str, str] = {}
        for a in contas:
            aid = a["account_id"]
            if aid in prontas:  # já gravada por uma rodada interrompida de hoje (EV2): não refaz
                lidos, novos = lidos + prontas[aid][0], novos + prontas[aid][1]
                continue
            try:
                itens, faturas = _buscar_conta(con, a, ids[aid], cliente, hoje)
                rotulo = f"{agora:%H%M%S}-{re.sub(r'[^A-Za-z0-9._-]', '', aid[-6:])}"
                bruto = gravar_bruto(bruto_base, "open-finance", agora.date(),
                                     [{"conta": aid, "tipo": "transacao", "dado": t} for t in itens]
                                     + [{"conta": aid, "tipo": "fatura", "dado": f} for f in faturas], rotulo=rotulo)
                con.execute("begin")
                try:
                    n_lidos, n_novos = _processar_conta(con, a, ids[aid], itens, faturas, hoje, donos, bruto.name)
                    con.execute("insert or replace into captura_conta(rodada_id, account_id, dia, lidos, novos, concluida_em) values (?,?,?,?,?,?)",
                                (rodada.id, aid, hoje.isoformat(), n_lidos, n_novos, agora.isoformat(timespec="seconds")))
                    con.execute("commit")
                except BaseException:
                    con.execute("rollback")
                    raise
                lidos, novos = lidos + n_lidos, novos + n_novos
            except Exception as e:  # a conta fica fora desta rodada (rollback do parcial); as outras seguem
                falhas[aid] = type(e).__name__
        erro_pos = None
        try:  # depois de todas as contas: o boleto do banco se confere com as faturas dos cartões gravadas nesta rodada
            with transacao(con):
                nao_gasto.reaplicar(con)
                gastador.preencher(con)
        except Exception as e:  # a natureza bruta do caixa.natureza fica e o gastador espera; a próxima rodada tenta de novo
            erro_pos = type(e).__name__
        registrar_estado(con, contas, ids, sync, bancos_pj, hoje, agora, falhas)
        rodada.lidos, rodada.novos = lidos, novos
        if falhas:
            rodada.aviso = "falhas: " + ", ".join(sorted(falhas))
        if erro_pos:
            rodada.aviso = "; ".join(filter(None, [rodada.aviso, f"não é gasto e quem gastou não foram reaplicados: {erro_pos}"]))
        rid = rodada.id
    return ResumoCaptura(len(contas), lidos, novos, sorted(falhas), problemas, rid)


TENTATIVAS_SALDOS = 3   # o provedor às vezes devolve só parte das contas (4 a 17 de 17 em 15/10): repete e junta o que vier
ESPERA_SALDOS = 20      # segundos entre as tentativas


def _contas_esperadas(con) -> dict[str, str]:
    """Contas que o brain já conhece e não foram desligadas (estado 'nao') nem excluídas: externo_id -> nome."""
    return {r[0]: (r[1] or r[0]) for r in con.execute("select externo_id, apelido from conta where estado<>'nao' and excluido_em is null")}


def capturar_saldos(con, cliente, agora: dt.datetime, bancos_pj=frozenset(), tentativas: int = TENTATIVAS_SALDOS,
                    dorme=time.sleep, espera: float = ESPERA_SALDOS) -> int:
    """Só contas e saldos (de hora em hora); não lê extrato. Fonte própria ('open-finance-saldos'): não entra no dados_ate.
    Se vierem menos contas do que o brain conhece, repete até `tentativas` vezes e junta o que chegou; o que ainda faltar mantém
    a última leitura (o caixa soma o saldo mais recente de cada conta) e a rodada guarda um aviso 'incompleta' em rodada.erro."""
    with registrar_rodada(con, "open-finance-saldos") as rodada:
        esperadas = _contas_esperadas(con)
        por_id: dict[str, dict] = {}
        for n in range(max(1, tentativas)):
            if n:
                dorme(espera)
            for a in lista(cliente("openfinance_list_accounts", {})):
                por_id[a["account_id"]] = a
            if not set(esperadas) - set(por_id):
                break
        contas = list(por_id.values())
        ids = _gravar_contas(con, contas, agora.replace(tzinfo=None).isoformat(timespec="seconds"), bancos_pj)
        registrar_estado(con, contas, ids, None, bancos_pj, agora.date(), agora)
        rodada.lidos = len(contas)
        faltam = sorted(nome for aid, nome in esperadas.items() if aid not in por_id)
        if faltam:
            rodada.aviso = f"incompleta: {len(esperadas) - len(faltam)} de {len(esperadas)} contas ({', '.join(faltam)[:200]} não vieram)"
    return len(contas)
