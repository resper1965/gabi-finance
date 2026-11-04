import sqlite3
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.contatos import contatos as c
from gabi.contatos import contatos_propostas as p

MIGR = Path(__file__).parent.parent.parent / "migrations"
NESS = "resper@ness.com.br"
AGORA = "2026-10-20T10:00:00Z"
NUM = "+5511912345678"



def _antigas(r):
    """Só criar/corrigir: os tipos de limpeza têm testes próprios."""
    return {k: r[k] for k in ("corrigir",)}

@pytest.fixture
def con(tmp_path):
    k = conectar(tmp_path / "t.db")
    migrar(k, MIGR)
    return k


def _graph(con, gid="g1", nome="Beltrano", orig="11 9999-0000", tel="+5511999990000", campo="mobile", conta=NESS):
    con.execute("insert into contato_graph(conta, graph_id, nome, telefone_original, telefone, campo) values (?,?,?,?,?,?)",
                (conta, gid, nome, orig, tel, campo))


def _criar(con, nome="Fulano", numero=NUM):
    """Uma proposta `criar` pendente antiga (o tipo segue decidível, mas não é mais gerado; ADR-023)."""
    p._inserir(con, AGORA, "criar", NESS, None, None, None, nome, numero, "whatsapp")


def _props(con):
    return [dict(r) for r in con.execute("select * from contato_proposta order by id")]


def _sync(con, *itens, conta=NESS):
    """Fixture pelo caminho real: itens brutos do Graph -> contatos.sincronizar -> contato_graph."""
    c.sincronizar(con, [conta], lambda _c: [dict(i) for i in itens])
    con.commit()


def _it(tel, nome="Beltrano", gid="AAMk0001", campo="mobile"):
    return {"nome": nome, "telefone": tel, "graph_id": gid, "campo": campo}


def test_celular_antigo_de_8_digitos_gera_exatamente_uma_correcao(con):
    _sync(con, _it("11 9999-0000", nome="  Beltrano "))
    assert _antigas(p.gerar(con, AGORA)) == {"corrigir": 1}
    (r,) = _props(con)
    assert (r["tipo"], r["conta"], r["graph_id"], r["origem"], r["estado"]) == ("corrigir", NESS, "AAMk0001", "telefone_invalido", "pendente")
    assert (r["nome_antes"], r["telefone_antes"]) == ("Beltrano", "11 9999-0000")
    assert (r["nome_depois"], r["telefone_depois"]) == ("Beltrano", "+5511999990000")


@pytest.mark.parametrize("bruto", ["+55 11 9999-0000", "005511 9999 0000", "(55) 9999-0000"])
def test_celular_antigo_com_ddi_ou_ddd_55_tambem_corrige(con, bruto):
    _sync(con, _it(bruto))
    assert p.gerar(con, AGORA)["corrigir"] == 1


@pytest.mark.parametrize("bruto", ["(11) 99999-0000", "+55 11 99999-0000", "11999990000", "+5511999990000", "0055 11 99999-0000",
                                   "(011) 9999-0000", "55 99999-0000"])
def test_so_formatacao_diferente_nao_gera_proposta(con, bruto):
    _sync(con, _it(bruto))
    assert _antigas(p.gerar(con, AGORA)) == {"corrigir": 0}


@pytest.mark.parametrize("campo", ["home", "business", None])
def test_nao_corrige_telefone_fixo_ou_de_trabalho(con, campo):
    _sync(con, _it("11 9999-0000", campo=campo))
    assert p.gerar(con, AGORA)["corrigir"] == 0


def test_estrangeiro_tem_telefone_mas_nunca_gera_corrigir(con):
    _sync(con, _it("+1 415 555 0000"))
    assert con.execute("select telefone from contato_graph").fetchone()[0] == "+14155550000"
    assert p.gerar(con, AGORA)["corrigir"] == 0


@pytest.mark.parametrize("bruto", ["(11) 9999-0000 ramal 5", "11 9999-0000 x 12", "123"])
def test_ramal_ou_numero_que_nao_normaliza_nunca_gera(con, bruto):
    _sync(con, _it(bruto))
    assert con.execute("select telefone from contato_graph").fetchone()[0] is None
    assert p.gerar(con, AGORA)["corrigir"] == 0


@pytest.mark.parametrize("nome", [None, "  "])
def test_nao_corrige_contato_sem_nome(con, nome):
    _sync(con, _it("11 9999-0000", nome=nome))
    assert p.gerar(con, AGORA)["corrigir"] == 0


def test_nao_corrige_se_outra_linha_ja_tem_o_numero(con):
    _sync(con, _it("11 9999-0000"), _it("+5511999990000", gid="AAMk0002", nome="Outro", campo="home"))
    assert p.gerar(con, AGORA)["corrigir"] == 0


def test_nao_corrige_se_o_mesmo_contato_tem_o_numero_em_outro_campo(con):
    _sync(con, _it("11 9999-0000"), _it("(11) 99999-0000", campo="home"))
    assert p.gerar(con, AGORA)["corrigir"] == 0


def test_recusada_nao_repete_mesmo_valor_e_repete_valor_novo(con):
    _sync(con, _it("11 9999-0000"))
    p.gerar(con, AGORA)
    p.decidir(con, _props(con)[0]["id"], "recusada", "ricardo", AGORA)
    assert _antigas(p.gerar(con, AGORA)) == {"corrigir": 0}
    _sync(con, _it("11 9999-0000", nome="Novo Nome"))
    assert p.gerar(con, AGORA)["corrigir"] == 1
    assert len(_props(con)) == 2


def test_gerar_e_idempotente(con):
    _sync(con, _it("11 9999-0000"))
    assert _antigas(p.gerar(con, AGORA)) == {"corrigir": 1}
    assert _antigas(p.gerar(con, AGORA)) == {"corrigir": 0}
    assert len(_props(con)) == 1


def test_decidir_de_pendente_e_recusar_aprovada(con):
    _criar(con)
    pid = _props(con)[0]["id"]
    p.decidir(con, pid, "aprovada", "ricardo", AGORA)
    r = _props(con)[0]
    assert (r["estado"], r["decidida_por"], r["decidida_em"]) == ("aprovada", "ricardo", AGORA)
    with pytest.raises(p.ErroProposta) as e:  # aprovada só volta atrás como recusada
        p.decidir(con, pid, "aprovada", "ricardo", AGORA)
    assert e.value.conflito
    auditou = []
    p.decidir(con, pid, "recusada", "outro", "2026-10-21T00:00:00Z", auditar=lambda: auditou.append(1))
    r = _props(con)[0]
    assert (r["estado"], r["decidida_por"], r["decidida_em"]) == ("recusada", "outro", "2026-10-21T00:00:00Z") and auditou == [1]
    with pytest.raises(p.ErroProposta) as e:
        p.decidir(con, 999, "aprovada", "ricardo", AGORA)
    assert e.value.nao_encontrado
    with pytest.raises(p.ErroProposta) as e:
        p.decidir(con, pid, "aplicada", "ricardo", AGORA)
    assert not e.value.conflito and not e.value.nao_encontrado


@pytest.mark.parametrize("final", ["recusada", "aplicada", "falhou"])
@pytest.mark.parametrize("estado", ["aprovada", "recusada"])
def test_estados_finais_sao_terminais(con, final, estado):
    _criar(con)
    pid = _props(con)[0]["id"]
    con.execute("update contato_proposta set estado=?", (final,))
    with pytest.raises(p.ErroProposta) as e:
        p.decidir(con, pid, estado, "ricardo", AGORA)
    assert e.value.conflito and _props(con)[0]["estado"] == final


def test_recusar_aprovada_com_auditoria_quebrada_desfaz(con):
    _criar(con)
    pid = _props(con)[0]["id"]
    p.decidir(con, pid, "aprovada", "ricardo", AGORA)

    def quebra():
        raise RuntimeError("x")
    with pytest.raises(RuntimeError):
        p.decidir(con, pid, "recusada", "ricardo", AGORA, auditar=quebra)
    assert _props(con)[0]["estado"] == "aprovada"


def _duas_correcoes(con):
    _sync(con, _it("11 9999-0000"), _it("11 9888-0000", nome="Ciclano", gid="AAMk0002"))
    p.gerar(con, AGORA)
    _criar(con)
    por = {(r["tipo"], r["graph_id"]): r["id"] for r in _props(con)}
    return por[("corrigir", "AAMk0001")], por[("corrigir", "AAMk0002")], por[("criar", None)]


def test_aprovar_correcoes_so_dos_ids_dados_e_so_corrigir_pendente(con):
    a, b, criar = _duas_correcoes(con)
    auditou = []
    assert p.aprovar_correcoes(con, "ricardo", AGORA, [a, criar, 9999], auditar=auditou.append) == 1
    assert {r["id"]: r["estado"] for r in _props(con)} == {a: "aprovada", b: "pendente", criar: "pendente"}
    assert auditou == [1]
    assert p.aprovar_correcoes(con, "ricardo", AGORA, [a], auditar=auditou.append) == 0  # já não é pendente
    assert auditou == [1]
    con.execute("update contato_proposta set estado='recusada' where id=?", (b,))
    assert p.aprovar_correcoes(con, "ricardo", AGORA, [b]) == 0
    assert {r["id"]: r["estado"] for r in _props(con)} == {a: "aprovada", b: "recusada", criar: "pendente"}


def test_aprovar_correcoes_aceita_adicionar_email_e_nao_criar_nem_apagar(con):
    ids = {}
    for tipo, origem, email in (("adicionar_email", "google_email", "a@x.com"), ("corrigir", "telefone_invalido", None), ("criar", "whatsapp", None),
                                ("apagar_contato", "nome_curto", None), ("apagar_telefone", "telefone_invalido", None)):
        ids[tipo] = con.execute("insert into contato_proposta(tipo, conta, graph_id, nome_depois, telefone_depois, origem, email_depois) values (?, ?, ?, 'A', '+5511900000001', ?, ?)",
                                (tipo, NESS, None if tipo == "criar" else "g-" + tipo, origem, email)).lastrowid
    assert p.aprovar_correcoes(con, "ricardo", AGORA, list(ids.values())) == 2
    estados = {r["tipo"]: r["estado"] for r in _props(con)}
    assert estados == {"adicionar_email": "aprovada", "corrigir": "aprovada", "criar": "pendente", "apagar_contato": "pendente", "apagar_telefone": "pendente"}


@pytest.mark.parametrize("ids", [[], None, "1", [1, "2"], [True], [1.5]])
def test_aprovar_correcoes_ids_invalidos(con, ids):
    with pytest.raises(p.ErroProposta):
        p.aprovar_correcoes(con, "ricardo", AGORA, ids)


def test_listar_filtra_por_estado_e_ordena(con):
    _criar(con)
    _sync(con, _it("11 9999-0000"))
    p.gerar(con, AGORA)
    assert [r["tipo"] for r in p.listar(con)] == ["criar", "corrigir"]
    p.aprovar_correcoes(con, "r", AGORA, [r["id"] for r in p.listar(con)])
    assert [r["tipo"] for r in p.listar(con, "aprovada")] == ["corrigir"]


def test_main_gera_propostas_e_imprime_so_contagens(tmp_path, capsys):
    banco = tmp_path / "m.db"
    k = conectar(banco); migrar(k, MIGR); k.commit(); k.close()
    code = c.main(banco, listar=lambda conta: [])
    out = capsys.readouterr().out
    assert code == 0 and "propostas: corrigir=0 nomes=0 apagar_telefone=0 apagar_contato=0 adicionar_email=0 revisar=0" in out


def test_migracao_0073_aceita_tipos_novos_e_preserva_linhas(tmp_path):
    import shutil
    import sqlite3
    antes = tmp_path / "antes"
    antes.mkdir()
    for f in MIGR.glob("[0-9][0-9][0-9][0-9]_*.sql"):
        if f.name < "0073":
            shutil.copy(f, antes / f.name)
    k = conectar(tmp_path / "m.db")
    migrar(k, antes)
    k.execute("insert into contato_proposta(tipo, conta, nome_depois, telefone_depois, origem) values ('criar', ?, 'A', '+5511900000001', 'whatsapp')", (NESS,))
    k.execute("insert into contato_proposta(tipo, conta, graph_id, nome_depois, telefone_depois, origem, estado) values ('corrigir', ?, 'g', 'B', '+5511900000002', 'telefone_invalido', 'aprovada')", (NESS,))
    k.commit()
    migrar(k, MIGR)
    assert [(r["tipo"], r["estado"]) for r in k.execute("select tipo, estado from contato_proposta order by id")] == [("criar", "pendente"), ("corrigir", "aprovada")]
    k.execute("insert into contato_proposta(tipo, conta, graph_id, nome_depois, telefone_depois, origem) values ('apagar_contato', ?, 'g9', 'U', '', 'nome_curto')", (NESS,))
    with pytest.raises(sqlite3.IntegrityError):
        k.execute("insert into contato_proposta(tipo, conta, nome_depois, telefone_depois, origem) values ('qualquer', ?, 'x', '', 'whatsapp')", (NESS,))
    assert k.execute("select 1 from sqlite_master where name='contato_proposta_aberta'").fetchone()


# ---------------- limpeza (ADR-021) ----------------
@pytest.mark.parametrize("sujo,limpo", [
    ("José Rodrigo Carvalho⁹", "José Rodrigo Carvalho"),
    ("Jaqueline Jurkovich |", "Jaqueline Jurkovich"),
    ("  Ana   Lima ", "Ana Lima"),
    ("EMR3 Segurança", "EMR3 Segurança"),
    ("NOFARO", "NOFARO"),
    ("LTB SAO PAULO", "LTB SAO PAULO"),
    ("Antonio Américo (Tonico) Barbosa De Oliveira", "Antonio Américo (Tonico) Barbosa De Oliveira"),
    ("Gabriela Andrade - HomeCred", "Gabriela Andrade - HomeCred"),
    ("Maria D'Ávila Jr.", "Maria D'Ávila Jr."),
])
def test_limpar_nome(sujo, limpo):
    assert p.limpar_nome(sujo) == limpo


def _g(con):
    return p.gerar(con, AGORA)


def test_gera_corrigir_nome_uma_por_contato_mesmo_com_dois_telefones(con):
    _sync(con, _it("+5511999990001", nome="José⁹", gid="AAMk0001"), _it("+5511999990002", nome="José⁹", gid="AAMk0001", campo="home"))
    r = _g(con)
    assert r["corrigir_nome"] == 1
    (x,) = [q for q in _props(con) if q["tipo"] == "corrigir_nome"]
    assert (x["graph_id"], x["nome_antes"], x["nome_depois"], x["telefone_antes"], x["telefone_depois"], x["origem"]) == \
        ("AAMk0001", "José⁹", "José", None, "", "nome_sujo")


def test_nao_gera_nome_para_caixa_alta_nem_emr3(con):
    _sync(con, _it("+5511999990001", nome="NOFARO", gid="AAMk0001"), _it("+5511999990002", nome="EMR3 Segurança", gid="AAMk0002"))
    r = _g(con)
    assert (r["corrigir_nome"], r["apagar_contato"]) == (0, 0)


def test_gera_apagar_contato_nome_de_uma_letra(con):
    _sync(con, _it("+5511947338256", nome="U", gid="AAMk0001"))
    assert _g(con)["apagar_contato"] == 1
    (x,) = [q for q in _props(con) if q["tipo"] == "apagar_contato"]
    assert (x["graph_id"], x["nome_antes"], x["telefone_antes"], x["nome_depois"], x["telefone_depois"], x["origem"]) == \
        ("AAMk0001", "U", "+5511947338256", "U", "", "nome_curto")


def test_nao_apaga_contato_de_uma_letra_com_email_ou_segundo_telefone(con):
    _sync(con, {**_it("+5511947338256", nome="U", gid="AAMk0001"), "emails": ["u@x.com"]},
          _it("+5511911111111", nome="V", gid="AAMk0002"), _it("+5511922222222", nome="V", gid="AAMk0002", campo="home"))
    r = _g(con)
    assert (r["apagar_contato"], r["corrigir_nome"]) == (0, 0)


def test_gera_apagar_telefone_para_invalido(con):
    _sync(con, _it("12345", nome="Beltrano", gid="AAMk0001", campo="business"))
    assert _g(con)["apagar_telefone"] == 1
    (x,) = [q for q in _props(con) if q["tipo"] == "apagar_telefone"]
    # telefone_depois repete o número só para a chave de deduplicação (um contato pode ter vários inválidos)
    assert (x["graph_id"], x["nome_antes"], x["telefone_antes"], x["nome_depois"], x["telefone_depois"], x["origem"]) == \
        ("AAMk0001", "Beltrano", "12345", "Beltrano", "12345", "telefone_invalido")


def test_estrangeiro_nao_gera_apagar_telefone(con):
    _sync(con, _it("+1 415 555 2671", gid="AAMk0001"))
    assert _g(con)["apagar_telefone"] == 0


def test_limpeza_idempotente_e_recusada_nao_volta(con):
    _sync(con, _it("+5511999990001", nome="José⁹", gid="AAMk0001"), _it("+5511947338256", nome="U", gid="AAMk0002"),
          _it("123", nome="Ana", gid="AAMk0003", campo="home"))
    chaves = ("corrigir_nome", "apagar_contato", "apagar_telefone")
    r1 = _g(con)
    assert [r1[k] for k in chaves] == [1, 1, 1]
    r2 = _g(con)
    assert [r2[k] for k in chaves] == [0, 0, 0]
    con.execute("update contato_proposta set estado='recusada'")
    r3 = _g(con)
    assert [r3[k] for k in chaves] == [0, 0, 0]
    assert len(_props(con)) == 3


def test_gerar_retorna_todas_as_contagens(con):
    assert set(_g(con)) == {"corrigir", "corrigir_nome", "apagar_telefone", "apagar_contato", "adicionar_email", "revisar"}


@pytest.mark.parametrize("bruto", ["11 3456-7890 ramal 12", "(11) 3456-7890, (11) 98765-4321", "999999999", "11912345678 x5"])
def test_nao_propoe_apagar_o_que_parece_telefone_real(con, bruto):
    _sync(con, _it(bruto, gid="AAMk0001", campo="home"))
    assert con.execute("select telefone from contato_graph").fetchone()[0] is None  # segue inválido para o sincronizador
    assert _g(con)["apagar_telefone"] == 0


def test_contato_com_dois_invalidos_ganha_uma_proposta_para_cada(con):
    _sync(con, _it("123", gid="AAMk0001", campo="home"), _it("456", gid="AAMk0001", campo="business"))
    assert _g(con)["apagar_telefone"] == 2
    con.execute("update contato_proposta set estado='aplicada' where telefone_antes='123'")
    con.execute("update contato_proposta set estado='recusada' where telefone_antes='456'")
    assert _g(con)["apagar_telefone"] == 0 and len(_props(con)) == 2


_INS = ("insert into contato_proposta(tipo, conta, graph_id, nome_depois, telefone_depois, email_depois, origem) "
        "values (?,?,?,?,?,?,?)")


def test_migracao_0074_aceita_adicionar_email_e_google_email(con):
    con.execute(_INS, ("adicionar_email", NESS, "g1", "Fulano", NUM, "a@x.com;b@x.com", "google_email"))
    (r,) = _props(con)
    assert (r["tipo"], r["origem"], r["email_depois"], r["telefone_depois"]) == ("adicionar_email", "google_email", "a@x.com;b@x.com", NUM)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(_INS, ("xis", NESS, "g1", "Fulano", NUM, None, "google_email"))


def test_migracao_0074_preserva_linhas_e_indice_aberto(con):
    con.execute(_INS, ("corrigir", NESS, "g1", "Fulano", NUM, None, "whatsapp"))
    con.commit()
    migrar(con, MIGR)
    (r,) = _props(con)
    assert (r["tipo"], r["estado"], r["email_depois"]) == ("corrigir", "pendente", None)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(_INS, ("corrigir", NESS, "g1", "Fulano", NUM, None, "whatsapp"))


def _ag(con, **kw):
    """Contato da ness com telefone já em E.164 (não vira proposta de corrigir)."""
    kw.setdefault("orig", "+5511999990000")
    _graph(con, **kw)


def _gmail(con, email, tel, nome, conta="resper@gmail.com"):
    con.execute("insert into contato_google_email(conta, email, telefone, nome) values (?,?,?,?)", (conta, email, tel, nome))


def test_nome_compativel():
    assert p.nome_compativel("Ricardo Esper", "Esper")
    assert p.nome_compativel("José da Silva", "Jose Silva")
    assert not p.nome_compativel("Ana Lima", "Bruno Souza")
    assert not p.nome_compativel(None, "x")
    assert not p.nome_compativel("Maria de Souza", "Pedro de Lima")


def test_gera_adicionar_email_quando_tudo_confere(con):
    _ag(con, nome="Ana Lima")
    _gmail(con, "Ana@X.com", "+5511999990000", "Ana Lima")
    _gmail(con, "b@x.com", "+5511999990000", "Ana")
    _gmail(con, "ana@x.com", "+5511999990000", "Ana", conta="outra@gmail.com")
    r = p.gerar(con, AGORA)
    assert r["adicionar_email"] == 1 and r["revisar"] == 0
    (x,) = _props(con)
    assert (x["tipo"], x["origem"], x["graph_id"], x["email_depois"]) == ("adicionar_email", "google_email", "g1", "ana@x.com;b@x.com")
    assert (x["nome_antes"], x["nome_depois"]) == ("Ana Lima", "Ana Lima")
    assert (x["telefone_antes"], x["telefone_depois"]) == ("+5511999990000",) * 2


def test_nao_gera_com_telefone_repetido_em_outro_contato(con):
    _ag(con, gid="g1", nome="Ana Lima")
    _ag(con, gid="g2", nome="Ana Lima")
    _gmail(con, "a@x.com", "+5511999990000", "Ana Lima")
    r = p.gerar(con, AGORA)
    assert r["adicionar_email"] == 0 and r["revisar"] == 2  # um por contato barrado
    assert _props(con) == []


def test_nao_gera_com_nome_sem_parte_comum(con):
    _ag(con, nome="Ana Lima")
    _gmail(con, "a@x.com", "+5511999990000", "Bruno Souza")
    r = p.gerar(con, AGORA)
    assert r["adicionar_email"] == 0 and r["revisar"] == 1 and _props(con) == []


def test_nao_gera_com_dois_telefones_validos(con):
    _ag(con, nome="Ana Lima")
    _ag(con, nome="Ana Lima", orig="+5511988880000", tel="+5511988880000", campo="home")
    _gmail(con, "a@x.com", "+5511999990000", "Ana Lima")
    r = p.gerar(con, AGORA)
    assert r["adicionar_email"] == 0 and r["revisar"] == 1 and _props(con) == []


def test_nao_gera_com_outra_linha_de_telefone_invalido(con):
    _ag(con, nome="Ana Lima")
    _ag(con, nome="Ana Lima", orig="ramal 12", tel=None, campo="business")
    _gmail(con, "a@x.com", "+5511999990000", "Ana Lima")
    r = p.gerar(con, AGORA)
    assert r["adicionar_email"] == 0 and r["revisar"] == 1


def test_nao_gera_sem_email_no_google(con):
    _ag(con, nome="Ana Lima")
    r = p.gerar(con, AGORA)
    assert r["adicionar_email"] == 0 and r["revisar"] == 0 and _props(con) == []


def test_descarta_email_sem_arroba(con):
    _ag(con, nome="Ana Lima")
    _gmail(con, "semarroba", "+5511999990000", "Ana Lima")
    _gmail(con, "a b@x.com", "+5511999990000", "Ana Lima")
    r = p.gerar(con, AGORA)
    assert r["adicionar_email"] == 0 and _props(con) == []
    _gmail(con, " Ok@X.com ", "+5511999990000", "Ana Lima")
    assert p.gerar(con, AGORA)["adicionar_email"] == 1
    assert _props(con)[0]["email_depois"] == "ok@x.com"


@pytest.mark.parametrize("estado", ["aplicada", "recusada"])
def test_aplicada_ou_recusada_nao_renasce(con, estado):
    _ag(con, nome="Ana Lima")
    _gmail(con, "a@x.com", "+5511999990000", "Ana Lima")
    assert p.gerar(con, AGORA)["adicionar_email"] == 1
    con.execute("update contato_proposta set estado=?", (estado,))
    assert p.gerar(con, AGORA)["adicionar_email"] == 0
    assert len(_props(con)) == 1


def test_gerar_devolve_chaves_novas(con):
    r = p.gerar(con, AGORA)
    assert r["adicionar_email"] == 0 and r["revisar"] == 0


def test_migracao_0074_preserva_linhas_antigas_e_indice(tmp_path):
    """Aplica as migrações até a 0073, semeia linhas no formato antigo e só então aplica a 0074."""
    ate73 = tmp_path / "ate73"
    ate73.mkdir()
    for arq in sorted(MIGR.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        if arq.name < "0074":
            (ate73 / arq.name).write_text(arq.read_text(encoding="utf-8"), encoding="utf-8")
    k = conectar(tmp_path / "m.db")
    migrar(k, ate73)
    cols = ("tipo, conta, graph_id, nome_antes, telefone_antes, nome_depois, telefone_depois, origem, estado, motivo, "
            "criada_em, decidida_em, decidida_por, aplicada_em")
    k.execute(f"insert into contato_proposta({cols}) values ('corrigir',?,'g1','Ana','11 9999-0000','Ana','+5511999990000','whatsapp','pendente','m1','2026-10-01T10:00:00Z',null,null,null)", (NESS,))
    k.execute(f"insert into contato_proposta({cols}) values ('criar',?,null,null,null,'Bia','+5511988887777','whatsapp','aplicada','m2','2026-10-02T10:00:00Z','2026-10-03T10:00:00Z','ricardo','2026-10-04T10:00:00Z')", (NESS,))
    antes = k.execute(f"select id, {cols} from contato_proposta order by id").fetchall()
    assert len(antes) == 2
    assert migrar(k, MIGR)[:1] == ["0074_contato_proposta_email.sql"]
    depois = k.execute(f"select id, {cols} from contato_proposta order by id").fetchall()
    assert [tuple(r) for r in depois] == [tuple(r) for r in antes]
    assert [r[0] for r in k.execute("select email_depois from contato_proposta")] == [None, None]
    with pytest.raises(sqlite3.IntegrityError):
        k.execute(f"insert into contato_proposta({cols}) values ('corrigir',?,'g1','Ana','x','Ana','+5511999990000','whatsapp','pendente',null,'2026-10-05T10:00:00Z',null,null,null)", (NESS,))


def test_email_de_outra_pessoa_no_mesmo_telefone_nao_vaza(con):
    _ag(con, nome="Maria Souza")
    _gmail(con, "maria@x.com", "+5511999990000", "Maria Souza")
    _gmail(con, "joao@x.com", "+5511999990000", "Joao Pereira")  # outra pessoa, mesmo telefone (casa)
    r = p.gerar(con, AGORA)
    assert r["adicionar_email"] == 0 and r["revisar"] == 1 and _props(con) == []


def test_email_de_linha_sem_nome_no_mesmo_telefone_nao_vaza(con):
    _ag(con, nome="Maria Souza")
    _gmail(con, "maria@x.com", "+5511999990000", "Maria Souza")
    _gmail(con, "anonimo@x.com", "+5511999990000", None)
    r = p.gerar(con, AGORA)
    assert r["adicionar_email"] == 0 and r["revisar"] == 1 and _props(con) == []


def test_contato_que_ja_tem_email_no_graph_nao_gera_nem_conta(con):
    _sync(con, dict(_it("+5511999990000", nome="Ana Lima"), emails=["ana@ness.com"]))
    for _ in range(3):  # sincronizações seguidas
        _sync(con, dict(_it("+5511999990000", nome="Ana Lima"), emails=["ana@ness.com"]))
        r = p.gerar(con, AGORA)
        assert r["adicionar_email"] == 0 and r["revisar"] == 0
    assert _props(con) == []


def test_ja_tem_email_no_graph_mesmo_com_email_novo_no_google(con):
    _sync(con, dict(_it("+5511999990000", nome="Ana Lima"), emails=["ana@ness.com"]))
    _gmail(con, "outro@x.com", "+5511999990000", "Ana Lima")
    r = p.gerar(con, AGORA)
    assert r["adicionar_email"] == 0 and r["revisar"] == 0 and _props(con) == []


def test_teto_de_tres_emails(con):
    _ag(con, nome="Ana Lima")
    for i in range(4):
        _gmail(con, f"a{i}@x.com", "+5511999990000", "Ana Lima")
    r = p.gerar(con, AGORA)
    assert r["adicionar_email"] == 0 and r["revisar"] == 1 and _props(con) == []
    con.execute("delete from contato_google_email where email='a3@x.com'")
    r = p.gerar(con, AGORA)
    assert r["adicionar_email"] == 1 and _props(con)[0]["email_depois"] == "a0@x.com;a1@x.com;a2@x.com"


@pytest.mark.parametrize("nome", ["李", "😀", "​"])
def test_nome_de_um_caractere_nao_latino_nao_gera_apagar_contato(con, nome):
    _graph(con, nome=nome)
    assert p.gerar(con, AGORA)["apagar_contato"] == 0


def test_telefone_longo_demais_nao_gera_apagar_telefone(con):
    _graph(con, nome="Ana", orig="x" * 31, tel=None)
    assert p.gerar(con, AGORA)["apagar_telefone"] == 0
