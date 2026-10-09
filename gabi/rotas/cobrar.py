"""Rotas da Fase 2 (Cobrar e Pedidos): reembolsos, lote do Nibo, comprovantes, rascunho de cobrança e decisão de pedidos. Só o Ricardo (boss).
R2: a única gravação externa é o lote do Nibo, com confirmação textual idêntica (409 se divergir); e-mail só vira rascunho (403 ao enviar).
Consome: cobrar.*, fontes (fábricas em app.state.fontes), dinheiro.contas_pagar."""
import datetime as dt

from fastapi import APIRouter, Depends, Request

from gabi.cobrar import cadastro, cobranca as cb, comprovantes as cp_, lote_nibo as lote, pedidos as pd, reembolso as rb
from gabi.cobrar import recebimentos as rec
from gabi.cobrar.previsao import RECENTE_DIAS, previsao as calcular_previsao
from gabi.dinheiro import contas_pagar
from gabi.dinheiro.valor import formatar
from gabi.envelope import envelope
from gabi.identidade import Identidade, exigir
from gabi.rotas.dinheiro import _agora, _con, _corpo, _data, _json, erro

router = APIRouter(prefix="/api/v1/cobrar", dependencies=[Depends(exigir("boss"))])


def _lote_json(itens, texto, lote_id=None):
    return {"id": lote_id, "texto_confirmacao": texto,
            "itens": [{"lancamento_id": i.lancamento_id, "data": i.data, "descricao": i.descricao, "valor": formatar(i.valor_centavos)} for i in itens]}


def _situacao_comprovante(con, lancamento_id: int) -> str:
    estados = {r[0] for r in con.execute("select estado from comprovante_vinculo where lancamento_id=?", (lancamento_id,))}
    return "confirmado" if "confirmado" in estados else "proposto" if "proposto" in estados else "faltando"


# ---------------- reembolsos e lote ----------------
@router.get("/reembolsos")
def reembolsos(request: Request):
    """Reembolsos por empresa contratante (itens em aberto e cobranças) e a prévia do lote do Nibo da Bekaa."""
    con = _con(request)
    try:
        empresas = []
        for e in cadastro.contratantes(con):
            itens = rb.itens_a_reembolsar(con, e["id"])
            empresas.append({
                "empresa_id": e["id"], "nome": e["nome"], "em_aberto": formatar(sum(i.em_aberto_centavos for i in itens)),
                "itens": [{"lancamento_id": i.lancamento_id, "data": i.data, "descricao": i.descricao, "valor": formatar(i.valor_centavos),
                           "em_aberto": formatar(i.em_aberto_centavos), "comprovante": _situacao_comprovante(con, i.lancamento_id)} for i in itens],
                "reembolsos": [{"id": r["id"], "estado": r["estado"], "cobrado_em": r["cobrado_em"]}
                               for r in con.execute("select id, estado, cobrado_em from reembolso where empresa_id=? order by id desc", (e["id"],))],
                "creditos": [{"lancamento_id": c["id"], "data": c["data"], "descricao": c["descricao_original"], "valor": formatar(c["valor_centavos"]),
                              "a_aplicar": formatar(c["valor_centavos"] - c["aplicado"])} for c in con.execute(
                    "select l.id, l.data, l.descricao_original, l.valor_centavos, coalesce(b.valor_centavos, 0) as aplicado from lancamento l "
                    "join conta cn on cn.id=l.conta_id left join reembolso_baixa b on b.credito_lancamento_id=l.id "
                    "where l.empresa_id=? and l.valor_centavos>0 and cn.pj=1 and l.valor_centavos > coalesce(b.valor_centavos, 0) order by l.data, l.id", (e["id"],))]})
        itens_lote = lote.itens_do_lote(con)
        aberto = con.execute("select id from lote_nibo where estado='montado' order by id desc limit 1").fetchone()
        return envelope(con, {"empresas": empresas, "lote": _lote_json(itens_lote, lote.texto_do_lote(itens_lote), aberto["id"] if aberto and itens_lote else None)},
                        agora=_agora(request))
    finally:
        con.close()


@router.post("/reembolsos")
async def reembolso_abrir(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Abre uma cobrança (a_cobrar) com os itens ainda sem cobrança da empresa contratante."""
    corpo = _corpo(await _json(request))
    con = _con(request)
    try:
        try:
            rid = rb.criar_reembolso(con, str(corpo.get("empresa_id", "")))
        except ValueError as e:
            raise erro(400, "requisicao_invalida", str(e))
        return envelope(con, {"id": rid}, agora=_agora(request))
    finally:
        con.close()


@router.post("/reembolsos/conciliar")
async def reembolso_conciliar(request: Request):
    """Baixa um crédito (entrada em conta PJ classificada como da empresa) contra os itens já cobrados, do mais antigo ao mais novo."""
    corpo = _corpo(await _json(request))
    con = _con(request)
    try:
        try:
            r = rb.conciliar_recebimento(con, str(corpo.get("empresa_id", "")), int(corpo.get("credito_id", 0)))
        except LookupError as e:
            raise erro(404, "nao_encontrado", str(e))
        except (ValueError, TypeError) as e:
            raise erro(400, "requisicao_invalida", str(e))
        return envelope(con, {"casados": r.casados, "sobra": formatar(r.sobra_centavos)}, agora=_agora(request))
    finally:
        con.close()


@router.post("/reembolsos/{rid}/cobrado")
def reembolso_cobrado(rid: int, request: Request):
    """Marca a cobrança como cobrada (a_cobrar → cobrado); repetir dá 409."""
    con = _con(request)
    try:
        try:
            rb.marcar_cobrado(con, rid)
        except LookupError as e:
            raise erro(404, "nao_encontrado", str(e))
        except ValueError as e:
            raise erro(409, "conflito", str(e))
        return envelope(con, {"id": rid, "estado": "cobrado"}, agora=_agora(request))
    finally:
        con.close()


@router.post("/lote/montar")
def lote_montar(request: Request):
    """Monta (ou remonta) o lote do dia para o Nibo da Bekaa e devolve o texto de confirmação gerado pelo servidor."""
    con = _con(request)
    try:
        l = lote.montar_lote(con, _agora(request).date())
        return envelope(con, _lote_json(l.itens, l.texto_confirmacao, l.id), agora=_agora(request))
    finally:
        con.close()


@router.post("/lote/{lote_id}/executar")
async def lote_executar(lote_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """ÚNICA gravação externa: grava o lote no Nibo. Exige {"confirmacao": <texto exato>}; divergência = 409 e nada é gravado."""
    corpo = _corpo(await _json(request))
    nibo = request.app.state.fontes["nibo"]()
    if nibo is None:
        raise erro(503, "fonte_indisponivel", "o Nibo não está configurado (NIBO_TOKEN)")
    paperless = request.app.state.fontes["paperless"]()
    con = _con(request)
    try:
        baixar = (lambda pid: (f"comprovante-{pid}.pdf", paperless.baixar(pid))) if paperless else None
        try:
            r = lote.executar_lote(con, lote_id, str(corpo.get("confirmacao", "")), nibo, baixar_comprovante=baixar)
        except LookupError as e:
            raise erro(404, "nao_encontrado", str(e))
        except lote.ConfirmacaoDivergente as e:
            raise erro(409, "confirmacao_divergente", str(e))
        except ValueError as e:
            raise erro(400, "requisicao_invalida", str(e))
        con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'cobrar')",
                    (_agora(request).isoformat(), ident.login, f"lote Nibo {lote_id}: {r.ok} ok, {r.erro} erro"))
        return envelope(con, {"ok": r.ok, "erro": r.erro}, agora=_agora(request))
    finally:
        con.close()


# ---------------- comprovantes ----------------
@router.get("/comprovantes")
def comprovantes(request: Request, desde: str | None = None):
    """Vínculos propostos (comprovante × lançamento, com confiança e motivo) e as despesas de empresa ainda sem comprovante (padrão: últimos 90 dias)."""
    con = _con(request)
    try:
        cand = [{"vinculo_id": r["vid"], "confianca": r["confianca"], "motivo": r["motivo"],
                 "comprovante": {"paperless_id": r["paperless_id"], "tipo": r["tipo"], "valor": formatar(r["cvalor"]), "data": r["cdata"]},
                 "lancamento": {"id": r["lid"], "data": r["ldata"], "descricao": r["descricao_original"], "valor": formatar(r["lvalor"]), "empresa": r["empresa_id"]}}
                for r in con.execute(
                    "select v.id as vid, v.confianca, v.motivo, c.paperless_id, c.tipo, c.valor_centavos as cvalor, c.data as cdata, "
                    "l.id as lid, l.data as ldata, l.descricao_original, l.valor_centavos as lvalor, l.empresa_id "
                    "from comprovante_vinculo v join comprovante c on c.id=v.comprovante_id join lancamento l on l.id=v.lancamento_id "
                    "where v.estado='proposto' order by v.confianca desc, v.id")]
        sem = [{"id": x["id"], "data": x["data"], "descricao": x["descricao_original"], "valor": formatar(-x["valor_centavos"]), "empresa_id": x["empresa_id"]}
               for x in cp_.sem_comprovante(con, _data(desde, "desde") or _agora(request).date() - dt.timedelta(days=90))]
        return envelope(con, {"candidatos": cand, "sem_comprovante": sem}, agora=_agora(request))
    finally:
        con.close()


def _decidir_vinculo(request: Request, vid: int, fn, ident):
    con = _con(request)
    try:
        try:
            fn(con, vid, ident.login)
        except LookupError as e:
            raise erro(404, "nao_encontrado", str(e))
        except ValueError as e:
            raise erro(409, "conflito", str(e))
        return envelope(con, {"id": vid}, agora=_agora(request))
    finally:
        con.close()


@router.post("/vinculos/{vid}/confirmar")
def vinculo_confirmar(vid: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Confirma um vínculo proposto (comprovante × lançamento); só o Ricardo confirma."""
    return _decidir_vinculo(request, vid, cp_.confirmar, ident)


@router.post("/vinculos/{vid}/rejeitar")
def vinculo_rejeitar(vid: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Rejeita um vínculo proposto; o par não volta a ser proposto como confirmado."""
    return _decidir_vinculo(request, vid, cp_.rejeitar, ident)


# ---------------- e-mail de cobrança (só rascunho, ADR-006) ----------------
def _cobranca_json(c: cb.Cobranca) -> dict:
    return {"id": c.id, "empresa_id": c.empresa_id, "para": c.para, "assunto": c.assunto, "corpo": c.corpo, "itens": len(c.itens),
            "total": formatar(sum(i.em_aberto_centavos for i in c.itens)), "anexos": len(c.anexos), "itens_sem_comprovante": c.aviso_sem_comprovante,
            "texto_confirmacao": cb.texto_confirmacao(c)}


def _bloco_json(b: dict) -> dict:
    return {"qtd": b["qtd"], "liquido": formatar(b["liquido_centavos"]), "bruto": formatar(b["bruto_centavos"]),
            "notas": [{"numero": n["numero"], "tomador": n["tomador"], "vencimento": n["vencimento"],
                       "liquido": formatar(n["liquido_centavos"] or 0), "bruto": formatar(n["bruto_centavos"] or 0)} for n in b["notas"]]}


@router.get("/previsao")
def previsao(request: Request, meses: int = 3):
    """Previsão de entradas a partir das NFS-e: a vencer, projetado (contrato recorrente) e, à parte, vencidas a confirmar pelo extrato."""
    if not 1 <= meses <= 12:
        raise erro(400, "requisicao_invalida", "meses deve estar entre 1 e 12")
    con = _con(request)
    try:
        agora = _agora(request)
        r = calcular_previsao(con, agora.date(), meses)
        dados = {"hoje": r["hoje"], "aviso": r["aviso"],
                 "meses": [{"mes": m["mes"], "a_vencer": _bloco_json(m["a_vencer"]), "projetado": _bloco_json(m["projetado"]),
                            "total_liquido": formatar(m["a_vencer"]["liquido_centavos"] + m["projetado"]["liquido_centavos"])} for m in r["meses"]],
                 "a_confirmar": _bloco_json(r["a_confirmar"]), "antigas": _bloco_json(r["antigas"])}
        return envelope(con, dados, agora=agora)
    finally:
        con.close()


@router.get("/notas")
def notas(request: Request, aberta: int = 0):
    """NFS-e autorizadas (Nibo): a vencer, vencidas a confirmar pelo extrato, antigas e as que o Nibo diz pagas (não é prova de recebimento)."""
    con = _con(request)
    try:
        hoje = _agora(request).date()
        itens, totais = [], {"a_vencer": 0, "a_confirmar": 0, "antigas": 0, "nibo_diz_pago": 0, "recebidas": 0}
        recebidas = {r[0] for r in con.execute("select nota_id from recebimento_nota where estado='confirmado'")}
        for n in con.execute("select * from nota_fiscal where status='autorizada'" + (" and nibo_pago=0" if aberta else "") + " order by vencimento desc, numero desc limit 400"):
            venc = dt.date.fromisoformat(n["vencimento"]) if n["vencimento"] else None
            if n["id"] in recebidas:
                sit, chave = "recebida", "recebidas"
            elif n["nibo_pago"]:
                sit, chave = "nibo_diz_pago", "nibo_diz_pago"
            elif venc is None or venc >= hoje:
                sit, chave = "a_vencer", "a_vencer"
            elif (hoje - venc).days <= RECENTE_DIAS:
                sit, chave = "a_confirmar", "a_confirmar"
            else:
                sit, chave = "antiga", "antigas"
            totais[chave] += n["valor_liquido_centavos"] or 0
            itens.append({"numero": n["numero"], "tomador": n["tomador_nome"], "emissao": n["emissao"], "vencimento": n["vencimento"],
                          "bruto": formatar(n["valor_bruto_centavos"]), "liquido": formatar(n["valor_liquido_centavos"] or 0), "situacao": sit,
                          "nibo_pago": bool(n["nibo_pago"]), "pdf": bool(n["pdf_arquivo"]), "xml": bool(n["xml_arquivo"])})
        return envelope(con, {"itens": itens, "totais": {k: formatar(v) for k, v in totais.items()}}, agora=_agora(request))
    finally:
        con.close()


@router.get("/recebimentos")
def recebimentos(request: Request):
    """Créditos do extrato que a Gabi propõe como recebimento de uma NFS-e (valor líquido igual); só o Ricardo confirma."""
    con = _con(request)
    try:
        itens = [{"id": r["id"], "confianca": r["confianca"], "motivo": r["motivo"],
                  "nota": {"numero": r["numero"], "tomador": r["tomador_nome"], "vencimento": r["vencimento"], "liquido": formatar(r["valor_liquido_centavos"] or 0)},
                  "lancamento": {"id": r["lid"], "data": r["data"], "descricao": r["descricao_original"], "valor": formatar(r["valor_centavos"])}}
                 for r in con.execute(
                     "select rn.id, rn.confianca, rn.motivo, n.numero, n.tomador_nome, n.vencimento, n.valor_liquido_centavos, l.id as lid, l.data, l.descricao_original, l.valor_centavos "
                     "from recebimento_nota rn join nota_fiscal n on n.id=rn.nota_id join lancamento l on l.id=rn.lancamento_id where rn.estado='proposto' "
                     "order by rn.confianca desc, rn.id")]
        return envelope(con, {"itens": itens}, agora=_agora(request))
    finally:
        con.close()


def _decidir_recebimento(request: Request, rid: int, acao, ident: Identidade):
    con = _con(request)
    try:
        try:
            acao(con, rid, ident.login)
        except LookupError as e:
            raise erro(404, "nao_encontrado", str(e))
        except ValueError as e:
            raise erro(409, "conflito", str(e))
        return envelope(con, {"id": rid, "ok": True}, agora=_agora(request))
    finally:
        con.close()


@router.post("/recebimentos/{rid}/confirmar")
async def recebimento_confirmar(rid: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Confirma o recebimento proposto (a nota deixa de ser prevista; as outras propostas da nota e do crédito caem)."""
    return _decidir_recebimento(request, rid, rec.confirmar_recebimento, ident)


@router.post("/recebimentos/{rid}/rejeitar")
async def recebimento_rejeitar(rid: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Rejeita o recebimento proposto (o mesmo par nota-crédito não volta a ser proposto)."""
    return _decidir_recebimento(request, rid, rec.rejeitar_recebimento, ident)


@router.get("/cobrancas")
def cobrancas(request: Request, empresa_id: str | None = None):
    """Rascunhos de cobrança guardados (opcionalmente de uma empresa)."""
    con = _con(request)
    try:
        itens = [{"id": r["id"], "empresa_id": r["empresa_id"], "para": r["para"], "assunto": r["assunto"], "criado_em": r["criado_em"], "itens": r["n"]}
                 for r in con.execute("select c.*, (select count(*) from cobranca_item i where i.cobranca_id=c.id) as n from cobranca c "
                                      "where (? is null or c.empresa_id=?) order by c.id desc", (empresa_id, empresa_id))]
        return envelope(con, {"itens": itens}, agora=_agora(request))
    finally:
        con.close()


@router.post("/cobrancas", status_code=201)
async def cobranca_montar(request: Request):
    """Monta o RASCUNHO do e-mail de cobrança (não envia). Corpo: {"empresa_id", "itens"?: [lancamento_id]}."""
    corpo = _corpo(await _json(request))
    con = _con(request)
    try:
        try:
            c = cb.montar(con, str(corpo.get("empresa_id", "")), corpo.get("itens"), hoje=_agora(request).date())
        except LookupError as e:
            raise erro(404, "nao_encontrado", str(e))
        except ValueError as e:
            raise erro(400, "requisicao_invalida", str(e))
        return envelope(con, _cobranca_json(c), agora=_agora(request))
    finally:
        con.close()


@router.post("/cobrancas/{cid}/enviar")
def cobranca_enviar(cid: int, request: Request):
    """Desabilitado (ADR-006): o app só guarda o rascunho."""
    con = _con(request)
    try:
        try:
            cb.enviar(con, cid)
        except cb.NaoPermitido as e:
            raise erro(403, "nao_permitido", str(e))
    finally:
        con.close()


# ---------------- pedidos do canal ----------------
@router.get("/pedidos")
def pedidos(request: Request, estado: str = "pendentes"):
    """Pedidos pendentes (inclui os com informação pedida) ou `decididos`."""
    if estado not in ("pendentes", "decididos"):
        raise erro(400, "requisicao_invalida", "estado deve ser pendentes ou decididos")
    con = _con(request)
    try:
        filtro = "p.estado in ('pendente','info_pedida')" if estado == "pendentes" else "p.estado in ('aprovado','recusado')"
        itens = [{"id": r["id"], "solicitante": r["nome"], "canal": r["canal"], "descricao": r["descricao"], "valor": formatar(r["valor_centavos"]) if r["valor_centavos"] is not None else None,
                  "vencimento": r["vencimento"], "pix_chave": r["pix_chave"], "anexo_paperless_id": r["anexo_paperless_id"], "estado": r["estado"],
                  "mensagem_original": r["mensagem_original"], "criado_em": r["criado_em"], "decidido_em": r["decidido_em"]}
                 for r in con.execute(f"select p.*, s.nome from pedido p join pessoa s on s.id=p.solicitante_pessoa_id where {filtro} order by p.id desc")]
        return envelope(con, {"itens": itens}, agora=_agora(request))
    finally:
        con.close()


@router.post("/pedidos/{pid}/decidir")
async def pedido_decidir(pid: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """aprovar (exige conta_id e beneficiario_id), recusar ou pedir_info. Só o Ricardo decide, pelo painel."""
    corpo = _corpo(await _json(request))
    con = _con(request)
    try:
        try:
            pedido = pd.estado(con, pid)
            if pedido["estado"] not in ("pendente", "info_pedida"):
                raise erro(409, "conflito", f"pedido {pid} já está {pedido['estado']}")
            pd.decidir(con, pid, str(corpo.get("acao", "")), ident.login, conta_id=corpo.get("conta_id"), beneficiario_id=corpo.get("beneficiario_id"),
                       mensagem=corpo.get("mensagem"))
        except LookupError as e:
            raise erro(404, "nao_encontrado", str(e))
        except ValueError as e:
            raise erro(400, "requisicao_invalida", str(e))
        if corpo.get("acao") == "aprovar":  # o pedido aprovado entra na agenda de contas a pagar
            contas_pagar.atualizar_compromissos(con, _agora(request).date(), _agora(request))
        return envelope(con, {"id": pid, "estado": pd.estado(con, pid)["estado"]}, agora=_agora(request))
    finally:
        con.close()
