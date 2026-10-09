import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro.classificar import Classificacao, classificar, classificar_pendentes

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('b1','C6','BANK','sim')")
    for n in ("Mercado", "Transporte", "Restaurante"):
        c.execute("insert into categoria(nome) values (?)", (n,))
    c.execute("insert into pessoa(id, nome) values ('p1','Ana')")
    c.execute("insert into pessoa(id, nome) values ('p2','Bia')")
    c.execute("insert into empresa(id, nome) values ('e1','Ness')")
    return c


def _lanc(con, i, desc="UBER TRIP", estab=None, cat_banco=None, **extra):
    cols = {"conta_id": 1, "externo_id": f"l{i}", "data": "2026-10-08", "valor_centavos": -1000, "descricao_original": desc,
            "estabelecimento": estab if estab is not None else desc.split()[0], "categoria_banco": cat_banco, **extra}
    con.execute(f"insert into lancamento({','.join(cols)}) values ({','.join('?' * len(cols))})", list(cols.values()))
    return con.execute("select id from lancamento where externo_id=?", (f"l{i}",)).fetchone()[0]


def _regra(con, padrao, acao, ativa=1):
    con.execute("insert into regra(padrao, acao, ativa, criado_em, criada_por) values (?,?,?, '2026-10-08', 'voce')",
                (padrao, json.dumps(acao), ativa))


def _l(con, lid):
    return con.execute("select * from lancamento where id=?", (lid,)).fetchone()


def test_regra_ativa_aplica_com_origem_regra(con):
    _regra(con, "UBER", {"categoria_id": 2, "para_quem_id": "p1"})
    lid = _lanc(con, 1)
    c = classificar(con, lid)
    r = _l(con, lid)
    assert (r["categoria_id"], r["categoria_origem"], r["para_quem_id"], r["para_quem_origem"]) == (2, "regra", "p1", "regra")
    assert isinstance(c, Classificacao) and c.categoria_id == 2 and c.origens["categoria"] == "regra" and c.confianca == 1.0


def test_regra_inativa_nao_aplica(con):
    _regra(con, "UBER", {"categoria_id": 2}, ativa=0)  # R1: só vale depois do Ricardo ligar
    lid = _lanc(con, 1)
    classificar(con, lid)
    assert _l(con, lid)["categoria_id"] is None


def test_regra_ganha_da_equivalencia_do_banco(con):
    con.execute("insert into equivalencia_categoria(origem_pluggy, categoria_id) values ('Transport', 3)")
    _regra(con, "UBER", {"categoria_id": 2})
    lid = _lanc(con, 1, cat_banco="Transport")
    classificar(con, lid)
    r = _l(con, lid)
    assert (r["categoria_id"], r["categoria_origem"]) == (2, "regra")


def test_equivalencia_do_banco_aplica_com_origem_banco(con):
    con.execute("insert into equivalencia_categoria(origem_pluggy, categoria_id) values ('Groceries', 1)")
    lid = _lanc(con, 1, "PADARIA", cat_banco="Groceries")
    classificar(con, lid)
    r = _l(con, lid)
    assert (r["categoria_id"], r["categoria_origem"]) == (1, "banco")


def test_decisao_do_ricardo_nunca_e_sobrescrita(con):
    _regra(con, "UBER", {"categoria_id": 2, "para_quem_id": "p1", "empresa_id": "e1"})
    lid = _lanc(con, 1, categoria_id=3, categoria_origem="voce", para_quem_id="p2", para_quem_origem="voce")
    classificar(con, lid)
    r = _l(con, lid)
    assert (r["categoria_id"], r["categoria_origem"], r["para_quem_id"], r["para_quem_origem"]) == (3, "voce", "p2", "voce")
    assert (r["empresa_id"], r["empresa_origem"]) == ("e1", "regra")  # o campo livre é preenchido


def test_regra_so_com_um_campo_deixa_os_outros_em_branco(con):
    _regra(con, "UBER", {"para_quem_id": "p1"})
    lid = _lanc(con, 1)
    classificar(con, lid)
    r = _l(con, lid)
    assert r["para_quem_id"] == "p1" and r["categoria_id"] is None and r["empresa_id"] is None


def test_regra_com_regex_invalido_e_ignorada_sem_quebrar(con):
    _regra(con, "([", {"categoria_id": 1})
    _regra(con, "UBER", {"categoria_id": 2})
    lid = _lanc(con, 1)
    classificar(con, lid)
    assert _l(con, lid)["categoria_id"] == 2


def test_regra_com_acao_invalida_e_ignorada(con):
    con.execute("insert into regra(padrao, acao, ativa, criado_em) values ('UBER','isto nao e json',1,'2026-10-08')")
    _regra(con, "UBER", {"categoria_id": 2})
    lid = _lanc(con, 1)
    classificar(con, lid)
    assert _l(con, lid)["categoria_id"] == 2


def test_primeira_regra_por_id_vence(con):
    _regra(con, "UBER", {"categoria_id": 2})
    _regra(con, "UBER", {"categoria_id": 3})
    lid = _lanc(con, 1)
    classificar(con, lid)
    assert _l(con, lid)["categoria_id"] == 2


def test_cache_por_estabelecimento_so_sugere_nao_grava(con):
    _lanc(con, 1, "PADARIA BOM PAO", estab="PADARIA BOM PAO", categoria_id=1, categoria_origem="voce")
    novo = _lanc(con, 2, "PADARIA BOM PAO LTDA", estab="PADARIA BOM PAO")
    classificar(con, novo)
    assert _l(con, novo)["categoria_id"] is None  # R1: uma decisão sua vale só para aquele lançamento
    s = con.execute("select * from sugestao").fetchall()
    assert len(s) == 1 and s[0]["tipo"] == "categoria" and s[0]["estado"] == "pendente" and s[0]["lancamento_id"] == novo
    assert json.loads(s[0]["payload"])["categoria_id"] == 1


def test_cache_nao_duplica_sugestao_pendente(con):
    _lanc(con, 1, "PADARIA", estab="PADARIA", categoria_id=1, categoria_origem="voce")
    novo = _lanc(con, 2, "PADARIA", estab="PADARIA")
    classificar(con, novo)
    classificar(con, novo)
    assert con.execute("select count(*) from sugestao").fetchone()[0] == 1


def test_cache_com_decisoes_divergentes_nao_sugere(con):
    _lanc(con, 1, "PADARIA", estab="PADARIA", categoria_id=1, categoria_origem="voce")
    _lanc(con, 2, "PADARIA", estab="PADARIA", categoria_id=3, categoria_origem="voce")
    novo = _lanc(con, 3, "PADARIA", estab="PADARIA")
    classificar(con, novo)
    assert con.execute("select count(*) from sugestao").fetchone()[0] == 0


def test_sem_resolucao_nao_grava_nada_nem_quebra(con):
    lid = _lanc(con, 1, "COISA NUNCA VISTA")
    c = classificar(con, lid)
    r = _l(con, lid)
    assert r["categoria_id"] is None and r["para_quem_id"] is None and c.confianca == 0.0 and c.origens == {}
    assert con.execute("select count(*) from sugestao").fetchone()[0] == 0


def test_classificar_pendentes_percorre_so_o_que_falta(con):
    _regra(con, "UBER", {"categoria_id": 2, "para_quem_id": "p1"})
    a = _lanc(con, 1)
    _lanc(con, 2, "X", categoria_id=1, categoria_origem="voce", para_quem_id="p1", para_quem_origem="voce")
    b = _lanc(con, 3, "OUTRA COISA")
    r = classificar_pendentes(con)
    assert r.examinados == 2 and r.resolvidos == 1
    assert _l(con, a)["categoria_id"] == 2 and _l(con, b)["categoria_id"] is None


def test_lancamento_inexistente_levanta_LookupError(con):
    with pytest.raises(LookupError):
        classificar(con, 9999)


def test_regra_tambem_casa_pelo_estabelecimento_normalizado(con):
    _regra(con, "^LOJA X$", {"categoria_id": 2})
    lid = _lanc(con, 1, desc="LOJA (X) *123", estab="LOJA X")  # a descrição original tem pontuação; o estabelecimento é normalizado
    classificar(con, lid)
    assert _l(con, lid)["categoria_id"] == 2


# ---------------- donos padrão ("para quem" sem perguntar): responsável > compromisso > conta > categoria ----------------
def _pessoas_da_familia(con):
    con.execute("insert into pessoa(id, nome, papel, dados) values ('casa','Casa (todos)','coletivo','{}')")
    con.execute("insert into pessoa(id, nome, papel, dados) values ('giovanna','Giovanna Della Torre Esper','filha','{}')")
    con.execute("insert into pessoa(id, nome, papel, dados) values ('sabrina','Sabrina Barbosa de Barros','esposa','{}')")
    con.execute("insert into pessoa(id, nome, papel, dados) values ('carla','Carla Noce Della Torre','ex-esposa', ?)",
                (json.dumps({"responsavel_por": ["giovanna"], "beneficiario": False}),))


def test_pagamento_a_quem_responde_por_uma_filha_vai_para_a_filha(con):
    _pessoas_da_familia(con)
    lid = _lanc(con, 1, desc="Pix enviado para CARLA NOCE DELA TORRE", estab="Pix enviado para CARLA NOCE DELA TORRE")
    c = classificar(con, lid)
    assert c.para_quem_id == "giovanna" and c.origens["para_quem"] == "regra"
    assert _l(con, lid)["para_quem_origem"] == "regra"


def test_dinheiro_que_ENTRA_da_responsavel_nao_vira_para_quem(con):
    _pessoas_da_familia(con)
    lid = _lanc(con, 1, desc="Pix recebido CARLA NOCE DELA TORRE", estab="CARLA NOCE", valor_centavos=5000)
    assert classificar(con, lid).para_quem_id is None


def test_responsavel_de_duas_filhas_nao_adivinha(con):
    _pessoas_da_familia(con)
    con.execute("update pessoa set dados=? where id='carla'", (json.dumps({"responsavel_por": ["giovanna", "sabrina"]}),))
    assert classificar(con, _lanc(con, 1, desc="Pix enviado CARLA NOCE DELA TORRE")).para_quem_id is None


def test_cartao_de_um_unico_usuario_define_o_para_quem(con):
    _pessoas_da_familia(con)
    con.execute("update conta set usuarios=? where id=1", (json.dumps(["sabrina"]),))
    lid = _lanc(con, 1)
    assert classificar(con, lid).para_quem_id == "sabrina"


def test_cartao_com_dois_usuarios_nao_decide_sozinho(con):
    _pessoas_da_familia(con)
    con.execute("update conta set usuarios=? where id=1", (json.dumps(["sabrina", "giovanna"]),))
    assert classificar(con, _lanc(con, 1)).para_quem_id is None


def test_categoria_com_dono_padrao_preenche_o_para_quem(con):
    _pessoas_da_familia(con)
    con.execute("update categoria set dono_padrao='casa' where nome='Mercado'")
    con.execute("insert into equivalencia_categoria(origem_pluggy, categoria_id) values ('Groceries', 1)")
    lid = _lanc(con, 1, cat_banco="Groceries")
    c = classificar(con, lid)
    assert (c.categoria_id, c.para_quem_id) == (1, "casa")


def test_pagamento_conciliado_com_compromisso_herda_o_padrao_dele(con):
    _pessoas_da_familia(con)
    con.execute("insert into compromisso_linha(id, nome, extrato, vencimento, valor_tipo, forma) values ('escola','Escola','ESCOLA X','dia:5','fixo','pix')")
    con.execute("insert into compromisso(id, linha_id, nome, vencimento, valor_centavos, estado) values ('escola:2026-10','escola','Escola','2026-10-05',1000,'pago')")
    con.execute("insert into compromisso_padrao(linha_id, para_quem_id, categoria_id) values ('escola','giovanna', 2)")
    lid = _lanc(con, 1, desc="PGTO QUALQUER COISA")
    con.execute("insert into conciliacao(tx_id, compromisso_id, metodo, diferenca_centavos, criado_em) values ('l1','escola:2026-10','valor',0,'x')")
    c = classificar(con, lid)
    assert (c.para_quem_id, c.categoria_id) == ("giovanna", 2)


def test_precedencia_regra_do_ricardo_vence_os_padroes(con):
    _pessoas_da_familia(con)
    con.execute("update conta set usuarios=? where id=1", (json.dumps(["sabrina"]),))
    _regra(con, "UBER", {"para_quem_id": "giovanna"})
    assert classificar(con, _lanc(con, 1)).para_quem_id == "giovanna"


def test_nunca_sobrescreve_o_que_o_ricardo_ja_decidiu(con):
    _pessoas_da_familia(con)
    con.execute("update conta set usuarios=? where id=1", (json.dumps(["sabrina"]),))
    lid = _lanc(con, 1, para_quem_id="giovanna", para_quem_origem="voce")
    classificar(con, lid)
    assert _l(con, lid)["para_quem_id"] == "giovanna" and _l(con, lid)["para_quem_origem"] == "voce"
