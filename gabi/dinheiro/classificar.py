"""Classificação em cascata de um lançamento (spec: regra -> equivalência do banco -> cache -> modelo).

R1: só as camadas que o Ricardo aprovou GRAVAM (regra ativa, equivalência de categorias). Cache por estabelecimento e
modelo só criam SUGESTÃO pendente. Preenche apenas campos vazios; nunca sobrescreve origem `voce`.
Consome: db (lancamento, regra, equivalencia_categoria, sugestao).
"""
import json
import re
import unicodedata
from dataclasses import dataclass

from gabi.dinheiro.condicao import confere
from gabi.dinheiro.regras import casa

CAMPOS = (("categoria", "categoria_id"), ("para_quem", "para_quem_id"), ("empresa", "empresa_id"))
CONFIANCA = {"regra": 1.0, "banco": 0.9, "cache": 0.6}
MIN_DECISOES_CERTEIRO = 2  # "para quem" é aplicado sozinho quando o Ricardo já decidiu ao menos isto, sempre igual, para o estabelecimento (ADR-023)
QUEM_CERTEIRO = "gabi (para quem certeiro)"


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


def _regras_ativas(con) -> list[tuple[re.Pattern, dict, dict | None]]:
    """Regras ligadas pelo Ricardo, por id. Regex ou ação inválidos (dado digitado por pessoa) são ignorados."""
    saida = []
    for r in con.execute("select padrao, acao, condicao from regra where ativa=1 order by id"):
        try:
            acao = json.loads(r["acao"])
            if not isinstance(acao, dict):
                continue
            saida.append((re.compile(r["padrao"], re.I), acao, json.loads(r["condicao"]) if r["condicao"] else None))
        except (ValueError, re.error):
            continue
    return saida


def _preencher(con, lid: int, campo: str, col: str, valor, origem: str) -> None:
    con.execute(f"update lancamento set {col}=?, {campo}_origem=? where id=?", (valor, origem, lid))


def para_quem_certeiro(con, lid: int, estab: str | None) -> str | None:
    """A pessoa que o Ricardo escolheu em TODAS as suas decisões (>= MIN_DECISOES_CERTEIRO) para o mesmo estabelecimento; senão None."""
    if not estab:
        return None
    r = con.execute("select count(*) n, count(distinct para_quem_id) d, max(para_quem_id) p from lancamento "
                    "where estabelecimento=? and para_quem_origem='voce' and para_quem_id is not null and id<>?", (estab, lid)).fetchone()
    return r["p"] if r["n"] >= MIN_DECISOES_CERTEIRO and r["d"] == 1 else None


def aplicar_certeiro(con, lid: int, estab: str, pessoa: str) -> None:
    """Preenche com origem 'gabi' e registra em `decisao` (o Ricardo desfaz trocando a pessoa no painel: vira 'voce')."""
    _preencher(con, lid, "para_quem", "para_quem_id", pessoa, "gabi")
    con.execute("insert into decisao(quando, quem, o_que, origem) values (datetime('now'), ?, ?, 'classificacao')",
                (QUEM_CERTEIRO, f"lançamento {lid}: para quem = {pessoa} ({estab}: todas as suas decisões foram iguais)"))


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


def _norm(t: str | None) -> str:
    return " ".join("".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").upper().split())


def _responsavel(con, r) -> str | None:
    """Pagamento (saída) a quem responde por UMA filha (pessoa.dados.responsavel_por) vai para ela. O nome do favorecido vem no
    descritivo: casa pelos dois primeiros nomes da pessoa. Responsável por duas ou mais: não adivinha."""
    if r["valor_centavos"] >= 0:
        return None
    texto = _norm(f"{r['descricao_original']} {r['estabelecimento']}")
    for p in con.execute("select nome, dados from pessoa where dados like '%responsavel_por%'"):
        try:
            alvo = json.loads(p["dados"] or "{}").get("responsavel_por")
        except ValueError:
            continue
        toks = _norm(p["nome"]).split()[:2]
        if isinstance(alvo, list) and len(alvo) == 1 and toks and all(t in texto for t in toks):
            return alvo[0]
    return None


def _padrao_do_compromisso(con, externo_id: str):
    return con.execute(
        "select cp.para_quem_id, cp.categoria_id from conciliacao co join compromisso c on c.id=co.compromisso_id "
        "join compromisso_padrao cp on cp.linha_id=c.linha_id where co.tx_id=?", (externo_id,)).fetchone()


def _usuario_unico(con, conta_id: int) -> str | None:
    u = con.execute("select usuarios from conta where id=?", (conta_id,)).fetchone()
    try:
        lista = json.loads(u["usuarios"]) if u and u["usuarios"] else []
    except ValueError:
        return None
    return lista[0] if isinstance(lista, list) and len(lista) == 1 else None


def classificar(con, lancamento_id: int) -> Classificacao:
    r = con.execute("select * from lancamento where id=?", (lancamento_id,)).fetchone()
    if r is None:
        raise LookupError(f"lançamento {lancamento_id} não existe")
    atual = {col: r[col] for _, col in CAMPOS}
    origens: dict[str, str] = {}
    confianca = 0.0

    # 1) regra ativa do Ricardo: a primeira que casa (por id) preenche os campos vazios
    for padrao, acao, condicao in _regras_ativas(con):
        if casa(padrao, r["descricao_original"], r["estabelecimento"]) and confere(condicao, r):
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

    # 2b) "para quem" sem perguntar (padrões que o Ricardo cadastrou), só se ainda vazio. Ordem: responsável > compromisso > conta > categoria.
    #     Origem 'fonte' (padrão do cadastro): uma regra por estabelecimento que ele dita vence, e 'voce'/'regra' nunca são sobrescritos
    #     (a coluna só aceita banco|regra|gabi|voce|fonte).
    if atual["para_quem_id"] is None:
        dono = _responsavel(con, r)
        if dono is None:
            comp = _padrao_do_compromisso(con, r["externo_id"])
            if comp and comp["categoria_id"] is not None and atual["categoria_id"] is None:
                _preencher(con, lancamento_id, "categoria", "categoria_id", comp["categoria_id"], "fonte")
                atual["categoria_id"], origens["categoria"] = comp["categoria_id"], "fonte"
            dono = comp["para_quem_id"] if comp else None
        if dono is None:
            dono = _usuario_unico(con, r["conta_id"])
        if dono is None and atual["categoria_id"] is not None:
            c = con.execute("select dono_padrao from categoria where id=?", (atual["categoria_id"],)).fetchone()
            dono = c["dono_padrao"] if c else None
        if dono is not None:
            _preencher(con, lancamento_id, "para_quem", "para_quem_id", dono, "fonte")
            atual["para_quem_id"], origens["para_quem"], confianca = dono, "fonte", max(confianca, CONFIANCA["regra"])

    # 3) "para quem" certeiro: todas as decisões do Ricardo para o estabelecimento (>= 2) iguais -> aplica sozinho (ADR-023)
    if atual["para_quem_id"] is None and (dono := para_quem_certeiro(con, lancamento_id, r["estabelecimento"])) is not None:
        aplicar_certeiro(con, lancamento_id, r["estabelecimento"], dono)
        atual["para_quem_id"], origens["para_quem"], confianca = dono, "gabi", max(confianca, CONFIANCA["cache"])

    # 4) cache por estabelecimento: só sugestão
    if r["estabelecimento"]:
        for campo, col in CAMPOS[:2]:
            if atual[col] is None and _sugerir_por_cache(con, lancamento_id, r["estabelecimento"], campo, col):
                confianca = max(confianca, CONFIANCA["cache"])

    return Classificacao(atual["categoria_id"], atual["para_quem_id"], atual["empresa_id"], origens, confianca)


def classificar_pendentes(con) -> ResumoClassificacao:
    from gabi.dinheiro.favorecidos import sugerir_por_favorecido  # import tardio: favorecidos usa regras, que usa este módulo
    ids = [r[0] for r in con.execute("select id from lancamento where categoria_id is null or para_quem_id is null order by id")]
    antes = con.execute("select count(*) from sugestao").fetchone()[0]
    resolvidos = sum(1 for i in ids if classificar(con, i).origens)
    sugerir_por_favorecido(con)
    return ResumoClassificacao(len(ids), resolvidos, con.execute("select count(*) from sugestao").fetchone()[0] - antes)
