import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.correio.__main__ import main
from gabi.db import conectar, migrar
from gabi.escuta import __main__ as escuta_prog
from gabi.fontes.google_email import ResultadoEmail
from gabi.fontes.google_oauth import ErroGoogleOAuth

MIGR = Path(__file__).parent.parent.parent / "migrations"
AGORA = dt.datetime(2026, 10, 12, 12, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def banco(tmp_path):
    p = tmp_path / "t.db"
    c = conectar(p)
    migrar(c, MIGR)
    c.close()
    return p


def _fonte(banco, conta, estado="sim", lixeira=1):
    c = conectar(banco)
    fid = c.execute("insert into email_fonte(conta, provedor, estado, lixeira) values (?, 'google', ?, ?)", (conta, estado, lixeira)).lastrowid
    c.close()
    return fid


def _m(ext, assunto="Oferta SEGREDO-ASSUNTO", de="promo@loja.com", lista=True):
    return {"externo_id": ext, "thread_id": ext + "t", "remetente": de, "assunto": assunto, "recebida_em": "2026-10-12T10:00:00+00:00", "trecho": "SEGREDO-TRECHO", "lista": lista}


class Modelo:
    def __init__(self, resposta=None):
        self.resposta = resposta or json.dumps({"classe": "lixo", "prioridade": 0, "motivo": "promoção", "confianca": 0.95})

    def completar(self, prompt, *, forte):
        return self.resposta, 0.001


class Ponte:
    def __init__(self, enviados=(), erro_enviados=None):
        self.enviados, self.erro_enviados, self.lixeiras, self.consultas = list(enviados), erro_enviados, [], 0

    def enviados_recentes(self, conta, dias):
        self.consultas += 1
        if self.erro_enviados:
            raise self.erro_enviados
        return self.enviados

    def lixeira(self, conta, ids):
        self.lixeiras.append((conta, list(ids)))
        return {i: "ok" for i in ids}


def _listar(*msgs):
    return lambda conta, h, j: ResultadoEmail(list(msgs), "H1", False)


def _estados(banco):
    c = conectar(banco)
    r = {x["externo_id"]: x["estado"] for x in c.execute("select externo_id, estado from email_msg")}
    c.close()
    return r


def test_main_sincroniza_processa_e_imprime_so_contagens(banco, capsys):
    _fonte(banco, "a@x.com")
    ponte = Ponte()
    rc = main(banco, listar=_listar(_m("a1"), _m("b2")), ponte=ponte, cliente=Modelo(), agora=AGORA)
    saida = capsys.readouterr()
    assert rc == 0 and "novos=2" in saida.out and "lixeira=2" in saida.out
    assert "SEGREDO" not in saida.out + saida.err and "loja.com" not in saida.out + saida.err
    assert _estados(banco) == {"a1": "na_lixeira", "b2": "na_lixeira"}
    assert len(ponte.lixeiras) == 1 and ponte.lixeiras[0][0] == "a@x.com" and sorted(ponte.lixeiras[0][1]) == ["a1", "b2"]


def test_main_sem_fonte_sim_sai_0_e_nao_consulta_nada(banco, capsys):
    _fonte(banco, "a@x.com", estado="a_decidir")
    assert main(banco, listar=lambda *a: pytest.fail("não deveria listar"), ponte=Ponte(), cliente=Modelo(), agora=AGORA) == 0
    assert "fontes=0" in capsys.readouterr().out


def test_main_todas_falham_sai_1(banco, capsys):
    _fonte(banco, "a@x.com"); _fonte(banco, "b@x.com")

    def listar(*a):
        raise ErroGoogleOAuth("messages.list -> 500")
    assert main(banco, listar=listar, ponte=Ponte(), cliente=Modelo(), agora=AGORA) == 1
    assert "falhou" in capsys.readouterr().err


def test_main_conta_nao_autorizada_nao_conta_como_falha_geral(banco):
    _fonte(banco, "a@x.com"); _fonte(banco, "b@x.com")

    def listar(conta, *a):
        raise ErroGoogleOAuth(f"conta não autorizada: {conta}")
    assert main(banco, listar=listar, ponte=Ponte(), cliente=Modelo(), agora=AGORA) == 0


def test_main_uma_ok_e_outra_falha_sai_0(banco):
    _fonte(banco, "ruim@x.com"); _fonte(banco, "boa@x.com")

    def listar(conta, *a):
        if conta == "ruim@x.com":
            raise ErroGoogleOAuth("messages.list -> 500")
        return ResultadoEmail([], "H", False)
    assert main(banco, listar=listar, ponte=Ponte(), cliente=Modelo(), agora=AGORA) == 0


def _rodadas(banco):
    c = conectar(banco)
    r = [tuple(x) for x in c.execute("select fonte, status, lidos, novos from rodada where fonte='correio' order by id")]
    c.close()
    return r


def test_main_registra_a_rodada_correio_para_o_frescor(banco):
    _fonte(banco, "a@x.com")
    main(banco, listar=_listar(_m("a1"), _m("b2")), ponte=Ponte(), cliente=Modelo(), agora=AGORA)
    assert _rodadas(banco) == [("correio", "ok", 2, 2)]


def test_main_todas_as_fontes_falhando_grava_rodada_em_erro_mesmo_saindo_0(banco):
    _fonte(banco, "a@x.com")

    def listar(conta, *a):
        raise ErroGoogleOAuth(f"conta não autorizada: {conta}")
    assert main(banco, listar=listar, ponte=Ponte(), cliente=Modelo(), agora=AGORA) == 0
    assert _rodadas(banco) == [("correio", "erro", 0, 0)]


def test_main_sem_fonte_liberada_grava_rodada_ok(banco):
    main(banco, listar=lambda *a: pytest.fail("não deveria listar"), ponte=Ponte(), cliente=Modelo(), agora=AGORA)
    assert _rodadas(banco) == [("correio", "ok", 0, 0)]


def test_main_sem_socket_sai_2(banco, monkeypatch, capsys):
    monkeypatch.delenv("GABI_FONTES_SOCKET", raising=False)
    assert main(banco, agora=AGORA) == 2 and "GABI_FONTES_SOCKET" in capsys.readouterr().err


def test_main_confere_os_respondidos_antes_de_mover_e_protege_quem_o_dono_respondeu(banco):
    _fonte(banco, "a@x.com")
    ponte = Ponte(enviados=["amigo@x.com"])
    main(banco, listar=_listar(_m("a1", de="Amigo <amigo@x.com>"), _m("b2")), ponte=ponte, cliente=Modelo(), agora=AGORA)
    assert _estados(banco) == {"a1": "classificada", "b2": "na_lixeira"} and ponte.consultas == 1  # só na carga/recarga, não a cada rodada


def test_main_se_a_conferencia_dos_respondidos_falha_nada_e_movido(banco, capsys):
    _fonte(banco, "a@x.com")
    ponte = Ponte(erro_enviados=ErroGoogleOAuth("serviço de fontes indisponível"))
    rc = main(banco, listar=_listar(_m("a1")), ponte=ponte, cliente=Modelo(), agora=AGORA)
    assert rc == 0 and ponte.lixeiras == [] and _estados(banco) == {"a1": "classificada"}
    # na rodada seguinte (ponte voltou) a conferência é refeita e só então o que chegar pode ir
    ponte.erro_enviados = None
    main(banco, listar=_listar(_m("c3")), ponte=ponte, cliente=Modelo(), agora=AGORA + dt.timedelta(minutes=15))
    assert _estados(banco)["c3"] == "na_lixeira" and ponte.consultas == 2


def test_main_sem_modelo_nada_vai_a_lixeira(banco, capsys):
    _fonte(banco, "a@x.com")
    ponte = Ponte()
    rc = main(banco, listar=_listar(_m("a1")), ponte=ponte, cliente=None, agora=AGORA)
    assert rc == 0 and ponte.lixeiras == [] and _estados(banco) == {"a1": "nova"} and "sem_modelo=1" in capsys.readouterr().out


def test_main_purga_trechos_antigos_e_nunca_imprime_texto(banco, capsys):
    _fonte(banco, "a@x.com")
    velha = dict(_m("velha"), recebida_em="2026-09-01T10:00:00+00:00")
    main(banco, listar=_listar(velha), ponte=Ponte(), cliente=Modelo(), agora=AGORA)
    c = conectar(banco)
    assert c.execute("select trecho from email_msg where externo_id='velha'").fetchone()[0] is None
    assert "SEGREDO" not in capsys.readouterr().out


def _linhas_custo(banco):
    c = conectar(banco)
    r = [(x["tarefa"], round(x["custo_usd"], 4)) for x in c.execute("select tarefa, custo_usd from custo_modelo order by id")]
    c.close()
    return r


def test_modelo_com_custo_grava_a_tarefa_pedida_e_o_padrao_segue_escuta(banco):
    w = escuta_prog.ModeloComCusto(Modelo(), banco)
    w.completar("p", forte=False)
    w.fechar()
    w2 = escuta_prog.ModeloComCusto(Modelo(), banco, tarefa="email")
    w2.completar("p", forte=False)
    w2.fechar()
    assert _linhas_custo(banco) == [("escuta", 0.001), ("email", 0.001)]


def test_modelo_com_custo_falha_depois_do_envio_grava_tarefa_falha(banco):
    class Quebra:
        def completar(self, prompt, *, forte):
            raise RuntimeError("timeout")
    w = escuta_prog.ModeloComCusto(Quebra(), banco, tarefa="email")
    with pytest.raises(RuntimeError):
        w.completar("p", forte=False)
    w.fechar()
    assert [t for t, _ in _linhas_custo(banco)] == ["email-falha"]
