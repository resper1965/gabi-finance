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
    con.execute("insert into pessoa(id, nome, dados) values ('sandra','Sandra',?)", (json.dumps({"nome_completo": "Sandra Lima"}),))
    assert _pessoa(con, nome="Sandra Maria Esper", parentesco="tia")["pessoa_id"] == "sandra-maria-esper"


def test_so_primeiro_nome_sem_completo_e_a_mesma(con):
    con.execute("insert into pessoa(id, nome) values ('chafic','Chafic')")
    n = _conta(con, "pessoa")
    r = _pessoa(con, nome="Chafic Esper", parentesco="irmão")
    assert r["criada"] is False and r["pessoa_id"] == "chafic" and _conta(con, "pessoa") == n
    assert _dados(con, "chafic")["nome_completo"] == "Chafic Esper"
    m = [x for x in r["mudancas"] if x["campo"] == "nome_completo"][0]
    contato.desfazer(con, m["historico_id"], "boss", AGORA)
    assert "nome_completo" not in _dados(con, "chafic")
    assert _pet(con, nome="Rex", especie="cachorro", dono="Chafic Esper")["pet_id"] == "rex"
    assert pessoas.listar_pets(con)[0]["dono"] == "chafic"


def test_nome_completo_nao_encurta(con):
    con.execute("insert into pessoa(id, nome) values ('ana1','Ana Souza')")
    r = _pessoa(con, nome="Ana", parentesco="prima")
    assert r["pessoa_id"] == "ana1" and "nome_completo" not in _dados(con, "ana1")
    assert [h["campo"] for h in contato.historico(con, "ana1")] == ["parentesco"]


def test_apelido_com_nome_alheio_nao_grava_completo(con):
    con.execute("insert into pessoa(id, nome, dados) values ('gigi','Giovanna',?)", (json.dumps({"apelido": "Gigi"}),))
    e = _erro(_pessoa, con, nome="Fulana Beltrana", apelido="Gigi", parentesco="filha")  # I2: pergunta em vez de juntar
    assert e.codigo == "pessoa_ambigua" and e.candidatos == ["Giovanna"]
    assert "nome_completo" not in _dados(con, "gigi") and contato.historico(con, "gigi") == []


def test_so_primeiro_nome_dois_casam_ambiguo(con):
    con.execute("insert into pessoa(id, nome) values ('chafic','Chafic')")
    con.execute("insert into pessoa(id, nome) values ('chafic2','Chafic')")
    e = _erro(_pessoa, con, nome="Chafic Esper", parentesco="irmão")
    assert e.codigo == "pessoa_ambigua" and e.candidatos == ["Chafic", "Chafic"]


def test_slug(con):
    assert pessoas._slug("Dr. João") == "dr-joao" and pessoas._slug("  Ana--Maria  d'Ávila ") == "ana-maria-d-avila"
    assert _erro(pessoas._slug, "!!!").codigo == "valor_invalido"
    assert _pet(con, nome="Dr. João", especie="gato")["pet_id"] == "dr-joao"
    assert _erro(_pet, con, nome="???", especie="gato").codigo == "valor_invalido"


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
    r = _pessoa(con, nome="Chafic Esper", parentesco="irmão", apelido="Chafa")
    criada = [h for h in contato.historico(con, "chafic") if h["campo"] == "criada"][0]
    contato.desfazer(con, criada["id"], "boss", AGORA)
    assert con.execute("select excluido_em from pessoa where id=?", (r["pessoa_id"],)).fetchone()["excluido_em"]
    hs = contato.historico(con, "chafic")
    assert hs[0]["campo"] == "criada" and hs[0]["depois"] is None
    assert all(h["desfeito_em"] for h in hs[1:])  # criada, parentesco e apelido da mesma chamada
    assert _erro(contato.desfazer, con, criada["id"], "boss", AGORA).codigo == "conflito"
    contato.desfazer(con, hs[0]["id"], "boss", AGORA)  # desfazer o desfazer traz a pessoa de volta
    assert con.execute("select excluido_em from pessoa where id='chafic'").fetchone()["excluido_em"] is None


def test_desfazer_criada_com_mudanca_posterior_conflito(con):
    _pessoa(con, nome="Chafic Esper", parentesco="irmão")
    pessoas.registrar_pessoa(con, nome="Chafic Esper", parentesco="irmão mais velho", quem="boss",
                             agora=AGORA + dt.timedelta(minutes=5))
    criada = [h for h in contato.historico(con, "chafic") if h["campo"] == "criada"][0]
    assert _erro(contato.desfazer, con, criada["id"], "boss", AGORA).codigo == "conflito"
    assert con.execute("select excluido_em from pessoa where id='chafic'").fetchone()["excluido_em"] is None
    assert not any(h["desfeito_em"] for h in contato.historico(con, "chafic"))


def test_substring_nao_bloqueia_criacao(con):
    con.execute("insert into pessoa(id, nome, dados) values ('ricardo2','Ricardo C',?)",
                (json.dumps({"nome_completo": "Ricardo Chafic Esper"}),))
    r = _pessoa(con, nome="Chafic Esper", parentesco="irmão")
    assert r["criada"] is True and r["pessoa_id"] == "chafic"
    assert _pet(con, nome="Rex", especie="cachorro", dono="Chafic Esper")["pet_id"] == "rex"
    assert pessoas.listar_pets(con)[0]["dono"] == "chafic"


def test_ambiguo_por_comeco_de_palavra(con):
    con.execute("insert into pessoa(id, nome) values ('lu1','Louise Lavrik')")
    con.execute("insert into pessoa(id, nome) values ('lu2','Louise Esper')")
    e = _erro(_pessoa, con, nome="Louise", parentesco="filha")
    assert e.codigo == "pessoa_ambigua" and sorted(e.candidatos) == ["Louise Esper", "Louise Lavrik"]


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


# --- Forma de produção: nome completo em `nome`, sem `nome_completo`; titular com papel='titular'. ---

@pytest.fixture
def prod(tmp_path):
    c = conectar(tmp_path / "p.db")
    migrar(c, MIGRACOES)
    for pid, nome, papel, dados in (
            ("ricardo", "Ricardo Chafic Esper", "titular", {}),
            ("louise", "Louise Lavrik Esper", "familia", {}),
            ("giovanna", "Giovanna Della Torre Esper", "familia", {"apelido": "Gigi"}),
            ("carla", "Carla Noce Della Torre", "familia", {})):
        c.execute("insert into pessoa(id, nome, papel, dados) values (?,?,?,?)", (pid, nome, papel, json.dumps(dados)))
    return c


def test_nome_encurtado_e_a_mesma_pessoa(prod):
    n = _conta(prod, "pessoa")
    r = _pessoa(prod, nome="Louise Esper", parentesco="filha")
    assert r["criada"] is False and r["pessoa_id"] == "louise" and _conta(prod, "pessoa") == n
    assert _pessoa(prod, nome="Louise", parentesco="filha")["pessoa_id"] == "louise"  # sem sequestro do nome curto
    assert _pessoa(prod, nome="Carla Torre", parentesco="ex-esposa")["pessoa_id"] == "carla"


def test_apelido_como_primeira_palavra(prod):
    r = _pessoa(prod, nome="Gigi Esper", parentesco="filha")
    assert r["criada"] is False and r["pessoa_id"] == "giovanna"


def test_primeira_palavra_diferente_cria(prod):
    r = _pessoa(prod, nome="Chafic Esper", parentesco="irmão")
    assert r["criada"] is True and r["pessoa_id"] == "chafic"
    assert _dados(prod, "ricardo") == {}


def test_encurtado_ambiguo(prod):
    prod.execute("insert into pessoa(id, nome, papel, dados) values ('louise2','Louise Maria Esper','familia','{}')")
    e = _erro(_pessoa, prod, nome="Louise Esper", parentesco="filha")
    assert e.codigo == "pessoa_ambigua" and sorted(e.candidatos) == ["Louise Lavrik Esper", "Louise Maria Esper"]


def test_titular_nunca_e_escrito(prod):
    nh, nd = _conta(prod, "pessoa_historico"), _conta(prod, "decisao")
    for nome in ("Ricardo", "Ricardo Esper", "Ricardo Chafic Esper"):
        e = _erro(_pessoa, prod, nome=nome, parentesco="eu")
        assert e.codigo == "pessoa_ambigua" and e.candidatos == ["Ricardo Chafic Esper"]
    e = _erro(_pessoa, prod, nome="Fulano Novo", apelido="Ricardo", parentesco="eu")  # pelo apelido também
    assert e.codigo == "pessoa_ambigua"
    assert _dados(prod, "ricardo") == {} and (_conta(prod, "pessoa_historico"), _conta(prod, "decisao")) == (nh, nd)


def test_resultado_traz_nome_e_nome_completo(prod):
    r = _pessoa(prod, nome="Louise Esper", parentesco="filha")
    assert r["nome"] == "Louise Lavrik Esper" and r["nome_completo"] is None
    r2 = _pessoa(prod, nome="Chafic Esper", parentesco="irmão")
    assert r2["nome"] == "Chafic" and r2["nome_completo"] == "Chafic Esper"


def test_apelido_casa_mas_nome_contradiz_pergunta(prod):
    n, nh = _conta(prod, "pessoa"), _conta(prod, "pessoa_historico")
    e = _erro(_pessoa, prod, nome="Fulana Beltrana", apelido="Gigi", parentesco="filha")
    assert e.codigo == "pessoa_ambigua" and e.candidatos == ["Giovanna Della Torre Esper"]
    assert (_conta(prod, "pessoa"), _conta(prod, "pessoa_historico")) == (n, nh)


def test_desfazer_criada_depois_de_desfazer_campo(con):
    _pessoa(con, nome="Chafic Esper", parentesco="irmão")
    p = pessoas.registrar_pessoa(con, nome="Chafic Esper", parentesco="primo", quem="boss", agora=AGORA + dt.timedelta(minutes=5))
    contato.desfazer(con, p["mudancas"][0]["historico_id"], "boss", AGORA + dt.timedelta(minutes=6))
    criada = [h for h in contato.historico(con, "chafic") if h["campo"] == "criada"][0]
    contato.desfazer(con, criada["id"], "boss", AGORA + dt.timedelta(minutes=7))
    assert con.execute("select excluido_em from pessoa where id='chafic'").fetchone()["excluido_em"]


def test_desfazer_criada_depois_de_desfazer_o_proprio_campo(con):
    r = _pessoa(con, nome="Chafic Esper", parentesco="irmão")
    contato.desfazer(con, r["mudancas"][0]["historico_id"], "boss", AGORA + dt.timedelta(minutes=1))
    criada = [h for h in contato.historico(con, "chafic") if h["campo"] == "criada"][0]
    contato.desfazer(con, criada["id"], "boss", AGORA + dt.timedelta(minutes=2))  # campo vazio de novo: nada se perde
    assert con.execute("select excluido_em from pessoa where id='chafic'").fetchone()["excluido_em"]


def test_desfazer_criada_com_campo_novo_desfeito(con):
    _pessoa(con, nome="Chafic Esper", parentesco="irmão")
    h = contato.atualizar(con, "chafic", "telefones", "adicionar", "+55 11 98888-7777", "boss", AGORA + dt.timedelta(minutes=1))
    criada = [x for x in contato.historico(con, "chafic") if x["campo"] == "criada"][0]
    assert _erro(contato.desfazer, con, criada["id"], "boss", AGORA).codigo == "conflito"
    contato.desfazer(con, h["historico_id"], "boss", AGORA + dt.timedelta(minutes=2))
    contato.desfazer(con, criada["id"], "boss", AGORA + dt.timedelta(minutes=3))
    assert con.execute("select excluido_em from pessoa where id='chafic'").fetchone()["excluido_em"]


def test_candidatos_com_nome_completo(con):
    _pessoa(con, nome="Sandra Maria Esper", parentesco="tia")
    _pessoa(con, nome="Sandra Lima", parentesco="prima")
    e = _erro(_pessoa, con, nome="Sandra", parentesco="tia")
    assert e.codigo == "pessoa_ambigua"
    assert sorted(e.candidatos) == ["Sandra (Sandra Lima)", "Sandra (Sandra Maria Esper)"]


def test_pet_legado_le_chaves_antigas_e_grava_as_novas(prod):
    prod.execute("insert into pet(id, nome, especie, dados) values ('cookie','Cookie','cachorro',?)",
                 (json.dumps({"tutor": "louise", "aniversario": "2017-07-19", "plano": "petlove"}),))
    assert pessoas.listar_pets(prod)[0] == {"id": "cookie", "nome": "Cookie", "especie": "cachorro", "raca": None,
                                            "nascimento": "2017-07-19", "dono": "louise"}
    r = _pet(prod, nome="Cookie", especie="cachorro", raca="shih-tzu", dono="Gigi", nascimento="2017-07-20")
    assert r["criado"] is False
    d = json.loads(prod.execute("select dados from pet where id='cookie'").fetchone()["dados"])
    assert d["dono"] == "giovanna" and d["nascimento"] == "2017-07-20" and d["raca"] == "shih-tzu"
    assert d["tutor"] == "louise" and d["aniversario"] == "2017-07-19" and d["plano"] == "petlove"  # legado intacto
    p = pessoas.listar_pets(prod)[0]
    assert (p["dono"], p["nascimento"]) == ("giovanna", "2017-07-20")
    contato.desfazer(prod, r["historico_id"], "boss", AGORA)
    p = pessoas.listar_pets(prod)[0]
    assert (p["dono"], p["nascimento"], p["raca"]) == ("louise", "2017-07-19", None)
