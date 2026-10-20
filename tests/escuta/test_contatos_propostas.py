from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.escuta import contatos as c
from gabi.escuta import contatos_propostas as p

MIGR = Path(__file__).parent.parent.parent / "migrations"
NESS = "resper@ness.com.br"
AGORA = "2026-10-20T10:00:00Z"
NUM = "+5511912345678"


@pytest.fixture
def con(tmp_path):
    k = conectar(tmp_path / "t.db")
    migrar(k, MIGR)
    return k


def _rem(con, numero=NUM, nome="Fulano", estado="aprovado"):
    con.execute("insert into escuta_remetente(numero, nome, estado) values (?,?,?)", (numero, nome, estado))


def _graph(con, gid="g1", nome="Beltrano", orig="11 9999-0000", tel="+5511999990000", campo="mobile", conta=NESS):
    con.execute("insert into contato_graph(conta, graph_id, nome, telefone_original, telefone, campo) values (?,?,?,?,?,?)",
                (conta, gid, nome, orig, tel, campo))


def _props(con):
    return [dict(r) for r in con.execute("select * from contato_proposta order by id")]


def test_criar_para_remetente_aprovado_com_nome_sem_contato(con):
    _rem(con, nome="  Fulano  ")
    assert p.gerar(con, AGORA) == {"criar": 1, "corrigir": 0}
    (r,) = _props(con)
    assert (r["tipo"], r["conta"], r["graph_id"], r["origem"], r["estado"]) == ("criar", NESS, None, "whatsapp", "pendente")
    assert (r["nome_depois"], r["telefone_depois"], r["criada_em"]) == ("Fulano", NUM, AGORA)


@pytest.mark.parametrize("nome", [None, "", "   "])
def test_nao_cria_sem_nome(con, nome):
    _rem(con, nome=nome)
    assert p.gerar(con, AGORA) == {"criar": 0, "corrigir": 0}


def test_nao_cria_remetente_nao_aprovado_ou_numero_estranho(con):
    _rem(con, estado="pendente")
    _rem(con, numero="123", nome="X")
    assert p.gerar(con, AGORA)["criar"] == 0


@pytest.mark.parametrize("onde", ["graph", "google"])
def test_nao_cria_se_numero_ja_e_contato_ness_ou_google(con, onde):
    _rem(con)
    if onde == "graph":
        _graph(con, orig="x", tel=NUM, conta="outra@x.com")
    else:
        con.execute("insert into contato_google(conta, telefone, nome) values ('resper@gmail.com',?,'G')", (NUM,))
    assert p.gerar(con, AGORA)["criar"] == 0


def _sync(con, *itens, conta=NESS):
    """Fixture pelo caminho real: itens brutos do Graph -> contatos.sincronizar -> contato_graph."""
    c.sincronizar(con, [conta], lambda _c: [dict(i) for i in itens])
    con.commit()


def _it(tel, nome="Beltrano", gid="AAMk0001", campo="mobile"):
    return {"nome": nome, "telefone": tel, "graph_id": gid, "campo": campo}


def test_celular_antigo_de_8_digitos_gera_exatamente_uma_correcao(con):
    _sync(con, _it("11 9999-0000", nome="  Beltrano "))
    assert p.gerar(con, AGORA) == {"criar": 0, "corrigir": 1}
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
    assert p.gerar(con, AGORA) == {"criar": 0, "corrigir": 0}


@pytest.mark.parametrize("campo", ["home", "business", None])
def test_nao_corrige_telefone_fixo_ou_de_trabalho(con, campo):
    _sync(con, _it("11 9999-0000", campo=campo))
    assert p.gerar(con, AGORA)["corrigir"] == 0


@pytest.mark.parametrize("bruto", ["(11) 9999-0000 ramal 5", "11 9999-0000 x 12", "+1 415 555 0000", "123"])
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
    assert p.gerar(con, AGORA) == {"criar": 0, "corrigir": 0}
    _sync(con, _it("11 9999-0000", nome="Novo Nome"))
    assert p.gerar(con, AGORA)["corrigir"] == 1
    assert len(_props(con)) == 2


def test_aplicada_nao_repete(con):
    _rem(con)
    p.gerar(con, AGORA)
    con.execute("update contato_proposta set estado='aplicada'")
    assert p.gerar(con, AGORA)["criar"] == 0


def test_gerar_e_idempotente(con):
    _rem(con)
    _sync(con, _it("11 9999-0000"))
    assert p.gerar(con, AGORA) == {"criar": 1, "corrigir": 1}
    assert p.gerar(con, AGORA) == {"criar": 0, "corrigir": 0}
    assert len(_props(con)) == 2


def test_decidir_de_pendente_e_recusar_aprovada(con):
    _rem(con)
    p.gerar(con, AGORA)
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
    _rem(con)
    p.gerar(con, AGORA)
    pid = _props(con)[0]["id"]
    con.execute("update contato_proposta set estado=?", (final,))
    with pytest.raises(p.ErroProposta) as e:
        p.decidir(con, pid, estado, "ricardo", AGORA)
    assert e.value.conflito and _props(con)[0]["estado"] == final


def test_recusar_aprovada_com_auditoria_quebrada_desfaz(con):
    _rem(con)
    p.gerar(con, AGORA)
    pid = _props(con)[0]["id"]
    p.decidir(con, pid, "aprovada", "ricardo", AGORA)

    def quebra():
        raise RuntimeError("x")
    with pytest.raises(RuntimeError):
        p.decidir(con, pid, "recusada", "ricardo", AGORA, auditar=quebra)
    assert _props(con)[0]["estado"] == "aprovada"


def _duas_correcoes(con):
    _sync(con, _it("11 9999-0000"), _it("11 9888-0000", nome="Ciclano", gid="AAMk0002"))
    _rem(con)
    p.gerar(con, AGORA)
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


@pytest.mark.parametrize("ids", [[], None, "1", [1, "2"], [True], [1.5]])
def test_aprovar_correcoes_ids_invalidos(con, ids):
    with pytest.raises(p.ErroProposta):
        p.aprovar_correcoes(con, "ricardo", AGORA, ids)


def test_listar_filtra_por_estado_e_ordena(con):
    _rem(con)
    _sync(con, _it("11 9999-0000"))
    p.gerar(con, AGORA)
    assert [r["tipo"] for r in p.listar(con)] == ["criar", "corrigir"]
    p.aprovar_correcoes(con, "r", AGORA, [r["id"] for r in p.listar(con)])
    assert [r["tipo"] for r in p.listar(con, "aprovada")] == ["corrigir"]


def test_main_gera_propostas_e_imprime_so_contagens(tmp_path, capsys):
    banco = tmp_path / "m.db"
    k = conectar(banco); migrar(k, MIGR); _rem(k, nome="Segredo"); k.commit(); k.close()
    code = c.main(banco, listar=lambda conta: [])
    out = capsys.readouterr().out
    assert code == 0 and "propostas: criar=1 corrigir=0" in out and "Segredo" not in out and "912345678" not in out
