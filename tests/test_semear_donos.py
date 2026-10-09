import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from tools.semear_donos import aplicar

MIGR = Path(__file__).parent.parent / "migrations"
DADOS = {
    "coletivos": [{"id": "casa", "nome": "Casa (todos)"}],
    "responsaveis": {"carla": ["giovanna"]},
    "categorias": {"Mercado": "casa"},
    "contas": {"CARTAO X": ["sabrina"]},
    "compromissos": {"carla-pensao": {"para_quem": "giovanna"}},
}


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    for pid, nome, dados in (("giovanna", "Giovanna", "{}"), ("sabrina", "Sabrina", "{}"), ("carla", "Carla", '{"obs": "x"}')):
        c.execute("insert into pessoa(id, nome, dados) values (?,?,?)", (pid, nome, dados))
    c.execute("insert into categoria(nome) values ('Mercado')")
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('c1','Itau','CREDIT','  cartao x  ','sim')")
    c.execute("insert into compromisso_linha(id, nome, extrato, vencimento, valor_tipo, forma) values ('carla-pensao','Pensão','X','dia:5','fixo','pix')")
    return c


@pytest.fixture
def arq(tmp_path):
    p = tmp_path / "d.json"
    p.write_text(json.dumps(DADOS), encoding="utf-8")
    return p


def test_aplica_tudo_e_preserva_os_outros_dados(con, arq):
    r = aplicar(con, arq, "teste")
    assert r.conflitos == [] and r.nao_encontrados == []
    assert con.execute("select nome, papel from pessoa where id='casa'").fetchone()[:] == ("Casa (todos)", "coletivo")
    d = json.loads(con.execute("select dados from pessoa where id='carla'").fetchone()[0])
    assert d == {"obs": "x", "responsavel_por": ["giovanna"], "beneficiario": False}
    assert con.execute("select dono_padrao from categoria where nome='Mercado'").fetchone()[0] == "casa"
    assert json.loads(con.execute("select usuarios from conta where id=1").fetchone()[0]) == ["sabrina"]   # casou pelo apelido sem espaços/caixa
    assert tuple(con.execute("select para_quem_id from compromisso_padrao where linha_id='carla-pensao'").fetchone()) == ("giovanna",)


def test_e_idempotente_e_audita(con, arq):
    aplicar(con, arq, "teste")
    antes = con.execute("select count(*) from decisao").fetchone()[0]
    aplicar(con, arq, "teste")
    assert con.execute("select count(*) from decisao").fetchone()[0] == antes and antes > 0


def test_nao_sobrescreve_o_que_o_ricardo_ja_escolheu(con, arq):
    con.execute("update conta set usuarios=? where id=1", (json.dumps(["giovanna"]),))
    con.execute("update categoria set dono_padrao='sabrina' where nome='Mercado'")
    r = aplicar(con, arq, "teste")
    assert sorted(r.conflitos) == ["categoria Mercado", "conta CARTAO X"]
    assert json.loads(con.execute("select usuarios from conta where id=1").fetchone()[0]) == ["giovanna"]
    assert con.execute("select dono_padrao from categoria where nome='Mercado'").fetchone()[0] == "sabrina"


def test_item_inexistente_e_reportado_sem_derrubar(con, tmp_path):
    p = tmp_path / "d.json"
    p.write_text(json.dumps({"coletivos": [{"id": "casa", "nome": "Casa"}], "contas": {"NAO EXISTE": ["sabrina"]}, "categorias": {"Fantasma": "casa"}, "compromissos": {"x": {"para_quem": "sabrina"}}, "responsaveis": {"ninguem": ["sabrina"]}}), encoding="utf-8")
    r = aplicar(con, p, "teste")
    assert sorted(r.nao_encontrados) == ["categoria Fantasma", "compromisso x", "conta NAO EXISTE", "pessoa ninguem"]


def test_pessoa_inexistente_como_dono_nao_grava_nada(con, tmp_path):
    p = tmp_path / "d.json"
    p.write_text(json.dumps({"contas": {"CARTAO X": ["fantasma"]}}), encoding="utf-8")
    with pytest.raises(ValueError):
        aplicar(con, p, "teste")
    assert con.execute("select usuarios from conta where id=1").fetchone()[0] is None


def test_o_arquivo_de_seeds_do_projeto_e_json_valido():
    d = json.loads((Path(__file__).parent.parent / "seeds" / "donos-padrao.json").read_text(encoding="utf-8"))
    assert {"coletivos", "responsaveis", "categorias", "contas", "compromissos"} <= set(d)


def test_grava_parametros_sem_sobrescrever_o_existente(con, tmp_path):
    p = tmp_path / "d.json"
    p.write_text(json.dumps({"parametros": {"categorias_assinatura": ["Assinaturas"], "outro": 1}}), encoding="utf-8")
    r = aplicar(con, p, "teste")
    assert r.aplicados == 2 and json.loads(con.execute("select valor from parametro where chave='categorias_assinatura'").fetchone()[0]) == ["Assinaturas"]
    assert aplicar(con, p, "teste").aplicados == 0                      # idempotente
    con.execute("update parametro set valor=? where chave='outro'", ("2",))
    assert aplicar(con, p, "teste").conflitos == ["parametro outro"]    # o que o Ricardo mudou fica
    assert con.execute("select valor from parametro where chave='outro'").fetchone()[0] == "2"


def test_regras_do_arquivo_na_ordem_com_nomes_resolvidos(con, tmp_path):
    con.execute("insert into categoria(nome) values ('Assinaturas')")
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, estabelecimento, categoria_id, categoria_origem, status) "
                "values (1,'a','2026-09-10',-13990,'MP *MELIMAIS','MP',1,'banco','posted')")
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, estabelecimento, status) values (1,'b','2026-09-10',-5000,'MERCADOLIVRE PROD','MERCADOLIVRE','posted')")
    p = tmp_path / "d.json"
    p.write_text(json.dumps({"coletivos": [{"id": "casa", "nome": "Casa"}], "regras": [
        {"padrao": "MELIMAIS", "acao": {"para_quem": "sabrina", "categoria": "Assinaturas"}},
        {"padrao": "MERCADOLIVRE", "acao": {"para_quem": "casa"}}]}), encoding="utf-8")
    r = aplicar(con, p, "teste")
    assert r.aplicados == 3 and r.nao_encontrados == []
    assert [x[0] for x in con.execute("select padrao from regra order by id")] == ["MELIMAIS", "MERCADOLIVRE"]   # a exceção vem antes
    a, b = (con.execute("select para_quem_id, categoria_id from lancamento where externo_id=?", (k,)).fetchone() for k in ("a", "b"))
    assert (a[0], a[1]) == ("sabrina", 2) and b[0] == "casa"
    assert aplicar(con, p, "teste").aplicados == 0                                                                      # idempotente


def test_regra_com_nome_inexistente_e_reportada_sem_gravar(con, tmp_path):
    p = tmp_path / "d.json"
    p.write_text(json.dumps({"regras": [{"padrao": "X", "acao": {"para_quem": "fantasma"}}, {"padrao": "Y", "acao": {"categoria": "Nao existe"}}]}), encoding="utf-8")
    r = aplicar(con, p, "teste")
    assert sorted(r.nao_encontrados) == ["regra X", "regra Y"] and con.execute("select count(*) from regra").fetchone()[0] == 0
