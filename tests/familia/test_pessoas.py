"""Pessoa e pet ditados ao Hermes, com histórico e desfazer.
Consome: gabi.familia.pessoas, gabi.familia.contato, migrações."""
import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.familia import contato, pessoas
from gabi.familia.fichas import ErroFamilia

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
AGORA = dt.datetime(2026, 10, 25, 12, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into pessoa(id, nome, dados) values ('ricardo','Ricardo',?)",
              (json.dumps({"nome_completo": "Ricardo Esper"}),))
    return c


def _dados(con, pid):
    return json.loads(con.execute("select dados from pessoa where id=?", (pid,)).fetchone()["dados"])


def _conta(con, tabela):
    return con.execute(f"select count(*) n from {tabela}").fetchone()["n"]


def _erro(fn, *a, **k):
    with pytest.raises(ErroFamilia) as e:
        fn(*a, **k)
    return e.value


def _pessoa(con, **k):
    return pessoas.registrar_pessoa(con, quem="boss", agora=AGORA, **k)


def _pet(con, **k):
    return pessoas.registrar_pet(con, quem="boss", agora=AGORA, **k)


def test_cria_pessoa_nova_com_parentesco(con):
    r = _pessoa(con, nome="Chafic Esper", parentesco="irmão")
    assert r["criada"] is True and r["pessoa_id"] == "chafic"
    d = _dados(con, "chafic")
    assert d["parentesco"] == "irmão" and d["nome_completo"] == "Chafic Esper"
    row = con.execute("select nome, papel, origem from pessoa where id='chafic'").fetchone()
    assert tuple(row) == ("Chafic", "familia", "hermes")
    h = contato.historico(con, "chafic")
    assert [x["campo"] for x in reversed(h)] == ["criada", "parentesco"]
    assert [m["campo"] for m in r["mudancas"]] == ["parentesco"] and r["mudancas"][0]["depois"] == "irmão"


def test_atualiza_existente_sem_duplicar(con):
    con.execute("insert into pessoa(id, nome, dados) values ('carla','Carla',?)",
                (json.dumps({"nome_completo": "Carla Noce Della Torre"}),))
    n = _conta(con, "pessoa")
    r = _pessoa(con, nome="Carla Noce Della Torre", parentesco="ex-esposa, mãe da Gigi")
    assert r["criada"] is False and r["pessoa_id"] == "carla" and _conta(con, "pessoa") == n
    assert _dados(con, "carla")["parentesco"] == "ex-esposa, mãe da Gigi"
    r2 = _pessoa(con, nome="Carla", parentesco="ex-esposa, mãe da Gigi")
    assert r2["mudancas"] == [] and len(contato.historico(con, "carla")) == 1


def test_resolve_pelo_apelido(con):
    con.execute("insert into pessoa(id, nome, dados) values ('gigi','Giovanna',?)", (json.dumps({"apelido": "Gigi"}),))
    r = _pessoa(con, nome="Giovanna Della Torre Esper", apelido="Gigi", parentesco="filha")
    assert r["criada"] is False and r["pessoa_id"] == "gigi"


def test_ambiguo_nao_grava(con):
    con.execute("insert into pessoa(id, nome) values ('ana1','Ana Souza')")
    con.execute("insert into pessoa(id, nome) values ('ana2','Ana Lima')")
    n, nh = _conta(con, "pessoa"), _conta(con, "pessoa_historico")
    e = _erro(_pessoa, con, nome="Ana", parentesco="prima")
    assert e.codigo == "pessoa_ambigua" and len(e.candidatos) == 2
    assert _conta(con, "pessoa_historico") == nh and _conta(con, "pessoa") == n


def test_id_colide_usa_nome_completo(con):
    con.execute("insert into pessoa(id, nome) values ('sandra','Sandra')")
    assert _pessoa(con, nome="Sandra Maria Esper", parentesco="tia")["pessoa_id"] == "sandra-maria-esper"


def test_id_colide_duas_vezes_usa_sufixo(con):
    con.execute("insert into pessoa(id, nome, excluido_em) values ('joao','X','2026-01-01T00:00:00Z')")
    con.execute("insert into pessoa(id, nome, excluido_em) values ('joao-da-silva','Y','2026-01-01T00:00:00Z')")
    assert _pessoa(con, nome="João da Silva", parentesco="amigo")["pessoa_id"] == "joao-da-silva-2"


def test_falecido_e_observacao(con):
    r = _pessoa(con, nome="Salim Esper", parentesco="pai", falecido=True, observacao="faleceu em 2010")
    d = _dados(con, r["pessoa_id"])
    assert d["falecido"] is True and d["observacao"] == "faleceu em 2010"
    r2 = _pessoa(con, nome="Chafic Esper", parentesco="irmão")
    assert "falecido" not in _dados(con, r2["pessoa_id"])


def test_desfazer_criada_exclui(con):
    r = _pessoa(con, nome="Chafic Esper", parentesco="")
    criada = contato.historico(con, "chafic")[0]
    assert criada["campo"] == "criada" and r["mudancas"] == []
    contato.desfazer(con, criada["id"], "boss", AGORA)
    assert con.execute("select excluido_em from pessoa where id=?", (r["pessoa_id"],)).fetchone()["excluido_em"]
    volta = contato.historico(con, "chafic")[0]
    assert volta["campo"] == "criada" and volta["depois"] is None
    assert _erro(contato.desfazer, con, criada["id"], "boss", AGORA).codigo == "conflito"
    contato.desfazer(con, volta["id"], "boss", AGORA)  # desfazer o desfazer traz a pessoa de volta
    assert con.execute("select excluido_em from pessoa where id='chafic'").fetchone()["excluido_em"] is None


def test_desfazer_criada_com_mudanca_posterior_conflito(con):
    _pessoa(con, nome="Chafic Esper", parentesco="irmão")
    criada = [h for h in contato.historico(con, "chafic") if h["campo"] == "criada"][0]
    assert _erro(contato.desfazer, con, criada["id"], "boss", AGORA).codigo == "conflito"
    assert con.execute("select excluido_em from pessoa where id='chafic'").fetchone()["excluido_em"] is None


def test_pet_cria_e_atualiza(con):
    r = _pet(con, nome="Cookie", especie="cachorro", raca="shih-tzu", nascimento="2017-07-19", dono="Ricardo")
    assert r["criado"] is True and r["pet_id"] == "cookie"
    pets = pessoas.listar_pets(con)
    assert pets == [{"id": "cookie", "nome": "Cookie", "especie": "cachorro", "raca": "shih-tzu", "nascimento": "2017-07-19",
                     "dono": "ricardo"}]
    r2 = _pet(con, nome="Cookie", especie="cachorro", raca="lhasa")
    assert r2["criado"] is False and r2["pet_id"] == "cookie"
    assert _conta(con, "pet") == 1 and pessoas.listar_pets(con)[0]["raca"] == "lhasa"
    assert pessoas.listar_pets(con)[0]["dono"] == "ricardo"
    h = contato.historico(con, "pets")
    assert [x["campo"] for x in h] == ["pet:cookie", "pet:cookie"] and h[1]["antes"] is None


def test_pet_dono_ambiguo(con):
    con.execute("insert into pessoa(id, nome) values ('ana1','Ana Souza')")
    con.execute("insert into pessoa(id, nome) values ('ana2','Ana Lima')")
    assert _erro(_pet, con, nome="Rex", especie="cachorro", dono="Ana").codigo == "pessoa_ambigua"
    assert _conta(con, "pet") == 0 and _conta(con, "pessoa_historico") == 0


def test_desfazer_pet_novo_apaga(con):
    r = _pet(con, nome="Cookie", especie="cachorro")
    contato.desfazer(con, r["historico_id"], "boss", AGORA)
    assert _conta(con, "pet") == 0


def test_desfazer_pet_atualizado_restaura_e_conflito(con):
    _pet(con, nome="Cookie", especie="cachorro", raca="shih-tzu")
    r1 = _pet(con, nome="Cookie", especie="cachorro", raca="lhasa")
    r2 = _pet(con, nome="Cookie", especie="cachorro", raca="poodle")
    assert _erro(contato.desfazer, con, r1["historico_id"], "boss", AGORA).codigo == "conflito"
    contato.desfazer(con, r2["historico_id"], "boss", AGORA)
    assert pessoas.listar_pets(con)[0]["raca"] == "lhasa"


def test_nascimento_invalido(con):
    n, nh, nd = _conta(con, "pessoa"), _conta(con, "pessoa_historico"), _conta(con, "decisao")
    assert _erro(_pessoa, con, nome="Chafic Esper", parentesco="irmão", nascimento="19/07/1970").codigo == "valor_invalido"
    assert _erro(_pet, con, nome="Cookie", especie="cachorro", nascimento="2017-13-40").codigo == "valor_invalido"
    assert (_conta(con, "pessoa"), _conta(con, "pessoa_historico"), _conta(con, "decisao")) == (n, nh, nd)
    assert _conta(con, "pet") == 0


def test_parentesco_longo_invalido(con):
    assert _erro(_pessoa, con, nome="Chafic Esper", parentesco="x" * (contato.MAX_TEXTO + 1)).codigo == "valor_invalido"
    assert _conta(con, "pessoa") == 1


def test_auditoria_sem_nome(con):
    _pessoa(con, nome="Chafic Esper", parentesco="irmão", apelido="Chafa")
    _pet(con, nome="Cookie", especie="cachorro", dono="Chafic")
    textos = [r["o_que"] for r in con.execute("select o_que, origem from decisao")]
    assert textos and all("Chafic" not in t and "Esper" not in t and "Chafa" not in t for t in textos)
    assert {r["origem"] for r in con.execute("select origem from decisao")} == {"familia"}
