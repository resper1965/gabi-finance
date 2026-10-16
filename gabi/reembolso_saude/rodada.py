"""Rodada do reembolso de saúde (timer): lê do Paperless os documentos marcados `gabi:saude-reembolso` (e adota os antigos do gabi-fin) ainda não vistos,
classifica pelo TEXTO com modelo barato, monta os dossiês no COFRE cifrado (ADR-014), reabre o que ganhou o item que faltava, aplica o "pedi/recebi" do Ricardo,
casa o crédito da operadora no extrato e atualiza a projeção do `gabi.db` (só número do dossiê, mês, estado, contagens e códigos do que falta).
R1: o brain só sugere e registra; nada é enviado a ninguém. Etiquetas: só `gabi:*` acrescentadas (pedido, recebido); o estado de verdade é o do cofre.
Nada de nome, valor ou texto de documento em log, aviso ou `gabi.db`. Consome: requisitos, dossies, classificar, cofre, fontes.paperless (pela ponte), avisos."""
import datetime as dt
import json
from zoneinfo import ZoneInfo

from gabi import visao_pdf
from gabi.avisos import _novo
from gabi.dinheiro.modelo import LIMIAR, Orcamento
from gabi.fontes.paperless import ErroPaperless
from gabi.reembolso_saude import classificar as clf, cofre, dossies, requisitos
from gabi.reembolso_saude.tipos import ETIQUETA_ENTRADA, ETIQUETA_PEDIDO, ETIQUETA_RECEBIDO, ETIQUETAS_LEGADAS, TIPO_PAPERLESS_AUTORIZACAO

BRT = ZoneInfo("America/Sao_Paulo")
MAX_TENTATIVAS = 8
PRIORIDADE = ("a_pedir", "sem_nf", "sem_aprovacao", "a_conferir", "pedido", "recebido")
ETIQUETA_DO_ESTADO = {"pedido": ETIQUETA_PEDIDO, "recebido": ETIQUETA_RECEBIDO}


def _data(v, padrao: dt.date) -> dt.date:
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return padrao


def _fontes(paperless) -> dict[int, tuple[dict, str | None]]:
    """{id: (documento do Paperless, estado do gabi-fin ou None)}. A etiqueta nova vem primeiro; as antigas e o tipo "Autorização" são só LIDOS (adoção)."""
    achados: dict[int, tuple[dict, str | None]] = {}
    for d in paperless.por_etiqueta(ETIQUETA_ENTRADA):
        achados.setdefault(d["id"], (d, None))
    for etiqueta, estado in ETIQUETAS_LEGADAS.items():
        for d in paperless.por_etiqueta(etiqueta):
            achados.setdefault(d["id"], (d, estado))
    for d in paperless.docs(document_type__name__iexact=TIPO_PAPERLESS_AUTORIZACAO):
        achados.setdefault(d["id"], (d, "autorizacao"))
    return achados


def _estado_inicial(pista: clf.Pista, legado: str | None, doc: dict, todos: list[dict], req: dict) -> str:
    if legado in ("pedido", "recebido"):
        return legado
    if pista.documento == "autorizacao" or legado == "autorizacao":
        return "autorizacao"
    if (pista.confianca < LIMIAR or not (pista.documento and pista.caso and pista.paciente and pista.prestador)):
        return "a_conferir"
    par = [x for x in todos if dossies.par(x) == dossies.par(doc)] + [doc]
    return dossies.estado_pelo_portao(doc["caso"], dossies.itens_portao(doc, par), req)


def _montar(pid: int, d: dict, pista: clf.Pista, legado: str | None, hoje: dt.date) -> dict:
    campos = {k: v for k, v in (("paciente", pista.paciente), ("prestador", pista.prestador), ("valor", pista.valor), ("doc_prestador", pista.doc_prestador),
                                ("conselho", pista.conselho), ("especialidade", pista.especialidade)) if v}
    documento = "autorizacao" if legado == "autorizacao" and not pista.documento else pista.documento
    return {"id": pid, "documento": documento, "caso": pista.caso, "campos": campos, "confianca": pista.confianca,
            "data": _data(pista.data or d.get("created"), _data(d.get("added"), hoje)), "adicionado": _data(d.get("added"), hoje),
            "pedido_em": hoje if legado in ("pedido", "recebido") else None, "protocolo": None, "credito_tx": None}


def _gravar_doc(con, pid: int, estado: str, motivo: str | None, agora: str, tentativas: int = 0) -> None:
    con.execute("insert into reembolso_saude_doc(paperless_id, estado, tentativas, motivo, atualizado_em) values (?,?,?,?,?) "
                "on conflict(paperless_id) do update set estado=excluded.estado, tentativas=excluded.tentativas, motivo=excluded.motivo, atualizado_em=excluded.atualizado_em",
                (pid, estado, tentativas, motivo, agora))


def _creditos(con, desde: dt.date) -> list[dict]:
    return [{"id": r["id"], "data": r["data"], "descricao": r["descricao_original"] or "", "valor_centavos": r["valor_centavos"]}
            for r in con.execute("select id, data, descricao_original, valor_centavos from lancamento where valor_centavos>0 and status='posted' and data>=?",
                                 (desde.isoformat(),))]


def _prioridade(estados: list[str]) -> str:
    return next(e for e in PRIORIDADE if e in estados)


def _projecao(s, todos: dict[int, dict], res: list[dict]) -> list[dict]:
    """Uma linha por dossiê (documentos de apoio, sozinhos, não contam), só com o que o MCP pode ler: nada de nome nem valor."""
    por_resumo = {x["docs"][0]: x for x in res}
    linhas = []
    for dos in cofre.dossies_todos(s):
        ds = [d for d in todos.values() if d["dossie_id"] == dos["id"]]
        if not ds or all(d["estado"] == "autorizacao" for d in ds):
            continue
        estado = _prioridade([d["estado"] for d in ds if d["estado"] != "autorizacao"])
        r = next((por_resumo[d["id"]] for d in ds if d["id"] in por_resumo), None) if estado == "a_pedir" else None
        base = [d for d in ds if d["estado"] == estado]
        linhas.append({"id": dos["id"], "mes": dos["mes"], "estado": estado, "docs": len(ds), "pronto": int(bool(r and r["pronto"])),
                       "faltam": r["faltam"] if r else [], "doc_ids": sorted(d["id"] for d in ds),
                       "parado_desde": max(d["adicionado"] for d in base).isoformat()})
    return linhas


def rodar(con, abrir_cofre, paperless, cliente, orcamento: Orcamento, agora: dt.datetime) -> dict:
    """-> contagens (nunca nome, valor ou texto). RequisitosInvalidos e ErroPaperless sobem para o programa registrar a falha."""
    req = requisitos.carregar(con)
    agora_s, hoje = agora.astimezone(dt.timezone.utc).isoformat(), agora.astimezone(BRT).date()
    r = {"novos": 0, "classificados": 0, "a_conferir": 0, "falhos": 0, "esperando": 0, "motivo_espera": None, "adotados": 0, "acoes": 0,
         "recebidos": 0, "etiquetados": 0, "etiquetas_falhas": 0, "avisos": 0}
    vistos = {x["paperless_id"]: x for x in con.execute("select * from reembolso_saude_doc")}
    acoes = [dict(a) for a in con.execute("select * from reembolso_saude_acao where aplicado_em is null order by id")]
    fontes = _fontes(paperless)
    novos = sorted(i for i in fontes if i not in vistos or vistos[i]["estado"] == "novo")
    r["novos"] = len(novos)
    if not novos and not acoes and not any(v["estado"] == "classificado" for v in vistos.values()):
        return r
    alterados, pendentes_avisos, gravar_doc_ref = set(), [], []
    with abrir_cofre() as s:
        todos = {d["id"]: d for d in cofre.docs(s)}
        parar = False
        for pid in novos:
            if parar:
                r["esperando"] += 1
                continue
            raw, legado = fontes[pid]
            tent = vistos[pid]["tentativas"] if pid in vistos else 0
            texto = raw.get("content") or ""
            pdf = None
            if not texto.strip():
                motivo = "sem texto legível"
                if visao_pdf.tem_leitura(cliente):  # PDF digitalizado: só com `saude.visao_pdf` ligado (o PDF vai a um provedor externo)
                    cfg = visao_pdf.config(con)
                    if cfg is None:
                        motivo = visao_pdf.MOTIVO_DESLIGADA
                    elif not orcamento.permite():
                        motivo = None  # teto estourado: `classificar` devolve espera, sem baixar o PDF
                    else:
                        pdf = paperless.baixar(pid)
                        motivo = None if visao_pdf.dentro_do_teto(pdf, cfg) else visao_pdf.MOTIVO_GRANDE
                if motivo:
                    gravar_doc_ref.append((pid, "falhou", motivo, tent))
                    r["falhos"] += 1
                    continue
            res = clf.classificar(texto, cliente, orcamento, pdf or None)
            if res.estado == "espera":
                if res.temporaria:
                    tent += 1
                    gravar_doc_ref.append((pid, "falhou", "falhas repetidas", tent) if tent >= MAX_TENTATIVAS else (pid, "novo", res.motivo, tent))
                    r["falhos"] += tent >= MAX_TENTATIVAS
                    r["esperando"] += tent < MAX_TENTATIVAS
                else:  # sem modelo ou sem teto: nada foi cobrado, não conta tentativa; as demais esperariam também
                    r["motivo_espera"], parar = res.motivo, True
                    r["esperando"] += 1
                continue
            if res.estado == "falhou":
                gravar_doc_ref.append((pid, "falhou", res.motivo, tent))
                r["falhos"] += 1
                continue
            s.con.execute("savepoint doc")
            try:
                d = _montar(pid, raw, res.pista, legado, hoje)
                d["estado"] = _estado_inicial(res.pista, legado, d, list(todos.values()), req)
                if d["estado"] == "a_conferir" and not (d["campos"].get("paciente") and d["campos"].get("prestador")):
                    d["chave"] = f"conferir|{pid}"
                d["dossie_id"] = cofre.gravar_doc(s, d)
                s.con.execute("release doc")
            except Exception:  # noqa: BLE001 - o motivo é um código fixo: a mensagem do erro pode carregar texto do documento
                s.con.execute("rollback to doc")
                s.con.execute("release doc")
                gravar_doc_ref.append((pid, "falhou", "erro ao classificar", tent))
                r["falhos"] += 1
                continue
            todos[pid] = d
            alterados.add(pid)
            gravar_doc_ref.append((pid, "classificado", None, tent))
            r["classificados"] += 1
            r["adotados"] += legado is not None
            r["a_conferir"] += d["estado"] == "a_conferir"
            if d["estado"] in dossies.ESTADOS_SEM and legado is None:
                item = next(k for k, v in dossies.SEM.items() if v == d["estado"])
                pendentes_avisos.append(("reembolso_saude_sem_requisito", f"{pid}", {"dossie": d["dossie_id"], "mes": f"{d['data']:%Y-%m}",
                                                                                     "requisito": requisitos.rotulo(req, item)}))
        # reabrir: o item que faltava chegou (NF no mesmo mês; aprovação vale para o par)
        por_par: dict[tuple, list[dict]] = {}
        for d in todos.values():
            if d["campos"].get("paciente") and d["campos"].get("prestador"):
                por_par.setdefault(dossies.par(d), []).append(d)
        for ds in por_par.values():
            for d in dossies.reabrir(ds, hoje, req):
                d["estado"] = "a_pedir"
                alterados.add(d["id"])
        # "pedi" e "recebi" do Ricardo
        resultados = []
        for a in acoes:
            if cofre.dossie(s, a["dossie_id"]) is None:
                resultados.append((a["id"], "dossie_inexistente"))
                continue
            ds = [d for d in todos.values() if d["dossie_id"] == a["dossie_id"]]
            if a["acao"] == "pedi":
                alvos = [d for d in ds if d["estado"] == "a_pedir"]
            else:
                alvos = [d for d in ds if d["estado"] == "pedido" or (d["estado"] == "a_conferir" and d.get("pedido_em"))]
            for d in alvos:
                d["estado"] = "pedido" if a["acao"] == "pedi" else "recebido"
                if a["acao"] == "pedi":
                    d["pedido_em"], d["protocolo"] = hoje, a["protocolo"] or d.get("protocolo")
                alterados.add(d["id"])
            resultados.append((a["id"], "aplicado" if alvos else "sem_documentos"))
        r["acoes"] = len(acoes)
        # crédito da operadora; pedido sem crédito há muito tempo vai para conferir
        em_espera = [d for d in todos.values() if d.get("pedido_em") and d["estado"] in ("pedido", "a_conferir")]
        if em_espera:
            usados = {d["credito_tx"] for d in todos.values() if d.get("credito_tx")}
            txs = [t for t in _creditos(con, min(d["pedido_em"] for d in em_espera)) if t["id"] not in usados]
            for d in sorted(em_espera, key=lambda x: x["id"]):
                tx = dossies.casar_credito(d, txs, req["operadora_extrato"])
                if tx is not None:
                    d["estado"], d["credito_tx"] = "recebido", tx
                    txs = [t for t in txs if t["id"] != tx]
                    r["recebidos"] += 1
                    alterados.add(d["id"])
                elif d["estado"] == "pedido" and (hoje - d["pedido_em"]).days > req["dias_sem_credito"]:
                    d["estado"] = "a_conferir"
                    alterados.add(d["id"])
        for pid in sorted(alterados):
            cofre.gravar_doc(s, todos[pid])
        # dois avisos por dossiê (abriu / pronto), como no legado; o que já foi avisado fica no cofre
        res = dossies.resumo([d for d in todos.values() if d["estado"] == "a_pedir"], hoje, req)
        for x in res:
            did = todos[x["docs"][0]]["dossie_id"]
            ja = cofre.avisos_do_dossie(s, did)
            payload = {"dossie": did, "mes": x["mes"], "faltam": [requisitos.rotulo(req, i) for i in x["faltam"]]}
            if x["pronto"] and "pronto" not in ja:
                pendentes_avisos.append(("reembolso_saude_pronto", f"{did}", payload))
                cofre.gravar_avisos(s, did, ["abre", "pronto"])
            elif not x["pronto"] and "abre" not in ja:
                pendentes_avisos.append(("reembolso_saude_abre", f"{did}", payload))
                cofre.gravar_avisos(s, did, ["abre"])
        linhas = _projecao(s, todos, res)
        marcas = {pid: ETIQUETA_DO_ESTADO[d["estado"]] for pid, d in todos.items() if d["estado"] in ETIQUETA_DO_ESTADO}
    # Só aqui, com o cofre salvo: referência, projeção, ações aplicadas, avisos e etiquetas (se o cofre não gravou, nada disto aconteceu).
    con.execute("begin")
    try:
        for pid, estado, motivo, tent in gravar_doc_ref:
            _gravar_doc(con, pid, estado, motivo, agora_s, tent)
        con.execute("delete from reembolso_saude_dossie")
        for x in linhas:
            con.execute("insert into reembolso_saude_dossie(id, mes, estado, docs, pronto, faltam, doc_ids, parado_desde, atualizado_em) values (?,?,?,?,?,?,?,?,?)",
                        (x["id"], x["mes"], x["estado"], x["docs"], x["pronto"], json.dumps(x["faltam"]), json.dumps(x["doc_ids"]), x["parado_desde"], agora_s))
        for aid, resultado in resultados:
            con.execute("update reembolso_saude_acao set aplicado_em=?, resultado=?, protocolo=null where id=?", (agora_s, resultado, aid))
        for tipo, chave, payload in pendentes_avisos:
            r["avisos"] += _novo(con, agora, tipo, chave, payload) is not None
        con.execute("commit")
    except BaseException:
        if con.in_transaction:
            con.execute("rollback")
        raise
    _etiquetar(paperless, marcas, r)
    return r


def _etiquetar(paperless, marcas: dict[int, str], r: dict) -> None:
    """Acrescenta `gabi:reembolso-pedido`/`-recebido` ao que ainda não tem (auto-reparo: a falta de uma rodada é refeita na seguinte)."""
    for etiqueta in sorted(set(marcas.values())):
        alvo = [pid for pid, e in marcas.items() if e == etiqueta]
        try:
            ja = {d["id"] for d in paperless.por_etiqueta(etiqueta)}
        except ErroPaperless:
            r["etiquetas_falhas"] += len(alvo)
            continue
        for pid in sorted(set(alvo) - ja):
            try:
                paperless.etiquetar(pid, [etiqueta])
                r["etiquetados"] += 1
            except ErroPaperless:
                r["etiquetas_falhas"] += 1
