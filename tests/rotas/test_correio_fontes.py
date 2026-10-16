import json

import pytest
from fastapi.testclient import TestClient

from gabi.api import criar_app
from gabi.db import conectar
from gabi.fontes.google_oauth import ErroGoogleOAuth

from tests.rotas.test_escuta import AGORA, BOSS, JSON, VIP, banco  # noqa: F401  (fixture banco)

U = "/api/v1/correio"


class _Email:
    def __init__(self, erro=None, resultado="ok"):
        self.erro, self.resultado, self.chamadas = erro, resultado, []

    def restaurar(self, conta, ids):
        self.chamadas.append((conta, list(ids)))
        if self.erro:
            raise self.erro
        return {i: self.resultado for i in ids}


def _cli(banco, fonte=None):
    fontes = {"google_email": (lambda: fonte)} if fonte is not None else {}
    return TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA, fontes=fontes), client=("127.0.0.1", 50000))


@pytest.fixture
def cli(banco):
    return _cli(banco, _Email())


def _post(cli, url, corpo=None, h=BOSS):
    return cli.post(url, headers={**h, **JSON}, content=json.dumps(corpo if corpo is not None else {}))


def _patch(cli, url, corpo, h=BOSS):
    return cli.patch(url, headers={**h, **JSON}, content=json.dumps(corpo))


def _put(cli, corpo, h=BOSS):
    return cli.put(f"{U}/parametros", headers={**h, **JSON}, content=json.dumps(corpo))


def _criar(cli, conta="resper@gmail.com", **kw):
    r = _post(cli, f"{U}/fontes", {"conta": conta, **kw})
    assert r.status_code == 200, r.text
    return r.json()["dados"]["id"]


def _decisoes(banco):
    c = conectar(banco)
    r = [x["o_que"] for x in c.execute("select o_que from decisao order by id")]
    c.close()
    return r


def _msg(banco, fonte_id, ext, estado="classificada", classe="importante", prioridade=2, assunto="Proposta", thread=None, atualizado="2026-10-16T11:00:00+00:00"):
    c = conectar(banco)
    mid = c.execute("insert into email_msg(fonte_id, externo_id, thread_id, remetente, assunto, recebida_em, classe, prioridade, motivo, estado, atualizado_em) values (?,?,?,?,?,?,?,?,?,?,?)",
                    (fonte_id, ext, thread or ext + "t", "ana@x.com", assunto, "2026-10-16T10:00:00+00:00", classe, prioridade, "cliente", estado, atualizado)).lastrowid
    c.close()
    return mid


def test_so_boss_acessa(cli):
    for m, url in (("get", f"{U}/fontes"), ("post", f"{U}/fontes"), ("patch", f"{U}/fontes/1"), ("get", f"{U}/parametros"), ("put", f"{U}/parametros"),
                   ("get", f"{U}/prioridades"), ("get", f"{U}/lixeira"), ("post", f"{U}/mensagens/1/restaurar")):
        assert getattr(cli, m)(url, headers=VIP).status_code == 403, (m, url)
        assert getattr(cli, m)(url).status_code == 401, (m, url)


def test_criar_fonte_valida_conta_e_nasce_a_decidir_sem_lixeira(cli):
    assert _post(cli, f"{U}/fontes", {"conta": "isto-nao-e-email"}).status_code == 400
    assert _post(cli, f"{U}/fontes", {"conta": "a@x.com", "provedor": "imap"}).status_code == 400
    assert _post(cli, f"{U}/fontes", []).status_code == 400
    fid = _criar(cli, "Resper@Gmail.com")
    f = cli.get(f"{U}/fontes", headers=BOSS).json()["dados"]["fontes"]
    assert [(x["id"], x["conta"], x["estado"], x["lixeira"], x["provedor"], x["mensagens"], x["na_lixeira"]) for x in f] == [(fid, "resper@gmail.com", "a_decidir", 0, "google", 0, 0)]
    assert _post(cli, f"{U}/fontes", {"conta": "resper@gmail.com"}).status_code == 409  # minúsculas: mesma conta
    assert _post(cli, f"{U}/fontes", {"conta": "g@x.com", "provedor": "graph"}).status_code == 200


def test_liberar_leitura_e_lixeira_sao_chaves_separadas_e_a_lixeira_exige_leitura(cli, banco):
    fid = _criar(cli)
    assert _patch(cli, f"{U}/fontes/{fid}", {"lixeira": 1}).status_code == 400  # a_decidir: não pode ligar a lixeira
    assert _patch(cli, f"{U}/fontes/{fid}", {"estado": "sim"}).status_code == 200
    ler = lambda: cli.get(f"{U}/fontes", headers=BOSS).json()["dados"]["fontes"][0]  # noqa: E731
    assert (ler()["estado"], ler()["lixeira"]) == ("sim", 0)  # liberar a leitura NÃO liga a lixeira
    assert _patch(cli, f"{U}/fontes/{fid}", {"lixeira": 1}).status_code == 200 and ler()["lixeira"] == 1
    assert _patch(cli, f"{U}/fontes/{fid}", {"estado": "nao"}).status_code == 200
    assert (ler()["estado"], ler()["lixeira"]) == ("nao", 0)  # desligar a leitura desliga a lixeira junto
    assert _patch(cli, f"{U}/fontes/{fid}", {"estado": "talvez"}).status_code == 400
    assert _patch(cli, f"{U}/fontes/{fid}", {"lixeira": 2}).status_code == 400
    assert _patch(cli, f"{U}/fontes/{fid}", {"lixeira": True}).status_code == 400
    assert _patch(cli, f"{U}/fontes/{fid}", {}).status_code == 400
    assert _patch(cli, f"{U}/fontes/999", {"estado": "sim"}).status_code == 404
    d = " | ".join(_decisoes(banco))
    assert f"conta {fid} → estado nao, lixeira 0" in d and "lixeira 1" in d


def test_parametros_padrao_gravacao_e_normalizacao_dos_vips(cli):
    padrao = cli.get(f"{U}/parametros", headers=BOSS).json()["dados"]
    assert {k: v for k, v in padrao.items() if k != "palavras_protegidas"} == {"criterios_emergencia": "", "vips": [], "lixeira_confianca": 0.9, "janela_dias": 14, "retencao_dias": 30,
                                                                                "dias_em_aberto": 7, "max_alertas_dia": 5}
    assert "fatura" in padrao["palavras_protegidas"] and "boleto" in padrao["palavras_protegidas"]  # a lista padrão aparece para o dono editar
    r = _put(cli, {"vips": ["Chefe@Ionic.com", "chefe@ionic.com", " bia@x.com "], "criterios_emergencia": "banco ou cobrança com prazo", "lixeira_confianca": 0.95})
    assert r.status_code == 200
    d = r.json()["dados"]
    assert d["vips"] == ["chefe@ionic.com", "bia@x.com"] and d["criterios_emergencia"] == "banco ou cobrança com prazo" and d["lixeira_confianca"] == 0.95


@pytest.mark.parametrize("corpo", [{}, {"outra": 1}, {"vips": "chefe@x.com"}, {"vips": ["nao-e-email"]}, {"vips": [3]}, {"vips": ["a@x.com"] * 0 + [f"u{i}@x.com" for i in range(201)]},
                                   {"criterios_emergencia": 5}, {"criterios_emergencia": "x" * 2001}, {"lixeira_confianca": 0.49}, {"lixeira_confianca": 1.01},
                                   {"lixeira_confianca": "0.9"}, {"lixeira_confianca": True}, {"janela_dias": 0}, {"janela_dias": 61}, {"janela_dias": 1.5},
                                   {"retencao_dias": 0}, {"retencao_dias": 366}, {"retencao_dias": True},
                                   {"dias_em_aberto": 0}, {"dias_em_aberto": 31}, {"dias_em_aberto": True}, {"max_alertas_dia": 0}, {"max_alertas_dia": 51}, {"max_alertas_dia": 2.5},
                                   {"palavras_protegidas": "fatura"}, {"palavras_protegidas": [3]}, {"palavras_protegidas": ["x" * 61]}, {"palavras_protegidas": ["a"] * 0 + [f"p{i}" for i in range(201)]}])
def test_parametros_validam_faixas(cli, corpo):
    assert _put(cli, corpo).status_code == 400
    assert cli.get(f"{U}/parametros", headers=BOSS).json()["dados"]["lixeira_confianca"] == 0.9


def test_parametros_nao_logam_valores(cli, banco):
    _put(cli, {"vips": ["chefe@secreto.com"], "criterios_emergencia": "CRITERIO-SECRETO", "lixeira_confianca": 0.97})
    d = " | ".join(_decisoes(banco))
    assert "email.vips" in d and "email.criterios_emergencia" in d and "secreto" not in d.lower() and "0.97" not in d


def test_prioridades_e_lixeira_so_de_fontes_liberadas(cli, banco):
    f = _criar(cli); g = _criar(cli, "b@x.com")
    _patch(cli, f"{U}/fontes/{f}", {"estado": "sim"})
    _msg(banco, f, "a", "classificada", "importante", 3, "Contrato"); _msg(banco, f, "b", "alertada", "emergencial", 3, "Boleto")
    _msg(banco, f, "c", "na_lixeira", "lixo", 0, "Promo"); _msg(banco, g, "d", "classificada", "importante", 3, "Oculto")
    p = cli.get(f"{U}/prioridades", headers=BOSS).json()["dados"]["mensagens"]
    assert [m["assunto"] for m in p] == ["Boleto", "Contrato"]  # emergencial primeiro; fonte a_decidir não aparece
    assert [m["assunto"] for m in cli.get(f"{U}/lixeira", headers=BOSS).json()["dados"]["mensagens"]] == ["Promo"]


def test_restaurar_chama_a_ponte_marca_restaurada_fecha_o_alerta_e_e_idempotente(banco):
    fonte = _Email()
    cli = _cli(banco, fonte)
    f = _criar(cli); _patch(cli, f"{U}/fontes/{f}", {"estado": "sim"})
    mid = _msg(banco, f, "ab12cd", "na_lixeira", "lixo", 0, "Promo", thread="T9")
    c = conectar(banco)
    c.execute("insert into aviso(tipo, payload, criado_em) values ('email_emergencial', ?, '2026-10-16T10:00:00+00:00')", (json.dumps({"chave": "T9", "remetente": "a@x.com", "assunto": "s", "motivo": "m"}),))
    c.close()
    r = _post(cli, f"{U}/mensagens/{mid}/restaurar")
    assert r.status_code == 200 and r.json()["dados"] == {"id": mid, "estado": "restaurada"}
    assert fonte.chamadas == [("resper@gmail.com", ["ab12cd"])]
    c = conectar(banco)
    assert c.execute("select estado from email_msg where id=?", (mid,)).fetchone()[0] == "restaurada"
    assert c.execute("select count(*) from aviso where tipo='email_emergencial' and entregue_em is null").fetchone()[0] == 0
    c.close()
    assert _post(cli, f"{U}/mensagens/{mid}/restaurar").status_code == 200 and len(fonte.chamadas) == 1  # idempotente: nem chama a ponte de novo
    assert any(f"restaurou mensagem {mid}" in d for d in _decisoes(banco)) and "Promo" not in " ".join(_decisoes(banco))


def test_restaurar_nao_exige_a_fonte_ainda_liberada_mas_exige_estar_na_lixeira(banco):
    cli = _cli(banco, _Email())
    f = _criar(cli)
    ok = _msg(banco, f, "aa11bb", "na_lixeira", "lixo", 0); fora = _msg(banco, f, "cc22dd", "classificada")
    assert _post(cli, f"{U}/mensagens/{ok}/restaurar").status_code == 200  # fonte desligada depois: ainda dá para recuperar
    assert _post(cli, f"{U}/mensagens/{fora}/restaurar").status_code == 409
    assert _post(cli, f"{U}/mensagens/999/restaurar").status_code == 404


def test_restaurar_com_ponte_fora_ou_recusa_vira_503_e_nao_marca(banco):
    f_erro = _cli(banco, _Email(erro=ErroGoogleOAuth("serviço de fontes indisponível")))
    f = _criar(f_erro)
    mid = _msg(banco, f, "aa11bb", "na_lixeira", "lixo", 0)
    r = _post(f_erro, f"{U}/mensagens/{mid}/restaurar")
    assert r.status_code == 503 and r.json()["erro"] == "fonte_indisponivel"
    r = _post(_cli(banco, _Email(resultado="erro")), f"{U}/mensagens/{mid}/restaurar")
    assert r.status_code == 503 and r.json()["erro"] == "fonte_indisponivel"
    r = _post(_cli(banco), f"{U}/mensagens/{mid}/restaurar")  # fonte não configurada
    assert r.status_code == 503
    c = conectar(banco)
    assert c.execute("select estado from email_msg where id=?", (mid,)).fetchone()[0] == "na_lixeira"
    c.close()


def test_restaurada_nunca_volta_sozinha_a_lixeira_depois_de_restaurar_pelo_painel(banco):
    from gabi.correio import processar as pr
    from gabi.dinheiro.modelo import Orcamento
    cli = _cli(banco, _Email())
    f = _criar(cli); _patch(cli, f"{U}/fontes/{f}", {"estado": "sim"}); _patch(cli, f"{U}/fontes/{f}", {"lixeira": 1})
    mid = _msg(banco, f, "aa11bb", "na_lixeira", "lixo", 0)
    _post(cli, f"{U}/mensagens/{mid}/restaurar")

    class Ponte:
        chamadas = []

        def lixeira(self, conta, ids):
            self.chamadas.append(ids)
            return {i: "ok" for i in ids}
    p = Ponte()
    c = conectar(banco)
    pr.processar(c, None, Orcamento(1.0, 10.0), p, "2026-10-16T12:00:00+00:00")
    c.close()
    assert p.chamadas == []


def test_parametros_novos_gravam_e_normalizam_as_palavras(cli):
    r = _put(cli, {"palavras_protegidas": ["Fatura", " BOLETO ", "fatura", ""], "dias_em_aberto": 10, "max_alertas_dia": 3})
    assert r.status_code == 200
    d = r.json()["dados"]
    assert d["palavras_protegidas"] == ["Fatura", "BOLETO"] and d["dias_em_aberto"] == 10 and d["max_alertas_dia"] == 3  # aparadas e sem repetir (caixa não conta); vazia some
    assert _put(cli, {"palavras_protegidas": []}).json()["dados"]["palavras_protegidas"] == []  # o dono pode esvaziar a lista


def test_palavras_protegidas_nao_aparecem_na_auditoria(cli, banco):
    _put(cli, {"palavras_protegidas": ["PALAVRA-SECRETA"]})
    assert "PALAVRA-SECRETA" not in " | ".join(_decisoes(banco)) and "email.palavras_protegidas" in " | ".join(_decisoes(banco))


def test_restaurar_nao_trava_o_laco_da_api(banco):
    import asyncio
    fonte = _Email()
    original = fonte.restaurar
    fonte.no_laco = None

    def restaurar(conta, ids):
        try:
            asyncio.get_running_loop()
            fonte.no_laco = True  # a chamada de rede bloqueante rodou dentro do laço de eventos
        except RuntimeError:
            fonte.no_laco = False
        return original(conta, ids)
    fonte.restaurar = restaurar
    cli = _cli(banco, fonte)
    f = _criar(cli); _patch(cli, f"{U}/fontes/{f}", {"estado": "sim"})
    mid = _msg(banco, f, "ab12cd", "na_lixeira", "lixo", 0, "Promo")
    assert _post(cli, f"{U}/mensagens/{mid}/restaurar").status_code == 200
    assert fonte.no_laco is False
