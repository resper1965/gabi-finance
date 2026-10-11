import csv
import io
import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.escuta import contatos as c
from gabi.escuta import remetentes

MIGR = Path(__file__).parent.parent.parent / "migrations"
GMAIL, NESS = "resper@gmail.com", "resper@ness.com.br"


@pytest.fixture
def con(tmp_path):
    k = conectar(tmp_path / "t.db")
    migrar(k, MIGR)
    return k


def _listar(dados):
    return lambda conta: list(dados.get(conta, []))


def _linhas(con):
    return sorted((r["conta"], r["telefone"], r["nome"]) for r in con.execute("select conta, telefone, nome from contato_google"))


def test_mesmo_telefone_nas_duas_contas_e_um_contato(con):
    dados = {GMAIL: [{"nome": "Ana", "telefone": "(11) 91234-5678"}], NESS: [{"nome": "Ana S.", "telefone": "+55 11 91234-5678"}]}
    r = c.sincronizar(con, [GMAIL, NESS], _listar(dados))
    assert r == {"contas": {GMAIL: {"lidos": 1}, NESS: {"lidos": 1}}, "total": 1, "invalidos": 0}
    assert _linhas(con) == [(GMAIL, "+5511912345678", "Ana"), (NESS, "+5511912345678", "Ana S.")]
    assert [x["telefone"] for x in c.listar_unicos(con)] == ["+5511912345678"]


def test_nome_do_gmail_vence(con):
    dados = {NESS: [{"nome": "Ana da ness", "telefone": "11912345678"}], GMAIL: [{"nome": "Aninha", "telefone": "11912345678"}]}
    c.sincronizar(con, [NESS, GMAIL], _listar(dados))
    assert c.nome_do_numero(con, "+5511912345678") == "Aninha"
    assert c.nome_do_numero(con, "+5511900000000") is None
    con.execute("update contato_google set nome=null where conta=?", (GMAIL,))
    assert c.nome_do_numero(con, "+5511912345678") == "Ana da ness"


def test_nome_vazio_nao_vale(con):
    c.sincronizar(con, [GMAIL], _listar({GMAIL: [{"nome": None, "telefone": "11912345678"}]}))
    assert c.nome_do_numero(con, "+5511912345678") is None


def test_numero_invalido_e_pulado_e_contado_e_duplicata_na_conta_vira_uma(con):
    dados = {GMAIL: [{"nome": "A", "telefone": "123"}, {"nome": "B", "telefone": "11912345678"}, {"nome": None, "telefone": "11912345678"}, {"nome": "C", "telefone": None}]}
    r = c.sincronizar(con, [GMAIL], _listar(dados))
    assert r["invalidos"] == 2 and r["total"] == 1 and r["contas"] == {GMAIL: {"lidos": 4}}
    assert _linhas(con) == [(GMAIL, "+5511912345678", "B")]


def test_contato_removido_some_na_proxima_sincronizacao(con):
    dados = {GMAIL: [{"nome": "A", "telefone": "11911111111"}, {"nome": "B", "telefone": "11922222222"}]}
    c.sincronizar(con, [GMAIL], _listar(dados))
    dados[GMAIL].pop()
    c.sincronizar(con, [GMAIL], _listar(dados))
    assert _linhas(con) == [(GMAIL, "+5511911111111", "A")]


def test_sincronizar_conta_removida_do_parametro_some_da_lista(con):
    dados = {GMAIL: [{"nome": "A", "telefone": "11911111111"}], NESS: [{"nome": "B", "telefone": "11922222222"}]}
    c.sincronizar(con, [GMAIL, NESS], _listar(dados))
    r = c.sincronizar(con, [GMAIL], _listar(dados))
    assert _linhas(con) == [(GMAIL, "+5511911111111", "A")] and r["total"] == 1



def _com_falhas(dados, falhas):
    def listar(conta):
        if conta in falhas:
            raise falhas[conta]
        return list(dados.get(conta, []))
    return listar


def test_ness_falha_gmail_sincroniza_e_linhas_antigas_da_ness_ficam(con):
    c.sincronizar(con, [GMAIL, NESS], _listar({GMAIL: [{"nome": "Velho", "telefone": "11911111111"}], NESS: [{"nome": "Ness antigo", "telefone": "11922222222"}]}))
    falhas = {NESS: c.ErroGoogleContatos(f"conta não autorizada: {NESS}")}
    r = c.sincronizar(con, [GMAIL, NESS], _com_falhas({GMAIL: [{"nome": "Novo", "telefone": "11933333333"}]}, falhas))
    assert r["contas"] == {GMAIL: {"lidos": 1}, NESS: {"erro": f"conta não autorizada: {NESS}"}}
    assert _linhas(con) == [(GMAIL, "+5511933333333", "Novo"), (NESS, "+5511922222222", "Ness antigo")] and r["total"] == 2


def test_falha_na_segunda_pagina_nao_grava_lista_parcial(con):
    c.sincronizar(con, [GMAIL], _listar({GMAIL: [{"nome": "A", "telefone": "11911111111"}]}))
    r = c.sincronizar(con, [GMAIL], _com_falhas({}, {GMAIL: c.ErroGoogleContatos("people.connections.list -> 500")}))
    assert _linhas(con) == [(GMAIL, "+5511911111111", "A")] and "erro" in r["contas"][GMAIL]


def test_erro_nao_tipado_so_leva_o_nome_do_tipo(con):
    r = c.sincronizar(con, [GMAIL], _com_falhas({}, {GMAIL: RuntimeError("segredo 912345678")}))
    assert r["contas"][GMAIL] == {"erro": "RuntimeError"}


def test_conta_malformada_no_parametro_falha_so_ela(con):
    def listar(conta):
        if "@" not in conta:
            raise c.ErroGoogleContatos("conta inválida")
        return [{"nome": "A", "telefone": "11911111111"}]
    r = c.sincronizar(con, ["lixo", GMAIL], listar)
    assert r["contas"] == {"lixo": {"erro": "conta inválida"}, GMAIL: {"lidos": 1}} and _linhas(con) == [(GMAIL, "+5511911111111", "A")]


def test_todas_as_contas_falhando_nao_mexe_na_tabela_mas_conta_removida_e_purgada(con):
    c.sincronizar(con, [GMAIL, NESS], _listar({GMAIL: [{"nome": "A", "telefone": "11911111111"}], NESS: [{"nome": "B", "telefone": "11922222222"}]}))
    r = c.sincronizar(con, [GMAIL], _com_falhas({}, {GMAIL: c.ErroGoogleContatos("x")}))
    assert _linhas(con) == [(GMAIL, "+5511911111111", "A")] and all("erro" in v for v in r["contas"].values())


@pytest.mark.parametrize("item,esperado", [
    ({"telefone": "+1 (415) 555-2671"}, None),
    ({"telefone": "+44 20 7946 0958"}, None),
    ({"telefone": "001 415 555 2671"}, None),
    ({"telefone": "(11) 3456-7890 r.1"}, None),
    ({"telefone": "11 3456-7890 ramal 12"}, None),
    ({"telefone": "11912345678 x5"}, None),
    ({"telefone": "11912345678 ext 5"}, None),
    ({"telefone": "11912345678#2"}, None),
    ({"telefone": "+55 11 91234-5678"}, "+5511912345678"),
    ({"telefone": "0055 11 91234-5678"}, "+5511912345678"),
    ({"telefone": "(11) 91234-5678"}, "+5511912345678"),
    ({"telefone": "+1 (415) 555-2671", "canonico": "+14155552671"}, "+14155552671"),
    ({"telefone": "(11) 91234-5678", "canonico": "+5511912345678"}, "+5511912345678"),
    ({"telefone": "(11) 91234-5678", "canonico": "lixo"}, "+5511912345678"),
])
def test_telefones_internacionais_e_ramais(con, item, esperado):
    r = c.sincronizar(con, [GMAIL], _listar({GMAIL: [{"nome": "X", **item}]}))
    if esperado is None:
        assert r["invalidos"] == 0 + 1 and _linhas(con) == []
    else:
        assert _linhas(con) == [(GMAIL, esperado, "X")] and r["invalidos"] == 0


def test_saida_so_com_contagens(con):
    r = c.sincronizar(con, [GMAIL], _listar({GMAIL: [{"nome": "Segredo Nome", "telefone": "11912345678"}]}))
    assert "Segredo" not in json.dumps(r) and "912345678" not in json.dumps(r)


def test_contas_do_parametro_e_padrao(con):
    assert c.contas_contatos(con) == [GMAIL, NESS]
    con.execute("insert into parametro(chave, valor) values ('escuta.contas_contatos', ?)", (json.dumps(["a@x.com", "a@x.com", 3]),))
    assert c.contas_contatos(con) == ["a@x.com"]
    con.execute("update parametro set valor='lixo' where chave='escuta.contas_contatos'")
    assert c.contas_contatos(con) == [GMAIL, NESS]
    assert c.conta_origem(con) == NESS and c.conta_destino(con) == GMAIL


def test_so_na_ness_exclui_o_que_ja_esta_no_gmail(con):
    dados = {NESS: [{"nome": "Zé", "telefone": "11911111111"}, {"nome": "Ana", "telefone": "11922222222"}],
             GMAIL: [{"nome": "Ana G", "telefone": "(11) 92222-2222"}]}
    c.sincronizar(con, [GMAIL, NESS], _listar(dados))
    assert c.so_na(con, NESS, GMAIL) == [{"nome": "Zé", "telefone": "+5511911111111"}]
    assert c.so_na(con, GMAIL, NESS) == []


def test_csv_formato_do_google():
    s = c.csv_google([{"nome": "Ana", "telefone": "+5511912345678"}, {"nome": 'Silva, "Zé"', "telefone": "+5511900000000"}])
    assert s.splitlines()[0] == "Name,Phone 1 - Value"
    assert list(csv.reader(io.StringIO(s))) == [["Name", "Phone 1 - Value"], ["Ana", "+5511912345678"], ['Silva, "Zé"', "+5511900000000"]]
    assert '"Silva, ""Zé"""' in s and s.endswith("\r\n")


@pytest.mark.parametrize("nome", ["=1+1", "+cmd", "-2", "@SUM(A1)", "\tx", "\rx"])
def test_csv_nome_que_parece_formula_ganha_apostrofo(nome):
    linha = list(csv.reader(io.StringIO(c.csv_google([{"nome": nome, "telefone": "+5511912345678"}]))))[1]
    assert linha[0] == "'" + nome and linha[1] == "+5511912345678"


def test_csv_so_nome_e_telefone_e_telefone_estranho_fica_de_fora():
    s = c.csv_google([{"nome": "A", "telefone": "+5511912345678", "email": "x@y"}, {"nome": "B", "telefone": "=cmd"}, {"nome": None, "telefone": "+5511900000001"}])
    assert "x@y" not in s and "cmd" not in s
    assert list(csv.reader(io.StringIO(s)))[2] == ["", "+5511900000001"]


def test_fila_mostra_nome_do_contato_via_nome_do_numero(con):
    c.sincronizar(con, [NESS, GMAIL], _listar({NESS: [{"nome": "Ness", "telefone": "11912345678"}], GMAIL: [{"nome": "Gmail", "telefone": "11912345678"}]}))
    con.execute("insert into escuta_remetente(numero, estado, vista_em, qtd) values ('+5511912345678','pendente','2026-10-11T10:00:00',1)")
    assert remetentes.fila(con)[0]["nome"] == "Gmail"


def test_main_imprime_so_contagens(tmp_path, capsys, monkeypatch):
    banco = tmp_path / "m.db"
    k = conectar(banco); migrar(k, MIGR); k.close()
    code = c.main(banco, listar=_listar({GMAIL: [{"nome": "Segredo", "telefone": "11912345678"}]}))
    out = capsys.readouterr().out
    assert code == 0 and "total=1" in out and "Segredo" not in out and "912345678" not in out


def test_main_sem_socket_e_erro(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("GABI_FONTES_SOCKET", raising=False)
    assert c.main(tmp_path / "m.db") == 2


def _banco(tmp_path):
    banco = tmp_path / "m.db"
    k = conectar(banco); migrar(k, MIGR); k.close()
    return banco


def test_main_conta_nao_autorizada_com_outra_ok_sai_0_e_avisa_pelo_nome(tmp_path, capsys):
    f = _com_falhas({GMAIL: [{"nome": "Segredo", "telefone": "11912345678"}]}, {NESS: c.ErroGoogleContatos(f"conta não autorizada: {NESS}")})
    assert c.main(_banco(tmp_path), listar=f) == 0
    cap = capsys.readouterr()
    assert NESS in cap.err and "Segredo" not in cap.out + cap.err and "912345678" not in cap.out + cap.err and "total=1" in cap.out


def test_main_todas_falham_sai_1(tmp_path, capsys):
    f = _com_falhas({}, {GMAIL: c.ErroGoogleContatos(f"conta não autorizada: {GMAIL}"), NESS: c.ErroGoogleContatos(f"conta não autorizada: {NESS}")})
    assert c.main(_banco(tmp_path), listar=f) == 1


def test_main_falha_inesperada_de_uma_conta_sai_1(tmp_path):
    f = _com_falhas({GMAIL: [{"nome": "A", "telefone": "11912345678"}]}, {NESS: c.ErroGoogleContatos("people.connections.list -> 500")})
    assert c.main(_banco(tmp_path), listar=f) == 1
