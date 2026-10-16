"""Pergunta de dono (D5): fornecedor com gasto sem "para quem" vira pergunta no canal de decisão, um fornecedor por vez, até
`MAX_ABERTAS` abertas. R1: só pergunta; o Ricardo escolhe a pessoa (ou deixa para depois). Resposta preenche SÓ os lançamentos
ainda sem dono, com origem 'voce'. As opções são as pessoas mais usadas nos lançamentos já classificados (nada chumbado).
Consome: lancamento, conta, pessoa, decisoes."""
import json

from gabi import decisoes
from gabi.dinheiro.agenda_financeira import _brl

TIPO = "dono_fornecedor"
MAX_ABERTAS = 5
MAX_PESSOAS = 7      # + "deixar para depois" = 8 opções (o canal aceita até 9)
MIN_LANCAMENTOS = 2  # fornecedor de uma compra só não vale uma pergunta


def _pessoas(con) -> list[tuple[str, str]]:
    return [(r["id"], r["nome"]) for r in con.execute(
        "select p.id, p.nome from pessoa p join lancamento l on l.para_quem_id=p.id group by p.id order by count(*) desc, p.nome limit ?", (MAX_PESSOAS,))]


def candidatos(con, limite: int) -> list[dict]:
    """Fornecedores com mais lançamentos de custo sem dono em contas liberadas, do maior gasto para o menor."""
    return [dict(r) for r in con.execute(
        "select coalesce(l.estabelecimento, l.descricao_original) as fornecedor, count(*) as n, sum(-l.valor_centavos) as total "
        "from lancamento l join conta c on c.id=l.conta_id where c.estado='sim' and c.excluido_em is null and l.natureza like '%custo%' "
        "and l.valor_centavos<0 and l.para_quem_id is null and coalesce(l.estabelecimento, l.descricao_original) is not null "
        "group by 1 having n>=? order by total desc limit ?", (MIN_LANCAMENTOS, limite))]


def propor(con, agora_iso: str) -> int:
    abertas = con.execute("select count(*) from pergunta where tipo=? and estado='aberta'", (TIPO,)).fetchone()[0]
    vagas = MAX_ABERTAS - abertas
    pessoas = _pessoas(con)
    if vagas <= 0 or not pessoas:
        return 0
    criadas = 0
    for c in candidatos(con, 50):
        if criadas >= vagas:
            break
        titulo = f"De quem é o gasto em '{c['fornecedor']}'?"
        if con.execute("select 1 from pergunta where tipo=? and titulo=?", (TIPO, titulo)).fetchone():
            continue  # já perguntada (aberta, respondida ou expirada): não insiste
        opcoes = [{"n": i, "rotulo": nome, "efeito": "atribuir_para_quem", "parametros": {"estabelecimento": c["fornecedor"], "pessoa_id": pid}}
                  for i, (pid, nome) in enumerate(pessoas, 1)]
        opcoes.append({"n": len(opcoes) + 1, "rotulo": "Deixar para depois", "efeito": "registrar_nota"})
        decisoes.criar_pergunta(con, TIPO, titulo, f"{c['n']} lançamentos, {_brl(c['total'])} no total, sem dono.", opcoes, "claude", agora_iso)
        criadas += 1
    return criadas
