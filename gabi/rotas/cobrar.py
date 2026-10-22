"""Rotas de Cobrar: o que vou receber (previsão, notas, a receber, recebimentos). Só o Ricardo (boss). Nada é enviado (R2).
Reembolso PJ, lote do Nibo, comprovantes, rascunho de cobrança e pedidos saíram (ADR-023). Consome: cobrar.*."""
import datetime as dt

from fastapi import APIRouter, Depends, Request

from gabi.cobrar import recebimentos as rec
from gabi.cobrar.a_receber import a_receber_do_mes
from gabi.cobrar.previsao import RECENTE_DIAS, previsao as calcular_previsao
from gabi.dinheiro.valor import formatar
from gabi.envelope import envelope
from gabi.identidade import Identidade, exigir
from gabi.rotas.dinheiro import _agora, _con, erro

router = APIRouter(prefix="/api/v1/cobrar", dependencies=[Depends(exigir("boss"))])


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


@router.get("/a-receber")
def a_receber(request: Request):
    """O que se espera receber neste mês e se já entrou: pagadores recorrentes do extrato e NFS-e do mês, em blocos separados (não somar os dois)."""
    con = _con(request)
    try:
        d = a_receber_do_mes(con, _agora(request).date())
        fmt = lambda t: {k.removesuffix("_centavos"): formatar(v) for k, v in t.items()}  # noqa: E731
        for i in d["recorrentes"] + d["notas"]:
            i["esperado"], i["recebido"] = formatar(i.pop("esperado_centavos")), (formatar(i["recebido_centavos"]) if i["recebido_centavos"] is not None else None)
            i.pop("recebido_centavos")
        d["totais"] = {k: fmt(v) for k, v in d["totais"].items()}
        return envelope(con, d, agora=_agora(request))
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
                     "order by rn.confianca desc, rn.id limit 100")]
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


