"""Classificação em cascata de um lançamento (spec: regra -> equivalência do banco -> cache -> modelo).

R1: só as camadas que o Ricardo aprovou GRAVAM (regra ativa, equivalência de categorias). Cache por estabelecimento e
modelo só criam SUGESTÃO pendente. Preenche apenas campos vazios; nunca sobrescreve origem `voce`.
Consome: db (lancamento, regra, equivalencia_categoria, sugestao).
"""
import json
import re
from dataclasses import dataclass

from gabi.dinheiro.regras import casa

CAMPOS = (("categoria", "categoria_id"), ("para_quem", "para_quem_id"), ("empresa", "empresa_id"))
CONFIANCA = {"regra": 1.0, "banco": 0.9, "cache": 0.6}


@dataclass(frozen=True)
class Classificacao:
    categoria_id: int | None
    para_quem_id: str | None
    empresa_id: str | None
    origens: dict          # campos preenchidos NESTA chamada -> origem ('regra' | 'banco')
    confianca: float


@dataclass(frozen=True)
class ResumoClassificacao:
    examinados: int
    resolvidos: int
    sugestoes: int


def _regras_ativas(con) -> list[tuple[re.Pattern, dict]]:
    """Regras ligadas pelo Ricardo, por id. Regex ou ação inválidos (dado digitado por pessoa) são ignorados."""
    saida = []
    for r in con.execute("select padrao, acao from regra where ativa=1 order by id"):
        try:
            acao = json.loads(r["acao"])
            if not isinstance(acao, dict):
                continue
            saida.append((re.compile(r["padrao"], re.I), acao))
        except (ValueError, re.error):
            continue
    return saida


def _preencher(con, lid: int, campo: str, col: str, valor, origem: str) -> None:
    con.execute(f"update lancamento set {col}=?, {campo}_origem=? where id=?", (valor, origem, lid))


def _sugerir_por_cache(con, lid: int, estab: str, campo: str, col: str) -> bool:
    """Decisões anteriores do Ricardo para o mesmo estabelecimento, todas iguais: sugere (não grava)."""
    valores = {r[0] for r in con.execute(
        f"select {col} from lancamento where estabelecimento=? and {campo}_origem='voce' and {col} is not null and id<>?",
        (estab, lid))}
    if len(valores) != 1:
        return False
    if con.execute("select 1 from sugestao where lancamento_id=? and tipo=? and estado='pendente'", (lid, campo)).fetchone():
        return False
    con.execute("insert into sugestao(tipo, lancamento_id, payload, motivo, criado_em) values (?,?,?,?, datetime('now'))",
                (campo, lid, json.dumps({col: next(iter(valores))}),
                 f"você classificou assim os outros lançamentos de {estab}"))
    return True


def classificar(con, lancamento_id: int) -> Classificacao:
    r = con.execute("select * from lancamento where id=?", (lancamento_id,)).fetchone()
    if r is None:
        raise LookupError(f"lançamento {lancamento_id} não existe")
    atual = {col: r[col] for _, col in CAMPOS}
    origens: dict[str, str] = {}
    confianca = 0.0

    # 1) regra ativa do Ricardo: a primeira que casa (por id) preenche os campos vazios
    for padrao, acao in _regras_ativas(con):
        if casa(padrao, r["descricao_original"], r["estabelecimento"]):
            for campo, col in CAMPOS:
                if atual[col] is None and acao.get(col) is not None:
                    _preencher(con, lancamento_id, campo, col, acao[col], "regra")
                    atual[col], origens[campo], confianca = acao[col], "regra", CONFIANCA["regra"]
            break

    # 2) equivalência categoria do banco -> categoria nossa
    if atual["categoria_id"] is None and r["categoria_banco"]:
        e = con.execute("select categoria_id from equivalencia_categoria where origem_pluggy=?", (r["categoria_banco"],)).fetchone()
        if e:
            _preencher(con, lancamento_id, "categoria", "categoria_id", e["categoria_id"], "banco")
            atual["categoria_id"], origens["categoria"] = e["categoria_id"], "banco"
            confianca = max(confianca, CONFIANCA["banco"])

    # 3) cache por estabelecimento: só sugestão
    if r["estabelecimento"]:
        for campo, col in CAMPOS[:2]:
            if atual[col] is None and _sugerir_por_cache(con, lancamento_id, r["estabelecimento"], campo, col):
                confianca = max(confianca, CONFIANCA["cache"])

    return Classificacao(atual["categoria_id"], atual["para_quem_id"], atual["empresa_id"], origens, confianca)


def classificar_pendentes(con) -> ResumoClassificacao:
    ids = [r[0] for r in con.execute("select id from lancamento where categoria_id is null or para_quem_id is null order by id")]
    antes = con.execute("select count(*) from sugestao").fetchone()[0]
    resolvidos = sum(1 for i in ids if classificar(con, i).origens)
    return ResumoClassificacao(len(ids), resolvidos, con.execute("select count(*) from sugestao").fetchone()[0] - antes)
