"""Reembolsos de despesas pagas no PF para empresas contratantes (ness, IONIC): a_cobrar → cobrado → parcialmente_recebido → quitado.
Baixa por crédito em conta PJ, do item mais antigo para o mais novo. A Bekaa (`pj_titular`) nunca gera cobrança: vai ao lote do Nibo (T2.4).
Consome: cadastros (empresa.dados.relacao), lancamento, conta.pj."""
import datetime as dt
from dataclasses import dataclass

from gabi.cobrar import cadastro
from gabi.db import transacao
from gabi.cobrar.util import agora as _agora


@dataclass(frozen=True)
class ItemReembolso:
    lancamento_id: int
    data: str
    descricao: str | None
    valor_centavos: int
    em_aberto_centavos: int


@dataclass(frozen=True)
class ResultadoConciliacao:
    casados: list[int]       # lançamentos quitados por este crédito
    sobra_centavos: int      # parte do crédito que não achou item cobrado em aberto


def _contratante(con, empresa_id: str) -> bool:
    return cadastro.relacao(con, empresa_id) == "contratante"


def itens_a_reembolsar(con, empresa_id: str) -> list[ItemReembolso]:
    """Saídas da empresa pagas em conta que não é PJ, ainda não quitadas (inclui as já em cobrança). Só contratantes."""
    if not _contratante(con, empresa_id):
        return []
    return [ItemReembolso(r["id"], r["data"], r["descricao_original"], -r["valor_centavos"], -r["valor_centavos"] - (r["recebido"] or 0))
            for r in con.execute(
                "select l.id, l.data, l.descricao_original, l.valor_centavos, ri.recebido_centavos as recebido from lancamento l "
                "join conta c on c.id=l.conta_id left join reembolso_item ri on ri.lancamento_id=l.id "
                "where l.empresa_id=? and l.valor_centavos<0 and c.pj=0 and coalesce(ri.recebido_centavos,0) < -l.valor_centavos "
                "order by l.data, l.id", (empresa_id,))]


def criar_reembolso(con, empresa_id: str, itens: list[int] | None = None) -> int:
    """Abre uma cobrança (a_cobrar) com os itens ainda sem cobrança (ou só os `itens` escolhidos). Bekaa/empresa sem relação: ValueError. Tudo ou nada."""
    with transacao(con):
        return _criar_reembolso(con, empresa_id, itens)


def _criar_reembolso(con, empresa_id: str, itens: list[int] | None = None) -> int:
    """Abre uma cobrança (a_cobrar) com os itens ainda sem cobrança. Bekaa/empresa sem relação: ValueError."""
    if not _contratante(con, empresa_id):
        raise ValueError("a Bekaa vai pelo lote do Nibo, não por cobrança" if cadastro.relacao(con, empresa_id) == "pj_titular"
                         else "a empresa não está cadastrada como contratante")
    novos = [i for i in itens_a_reembolsar(con, empresa_id)
             if not con.execute("select 1 from reembolso_item where lancamento_id=?", (i.lancamento_id,)).fetchone()]
    if itens is not None:
        if not set(itens) <= {i.lancamento_id for i in novos}:
            raise ValueError("há item selecionado que não está em aberto para esta empresa")
        novos = [i for i in novos if i.lancamento_id in set(itens)]
    if not novos:
        raise ValueError("nada a cobrar")
    rid = con.execute("insert into reembolso(empresa_id, criado_em) values (?,?)", (empresa_id, _agora())).lastrowid
    for i in novos:
        con.execute("insert into reembolso_item(reembolso_id, lancamento_id, valor_centavos) values (?,?,?)", (rid, i.lancamento_id, i.valor_centavos))
    return rid


def marcar_cobrado(con, reembolso_id: int) -> None:
    r = con.execute("select estado from reembolso where id=?", (reembolso_id,)).fetchone()
    if r is None:
        raise LookupError(f"reembolso {reembolso_id} não existe")
    if r["estado"] != "a_cobrar":
        raise ValueError(f"reembolso {reembolso_id} já está {r['estado']}")
    con.execute("update reembolso set estado='cobrado', cobrado_em=? where id=?", (_agora(), reembolso_id))


def _atualizar_estado(con, reembolso_id: int) -> None:
    pago, total, cheios = con.execute("select sum(recebido_centavos), sum(valor_centavos), sum(recebido_centavos=valor_centavos) "
                                      "from reembolso_item where reembolso_id=?", (reembolso_id,)).fetchone()
    itens = con.execute("select count(*) from reembolso_item where reembolso_id=?", (reembolso_id,)).fetchone()[0]
    estado = "quitado" if cheios == itens else ("parcialmente_recebido" if pago else "cobrado")
    con.execute("update reembolso set estado=? where id=?", (estado, reembolso_id))


def conciliar_recebimento(con, empresa_id: str, credito_id: int) -> ResultadoConciliacao:
    """Baixa um crédito (entrada em conta PJ, classificado como da empresa) contra os itens JÁ COBRADOS, do mais antigo ao mais novo.
    Só o que foi de fato aplicado fica registrado: a sobra (ou um crédito que chegou antes da cobrança) pode ser aplicada depois. Tudo ou nada."""
    with transacao(con):
        return _conciliar(con, empresa_id, credito_id)


def _conciliar(con, empresa_id: str, credito_id: int) -> ResultadoConciliacao:
    c = con.execute("select l.valor_centavos, l.empresa_id, cn.pj from lancamento l join conta cn on cn.id=l.conta_id where l.id=?", (credito_id,)).fetchone()
    if c is None:
        raise LookupError(f"lançamento {credito_id} não existe")
    if c["valor_centavos"] <= 0 or not c["pj"]:
        raise ValueError("o recebimento precisa ser uma entrada em conta PJ")
    if c["empresa_id"] != empresa_id:
        raise ValueError(f"classifique o crédito como da empresa {empresa_id} antes de baixar os reembolsos")
    antes = con.execute("select valor_centavos from reembolso_baixa where credito_lancamento_id=?", (credito_id,)).fetchone()
    aplicado_antes = antes["valor_centavos"] if antes else 0
    restante = inicial = c["valor_centavos"] - aplicado_antes
    if restante <= 0:
        return ResultadoConciliacao([], 0)  # já aplicado por inteiro
    casados, tocados = [], set()
    for it in con.execute(
            "select ri.reembolso_id, ri.lancamento_id, ri.valor_centavos, ri.recebido_centavos, l.data from reembolso_item ri "
            "join reembolso r on r.id=ri.reembolso_id join lancamento l on l.id=ri.lancamento_id "
            "where r.empresa_id=? and r.estado in ('cobrado','parcialmente_recebido') and ri.recebido_centavos<ri.valor_centavos "
            "order by l.data, l.id", (empresa_id,)).fetchall():
        if restante <= 0:
            break
        falta = it["valor_centavos"] - it["recebido_centavos"]
        pagar = min(restante, falta)
        con.execute("update reembolso_item set recebido_centavos=recebido_centavos+? where reembolso_id=? and lancamento_id=?",
                    (pagar, it["reembolso_id"], it["lancamento_id"]))
        restante -= pagar
        tocados.add(it["reembolso_id"])
        if pagar == falta:
            casados.append(it["lancamento_id"])
    for rid in tocados:
        _atualizar_estado(con, rid)
    aplicado = inicial - restante
    if aplicado > 0:
        con.execute("insert into reembolso_baixa(credito_lancamento_id, empresa_id, valor_centavos, criado_em) values (?,?,?,?) "
                    "on conflict(credito_lancamento_id) do update set valor_centavos=valor_centavos+excluded.valor_centavos", (credito_id, empresa_id, aplicado, _agora()))
    return ResultadoConciliacao(casados, restante)
