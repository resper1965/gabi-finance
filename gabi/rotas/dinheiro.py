"""Rotas /api/v1 da Fase 1 (Dinheiro): caixa, contas a pagar, lançamentos, sugestões, regras, fontes. Só boss (Fase 4 abre por matriz).

Dinheiro sai como string decimal ("1234.56"); toda leitura leva o envelope (dados_ate da última rodada conferida).
Consome: dinheiro.{contas_pagar,regras,analise,repositorio,valor}, envelope, identidade.
"""
import datetime as dt
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request

from gabi.db import conectar
from gabi.dinheiro import analise, consultas, contas_pagar as cp, regras as rg, repositorio
from gabi.dinheiro.projecao import projetar
from gabi.dinheiro.valor import formatar, para_centavos
from gabi.envelope import envelope
from gabi.identidade import Identidade, exigir

router = APIRouter(prefix="/api/v1", dependencies=[Depends(exigir("boss"))])
PERIODOS = {"semana": 7, "mes": 30, "12m": 365}
EDITAVEIS = {"categoria_id", "beneficiario_id", "empresa_id", "frente_id"}


# ---------------- utilitários ----------------
def erro(status: int, codigo: str, mensagem: str) -> HTTPException:
    return HTTPException(status, detail={"erro": codigo, "mensagem": mensagem})


def _con(request: Request):
    return conectar(request.app.state.banco)


def _agora(request: Request) -> dt.datetime:
    return request.app.state.relogio()


def _m(centavos):
    return None if centavos is None else formatar(centavos)


def _data(texto: str | None, nome: str) -> dt.date | None:
    if texto is None:
        return None
    try:
        return dt.date.fromisoformat(texto)
    except ValueError:
        raise erro(400, "requisicao_invalida", f"{nome} deve ser AAAA-MM-DD")


def _corpo(corpo) -> dict:
    if not isinstance(corpo, dict):
        raise erro(400, "requisicao_invalida", "envie um objeto JSON")
    return corpo


async def _json(request: Request):
    try:
        return await request.json()
    except Exception:
        return None


# ---------------- caixa ----------------
def _serie_saldo(con, hoje: dt.date, dias: int, conta: str | None):
    contas = con.execute("select id, apelido, externo_id from conta where estado='sim' and tipo='BANK' and excluido_em is null").fetchall()
    if conta:
        contas = [c for c in contas if conta in (c["apelido"], c["externo_id"])]
    pontos = []
    for k in range(dias, -1, -1):
        d = hoje - dt.timedelta(days=k)
        total, algum = 0, False
        for c in contas:
            s = con.execute("select saldo_centavos from saldo where conta_id=? and em<=? order by em desc limit 1", (c["id"], f"{d.isoformat()}T23:59:59")).fetchone()
            if s:
                total, algum = total + s[0], True
        if algum:
            pontos.append({"data": d.isoformat(), "valor": formatar(total), "projecao": False})
    return pontos


@router.get("/caixa/projecao")
def caixa_projecao(request: Request, dias: int = 30):
    """Saldo projetado dia a dia (hoje até 90 dias): saldo atual, saídas de compromissos e faturas, entradas de NFS-e a vencer e recorrentes."""
    if not 1 <= dias <= 90:
        raise erro(400, "requisicao_invalida", "dias deve estar entre 1 e 90")
    con = _con(request)
    try:
        agora = _agora(request)
        serie = projetar(con, agora.date(), dias)
        menor = min(serie, key=lambda d: (d["saldo_centavos"], d["dia"]))
        inicial = cp.caixa_unico(con, agora.date()).saldo_centavos
        dados = {"saldo_inicial": formatar(inicial),
                 "dias": [{"dia": d["dia"], "entradas": formatar(d["entradas_centavos"]), "saidas": formatar(d["saidas_centavos"]), "saldo": formatar(d["saldo_centavos"])} for d in serie],
                 "menor_saldo": {"dia": menor["dia"], "saldo": formatar(menor["saldo_centavos"])},
                 "aviso": "Entradas só de notas ainda não vencidas e contratos recorrentes; o Nibo é defasado, então nota vencida e não baixada fica na fila de conferência e não entra."}
        return envelope(con, dados, agora=agora)
    finally:
        con.close()


@router.get("/caixa/resumo")
def caixa_resumo(request: Request, periodo: str = "mes", conta: str | None = None):
    """KPIs do caixa único, série de saldo (passado e projeção) e o que pede a sua atenção."""
    if periodo not in PERIODOS:
        raise erro(400, "requisicao_invalida", f"periodo deve ser um de {sorted(PERIODOS)}")
    con = _con(request)
    try:
        hoje = _agora(request).date()
        cx = cp.caixa_unico(con, hoje)
        contas = [c for c in cx.contas if not conta or conta == c["apelido"]]
        saldo = sum(c["saldo_centavos"] for c in contas)
        agenda = cp.contas_a_pagar(con, hoje)
        a_pagar = sum(i["valor_centavos"] or 0 for g in ("atrasadas", "hoje", "proximas") for i in agenda[g])
        fonte = repositorio.FonteAnalise(con)
        recorrentes = [r for r in analise.recorrentes(fonte, "custo", hoje) if r["sentido"] == "saida" and r["valor_medio"] < 600]
        assinaturas = sum(r["valor_medio"] for r in recorrentes)
        status_ass = {a["estabelecimento"]: a["status"] for a in con.execute("select estabelecimento, status from assinatura")}
        a_conferir = sum(1 for r in recorrentes if status_ass.get(r.get("chave") or r.get("descricao"), "a_conferir") == "a_conferir")
        abertas = [(f["vencimento"],) for f in cp.faturas_abertas(con, hoje)]
        serie = _serie_saldo(con, hoje, PERIODOS[periodo], conta)
        prev = analise.previsao(fonte, 14, None, hoje)
        delta = cx.saldo_centavos - para_centavos(prev["saldo_inicial"])  # projeção parte do saldo do caixa único
        serie += [{"data": e["data"], "valor": formatar(para_centavos(e["saldo"]) + delta), "projecao": True} for e in prev["eventos"]]
        atencao = []
        n_decidir = con.execute("select count(*) from conta where estado='a_decidir' and excluido_em is null").fetchone()[0]
        n_sug = con.execute("select count(*) from sugestao where estado='pendente'").fetchone()[0]
        for tipo, qtd, um, varios, rota in [
                ("atrasadas", len(agenda["atrasadas"]), "conta atrasada", "contas atrasadas", "/caixa/a-pagar"),
                ("a_conferir", len(agenda["a_conferir"]), "conta a conferir", "contas a conferir", "/caixa/a-pagar"),
                ("contas_a_decidir", n_decidir, "conta nova esperando você decidir se entra no caixa único",
                 "contas novas esperando você decidir se entram no caixa único", "/cadastros/contas"),
                ("sugestoes_pendentes", n_sug, "sugestão da Gabi para você revisar", "sugestões da Gabi para você revisar", "/regras")]:
            if qtd:
                atencao.append({"tipo": tipo, "quantidade": qtd, "texto": f"{qtd} {um if qtd == 1 else varios}", "rota": rota})
        dados = {"kpis": {"saldo": formatar(saldo), "a_pagar_7_dias": formatar(a_pagar), "a_receber": None,
                          "faturas_abertas": formatar(cx.faturas_abertas_centavos), "assinaturas_mes": formatar(para_centavos(round(assinaturas, 2)))},
                 "detalhe": {"saldo_por_conta": [{"apelido": c["apelido"], "saldo": formatar(c["saldo_centavos"])} for c in contas],
                             "a_pagar_contas": sum(len(agenda[g]) for g in ("atrasadas", "hoje", "proximas")), "a_pagar_vencidas": len(agenda["atrasadas"]),
                             "cartoes_abertos": len(abertas), "proxima_fatura": abertas[0][0] if abertas else None,
                             "assinaturas_ativas": len(recorrentes), "assinaturas_a_conferir": a_conferir},
                 "serie_saldo": serie, "atencao": atencao}
        return envelope(con, dados, agora=_agora(request))
    finally:
        con.close()


# ---------------- contas a pagar ----------------
def _item_pagar(i: dict) -> dict:
    saida = {k: v for k, v in i.items() if k not in ("valor_centavos", "diferenca_centavos")}
    saida["valor"] = _m(i["valor_centavos"])
    if "diferenca_centavos" in i:
        saida["diferenca"] = _m(i["diferenca_centavos"])
    return saida


@router.get("/contas-pagar")
def contas_pagar(request: Request, ate: str | None = None):
    """Contas agrupadas: atrasadas, hoje, próximas, adiante, débito automático, a conferir e pagas."""
    con = _con(request)
    try:
        grupos = cp.contas_a_pagar(con, _agora(request).date(), _data(ate, "ate"))
        return envelope(con, {g: [_item_pagar(i) for i in itens] for g, itens in grupos.items()}, agora=_agora(request))
    finally:
        con.close()


@router.post("/contas-pagar/{id_compromisso:path}/paga")
def marcar_paga(id_compromisso: str, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Baixa manual de um compromisso (vale só se não houver lançamento no extrato)."""
    con = _con(request)
    try:
        hoje = _agora(request).date()
        try:
            cp.marcar_paga_manual(con, id_compromisso, ident.login, hoje)
        except LookupError as e:
            raise erro(404, "nao_encontrado", str(e))
        except ValueError as e:
            raise erro(400, "requisicao_invalida", str(e))
        cp.atualizar_compromissos(con, hoje, _agora(request))
        r = con.execute("select estado from compromisso where id=?", (id_compromisso,)).fetchone()
        return {"id": id_compromisso, "estado": r["estado"] if r else None}
    finally:
        con.close()


# ---------------- lançamentos ----------------
_SQL_LANC = consultas.SQL_LANCAMENTO
_lanc = consultas.lancamento_dict


@router.get("/lancamentos")
def lancamentos(request: Request, pendente: str | None = None, de: str | None = None, ate: str | None = None, conta: str | None = None,
                categoria: int | None = None, para_quem: str | None = None, empresa: str | None = None, texto: str | None = None,
                limite: int = 50, offset: int = 0):
    """Lançamentos paginados, com filtros e a origem de cada classificação."""
    con = _con(request)
    try:
        try:
            dados = consultas.listar_lancamentos(con, pendente=pendente, de=de, ate=ate, conta=conta, categoria=categoria, para_quem=para_quem,
                                                 empresa=empresa, texto=texto, limite=limite, offset=offset)
        except ValueError as e:
            raise erro(400, "requisicao_invalida", str(e))
        return envelope(con, dados, agora=_agora(request))
    finally:
        con.close()


def _validar_mudancas(con, m: dict) -> dict:
    """{categoria_id, beneficiario_id, empresa_id, frente_id} -> colunas, validando existência. None limpa o campo."""
    if not m:
        raise erro(400, "requisicao_invalida", "informe ao menos um campo para mudar")
    if set(m) - EDITAVEIS:
        raise erro(400, "requisicao_invalida", f"campos que não se editam: {sorted(set(m) - EDITAVEIS)}")
    saida = {}
    for chave, valor in m.items():
        col = "para_quem_id" if chave == "beneficiario_id" else chave
        if valor is not None:
            if chave == "frente_id":
                if not isinstance(valor, int) or isinstance(valor, bool):
                    raise erro(400, "requisicao_invalida", "frente_id deve ser inteiro")
            else:
                tabela = {"categoria_id": "categoria", "beneficiario_id": "pessoa", "empresa_id": "empresa"}[chave]
                if con.execute(f"select 1 from {tabela} where id=?", (valor,)).fetchone() is None:
                    raise erro(400, "requisicao_invalida", f"{chave}={valor!r} não existe")
        saida[col] = valor
    return saida


def _aplicar_mudancas(con, ids: list[int], cols: dict) -> None:
    for lid in ids:
        for col, valor in cols.items():
            origem = f"{col[:-3]}_origem" if col != "frente_id" else None
            if origem:
                con.execute(f"update lancamento set {col}=?, {origem}=? where id=?", (valor, "voce" if valor is not None else None, lid))
            else:
                con.execute(f"update lancamento set {col}=? where id=?", (valor, lid))


@router.patch("/lancamentos/{lid}")
async def lancamento_patch(lid: int, request: Request):
    """Muda categoria, para quem, empresa ou frente de um lançamento (a origem vira 'voce')."""
    corpo = _corpo(await _json(request))
    con = _con(request)
    try:
        if con.execute("select 1 from lancamento where id=?", (lid,)).fetchone() is None:
            raise erro(404, "nao_encontrado", f"lançamento {lid} não existe")
        cols = _validar_mudancas(con, corpo)
        con.execute("begin")
        try:
            _aplicar_mudancas(con, [lid], cols)
            con.execute("commit")
        except BaseException:
            con.execute("rollback")
            raise
        return envelope(con, _lanc(con.execute(f"{_SQL_LANC} where l.id=?", (lid,)).fetchone()), agora=_agora(request))
    finally:
        con.close()


@router.post("/lancamentos/lote")
async def lancamentos_lote(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Muda vários lançamentos de uma vez; criar_regra cria uma regra por estabelecimento."""
    corpo = _corpo(await _json(request))
    ids = corpo.get("ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        raise erro(400, "requisicao_invalida", "ids deve ser uma lista não vazia de inteiros")
    con = _con(request)
    try:
        cols = _validar_mudancas(con, corpo.get("mudancas") or {})
        faltam = [i for i in ids if con.execute("select 1 from lancamento where id=?", (i,)).fetchone() is None]
        if faltam:
            raise erro(404, "nao_encontrado", f"lançamentos inexistentes: {faltam}")
        con.execute("begin")
        try:
            _aplicar_mudancas(con, ids, cols)
            con.execute("commit")
        except BaseException:
            con.execute("rollback")
            raise
        regras = []
        if corpo.get("criar_regra") is True:
            vistos = set()
            for lid in ids:
                r = con.execute("select estabelecimento, descricao_original from lancamento where id=?", (lid,)).fetchone()
                chave = r["estabelecimento"] or r["descricao_original"]
                if chave and chave not in vistos:
                    vistos.add(chave)
                    try:
                        regras.append(rg.sempre_assim(con, lid, ident.login))
                    except ValueError:
                        pass  # nada decidido neste lançamento (ex.: campo limpo): não há o que virar regra
        return envelope(con, {"atualizados": len(ids), "regras": regras}, agora=_agora(request))
    finally:
        con.close()


# ---------------- sugestões e regras ----------------
def _sug(con, r, hoje) -> dict:
    payload = json.loads(r["payload"])
    impacto = None
    if r["tipo"] == "regra":
        try:
            impacto = rg.contar_afetados(con, payload.get("padrao"), payload.get("acao"), hoje)
        except ValueError:
            impacto = None
    return {"id": r["id"], "tipo": r["tipo"], "lancamento_id": r["lancamento_id"], "payload": payload, "estado": r["estado"],
            "motivo": r["motivo"], "criado_em": r["criado_em"], "decidida_em": r["decidida_em"], "impacto": impacto}


@router.get("/sugestoes")
def sugestoes(request: Request, estado: str = "pendente"):
    """Sugestões da Gabi (padrão: pendentes), com o impacto de cada regra."""
    if estado not in ("pendente", "aprovada", "rejeitada"):
        raise erro(400, "requisicao_invalida", "estado inválido")
    con = _con(request)
    try:
        hoje = _agora(request).date()
        itens = [_sug(con, r, hoje) for r in con.execute("select * from sugestao where estado=? order by id", (estado,))]
        return envelope(con, {"itens": itens}, agora=_agora(request))
    finally:
        con.close()


def _decidir(request: Request, fn):
    con = _con(request)
    try:
        try:
            return fn(con)
        except LookupError as e:
            raise erro(404, "nao_encontrado", str(e))
        except rg.ConflitoDeEstado as e:
            raise erro(409, "conflito", str(e))
        except ValueError as e:
            raise erro(400, "requisicao_invalida", str(e))
    finally:
        con.close()


@router.post("/sugestoes/{sid}/aprovar")
async def sugestao_aprovar(sid: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Aprova uma sugestão; sugestão de regra cria a regra ATIVA e a aplica ao passado."""
    corpo = await _json(request)
    edicao = corpo.get("edicao") if isinstance(corpo, dict) else None
    return _decidir(request, lambda con: envelope(con, {"regra_id": rg.aprovar(con, sid, edicao, ident.login)}, agora=_agora(request)))


@router.post("/sugestoes/{sid}/rejeitar")
def sugestao_rejeitar(sid: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Rejeita uma sugestão (nada é criado)."""
    def fazer(con):
        rg.rejeitar(con, sid, ident.login)
        return {"id": sid, "estado": "rejeitada"}
    return _decidir(request, fazer)


def _regra(r) -> dict:
    return {"id": r["id"], "padrao": r["padrao"], "acao": json.loads(r["acao"]), "ativa": bool(r["ativa"]),
            "criado_em": r["criado_em"], "criada_por": r["criada_por"]}


@router.get("/regras")
def regras(request: Request):
    """Regras de classificação."""
    con = _con(request)
    try:
        itens = [{**_regra(r), "casam": rg.contar_casados(con, r["padrao"])} for r in con.execute("select * from regra order by id")]
        return envelope(con, {"itens": itens}, agora=_agora(request))
    finally:
        con.close()


@router.patch("/regras/{rid}")
async def regra_patch(rid: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Liga ou desliga uma regra; ligar aplica ao passado."""
    corpo = _corpo(await _json(request))
    if not isinstance(corpo.get("ativa"), bool):
        raise erro(400, "requisicao_invalida", "ativa deve ser true ou false")

    def fazer(con):
        rg.definir_ativa(con, rid, corpo["ativa"], ident.login)
        return envelope(con, _regra(con.execute("select * from regra where id=?", (rid,)).fetchone()), agora=_agora(request))
    return _decidir(request, fazer)


# ---------------- fontes e rodadas ----------------
@router.get("/fontes")
def fontes(request: Request):
    """Estado de cada fonte: ok, nao_conferida, erro ou parada."""
    con = _con(request)
    try:
        e = envelope(con, None, agora=_agora(request))
        e["dados"] = {"fontes": e["fontes"]}
        return e
    finally:
        con.close()


@router.get("/rodadas")
def rodadas(request: Request, limite: int = 50):
    """Últimas rodadas de ingestão e se foram conferidas."""
    con = _con(request)
    try:
        def reprovadas(rodada_id):  # só contas liberadas travam a rodada; o resto é registrado mas não aparece aqui
            return [{"conta": x["apelido"] or x["instituicao"], "tipo": x["tipo"], "detalhe": x["detalhe"]} for x in con.execute(
                "select c.apelido, c.instituicao, cf.tipo, cf.detalhe from conferencia cf join conta c on c.id=cf.conta_id "
                "where cf.rodada_id=? and cf.ok=0 and c.estado='sim' and c.excluido_em is null order by c.id, cf.tipo", (rodada_id,))]

        itens = [{"id": r["id"], "fonte": r["fonte"], "inicio": r["inicio"], "fim": r["fim"], "status": r["status"], "lidos": r["lidos"],
                  "novos": r["novos"], "alterados": r["alterados"], "erro": r["erro"], "conferida": bool(r["conferida"]),
                  "reprovadas": [] if r["conferida"] else reprovadas(r["id"])}
                 for r in con.execute("select * from rodada order by id desc limit ?", (min(max(limite, 1), 200),))]
        return envelope(con, {"itens": itens}, agora=_agora(request))
    finally:
        con.close()
