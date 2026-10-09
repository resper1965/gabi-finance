"""Leitura dos cadastros que a Fase 2 usa. A relação da empresa (contratante | pj_titular | outra), o e-mail de cobrança e as permissões de
pedido ficam no JSON `dados` do cadastro (Cadastros já valida e edita), não em colunas próprias. Consome: db (empresa, pessoa)."""
import json

RELACAO_SQL = "json_extract(e.dados, '$.relacao')"  # use com a tabela empresa aliasada `e`


def relacao(con, empresa_id: str) -> str | None:
    r = con.execute("select json_extract(dados, '$.relacao') as r from empresa where id=? and excluido_em is null", (empresa_id,)).fetchone()
    return r["r"] if r else None


def contratantes(con) -> list:
    return con.execute("select e.id, e.nome from empresa e where e.excluido_em is null and " + RELACAO_SQL + "='contratante' order by e.nome").fetchall()


def dados(linha) -> dict:
    return json.loads((linha["dados"] if linha else None) or "{}")
