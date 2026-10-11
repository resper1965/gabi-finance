import pytest

from gabi.fontes.openrouter import ErroOpenRouter, Limites, OpenRouter

CHAVE = "sk-or-SEGREDO123"


def _ok(corpo):
    chamadas = []

    def http(metodo, url, corpo_req=None, cab=None):
        chamadas.append((metodo, url, corpo_req, cab))
        return 200, corpo
    return http, chamadas


def test_completar_devolve_texto_e_custo():
    http, chamadas = _ok({"choices": [{"message": {"content": "oi"}}], "usage": {"cost": 0.0012}})
    o = OpenRouter(CHAVE, "rapido/m", "forte/m", http=http)
    assert o.completar("p", forte=False) == ("oi", 0.0012)
    assert o.completar("p", forte=True)[0] == "oi"
    assert [c[2]["model"] for c in chamadas] == ["rapido/m", "forte/m"]
    assert chamadas[0][1] == "https://openrouter.ai/api/v1/chat/completions"
    assert chamadas[0][3]["Authorization"] == f"Bearer {CHAVE}"


def _com_usage(usage):
    return _ok({"choices": [{"message": {"content": "oi"}}], "usage": usage})[0]


def test_custo_ausente_com_tokens_estima_pessimista():
    o = OpenRouter(CHAVE, "a", "b", http=_com_usage({"prompt_tokens": 1_000_000, "completion_tokens": 100_000}))
    assert o.completar("p", forte=False) == ("oi", pytest.approx(3.0 + 1.5))


def test_custo_ausente_sem_tokens_usa_valor_fixo():
    for usage in ({}, None):
        assert OpenRouter(CHAVE, "a", "b", http=_com_usage(usage)).completar("p", forte=False)[1] == 0.05


def test_custo_negativo_nan_ou_texto_nunca_vira_zero():
    for c in (-1, float("nan"), "x", None, True, 0, float("inf")):
        o = OpenRouter(CHAVE, "a", "b", http=_com_usage({"cost": c, "prompt_tokens": 1000, "completion_tokens": 1000}))
        assert o.completar("p", forte=False)[1] == pytest.approx(0.003 + 0.015)


def test_precos_e_custo_padrao_configuraveis():
    lim = Limites(preco_entrada_usd_m=1.0, preco_saida_usd_m=2.0, custo_padrao_usd=0.5)
    o = OpenRouter(CHAVE, "a", "b", http=_com_usage({"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}), limites=lim)
    assert o.completar("p", forte=False)[1] == pytest.approx(3.0)
    assert OpenRouter(CHAVE, "a", "b", http=_com_usage({}), limites=lim).completar("p", forte=False)[1] == 0.5


def test_limites_do_ambiente():
    assert Limites.do_ambiente({}) == Limites()
    assert Limites().teto_dia_usd == 3.0 and Limites().max_prompt_chars == 50000 and Limites().max_chamadas_min == 30
    assert (Limites().max_tokens_rapido, Limites().max_tokens_forte) == (1024, 2048)
    assert (Limites().preco_entrada_usd_m, Limites().preco_saida_usd_m, Limites().custo_padrao_usd) == (3.0, 15.0, 0.05)
    l = Limites.do_ambiente({"OPENROUTER_TETO_DIA_USD": "1.5", "OPENROUTER_MAX_CHAMADAS_MIN": "2", "OPENROUTER_MAX_TOKENS_FAST": "7",
                             "OPENROUTER_PRECO_ENTRADA_USD_M": "lixo"})
    assert (l.teto_dia_usd, l.max_chamadas_min, l.max_tokens_rapido, l.preco_entrada_usd_m) == (1.5, 2, 7, 3.0)


def test_prompt_grande_demais_antes_da_rede():
    o = OpenRouter(CHAVE, "a", "b", http=lambda *a: pytest.fail("rede"), limites=Limites(max_prompt_chars=10))
    with pytest.raises(ErroOpenRouter, match="^prompt grande demais$"):
        o.completar("x" * 11, forte=False)


def test_max_tokens_vai_no_corpo():
    http, chamadas = _ok({"choices": [{"message": {"content": "oi"}}], "usage": {"cost": 0.01}})
    o = OpenRouter(CHAVE, "a", "b", http=http)
    o.completar("p", forte=False)
    o.completar("p", forte=True)
    assert [c[2]["max_tokens"] for c in chamadas] == [1024, 2048]


class Relogio:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def test_teto_diario_bloqueia_e_zera_no_dia_seguinte_em_brt():
    from datetime import datetime, timezone
    r = Relogio(datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc).timestamp())  # 09h BRT dia 11
    http, chamadas = _ok({"choices": [{"message": {"content": "oi"}}], "usage": {"cost": 1.0}})
    o = OpenRouter(CHAVE, "a", "b", http=http, limites=Limites(teto_dia_usd=2.0, max_chamadas_min=1000), relogio=r)
    o.completar("p", forte=False)
    o.completar("p", forte=False)  # soma chega a 2.0
    with pytest.raises(ErroOpenRouter, match="^teto diário$"):
        o.completar("p", forte=False)
    assert len(chamadas) == 2
    r.t = datetime(2026, 10, 12, 2, 30, tzinfo=timezone.utc).timestamp()  # 23h30 BRT, ainda dia 11
    with pytest.raises(ErroOpenRouter, match="teto diário"):
        o.completar("p", forte=False)
    r.t = datetime(2026, 10, 12, 3, 30, tzinfo=timezone.utc).timestamp()  # 00h30 BRT dia 12
    o.completar("p", forte=False)
    assert len(chamadas) == 3


def test_limite_por_minuto_bloqueia_a_31a_e_libera_depois():
    r = Relogio(1_000_000.0)
    http, chamadas = _ok({"choices": [{"message": {"content": "oi"}}], "usage": {"cost": 0.0001}})
    o = OpenRouter(CHAVE, "a", "b", http=http, relogio=r, monotonico=r)
    for _ in range(30):
        o.completar("p", forte=False)
    with pytest.raises(ErroOpenRouter, match="^muitas chamadas$"):
        o.completar("p", forte=False)
    assert len(chamadas) == 30
    r.t += 61
    o.completar("p", forte=False)
    assert len(chamadas) == 31


def test_chave_nunca_aparece_no_erro():
    def http_erro(*a):
        return 401, {"error": {"message": f"bad key {CHAVE}"}}

    def http_explode(*a):
        raise RuntimeError(f"Bearer {CHAVE}")
    for http in (http_erro, http_explode, _ok({"choices": [], "echo": CHAVE})[0]):
        with pytest.raises(ErroOpenRouter) as e:
            OpenRouter(CHAVE, "a", "b", http=http).completar("p", forte=False)
        assert CHAVE not in str(e.value) and CHAVE not in repr(e.value) and e.value.__cause__ is None
        assert e.value.__context__ is None
    assert CHAVE not in repr(OpenRouter(CHAVE, "a", "b"))


def test_sem_chave_levanta_chave_ausente():
    with pytest.raises(ErroOpenRouter, match="chave ausente"):
        OpenRouter("", "a", "b", http=lambda *a: pytest.fail("rede")).completar("p", forte=False)


def test_custo_com_prompt_tokens_sem_completion_estima_saida_no_max_tokens():
    o = OpenRouter(CHAVE, "a", "b", http=_com_usage({"prompt_tokens": 1_000_000}), limites=Limites(max_tokens_rapido=1_000_000, teto_dia_usd=100.0))
    assert o.completar("p", forte=False)[1] == pytest.approx(3.0 + 15.0)


def _bom(cost=0.01):
    return _ok({"choices": [{"message": {"content": "oi"}}], "usage": {"cost": cost}})[0]


def test_sucesso_troca_a_reserva_pelo_custo_real():
    o = OpenRouter(CHAVE, "a", "b", http=_bom(0.01))
    o.completar("p", forte=False)
    assert o._gasto == pytest.approx(0.01)


def test_200_sem_conteudo_mantem_a_reserva():
    o = OpenRouter(CHAVE, "a", "b", http=_ok({"choices": [{"message": {"content": None}}], "usage": {"cost": 0.5}})[0])
    with pytest.raises(ErroOpenRouter):
        o.completar("p", forte=False)
    assert o._gasto >= 0.05


def test_timeout_e_erro_http_mantem_a_reserva():
    def timeout(*a):
        raise TimeoutError()
    o = OpenRouter(CHAVE, "a", "b", http=timeout)
    with pytest.raises(ErroOpenRouter):
        o.completar("p", forte=False)
    assert o._gasto >= 0.05
    o2 = OpenRouter(CHAVE, "a", "b", http=lambda *a: (500, {}))
    with pytest.raises(ErroOpenRouter):
        o2.completar("p", forte=False)
    assert o2._gasto >= 0.05


def test_recusa_antes_da_rede_nao_cobra():
    o = OpenRouter(CHAVE, "a", "b", http=lambda *a: pytest.fail("rede"), limites=Limites(max_prompt_chars=3))
    with pytest.raises(ErroOpenRouter):
        o.completar("xxxx", forte=False)
    o = OpenRouter(CHAVE, "a", "b", http=lambda *a: pytest.fail("rede"), limites=Limites(teto_dia_usd=0.01))
    with pytest.raises(ErroOpenRouter, match="teto diário"):
        o.completar("p", forte=False)
    assert o._gasto == 0.0


def test_retentativas_de_chamadas_cobradas_que_falham_estouram_o_teto():
    o = OpenRouter(CHAVE, "a", "b", http=lambda *a: (200, {"choices": []}), limites=Limites(teto_dia_usd=0.12, max_chamadas_min=1000))
    erros = []
    for _ in range(5):
        try:
            o.completar("p", forte=False)
        except ErroOpenRouter as e:
            erros.append(str(e))
    assert "teto diário" in erros and erros.count("teto diário") >= 2


def test_chamadas_paralelas_nao_estouram_o_teto():
    import threading
    solta, dentro = threading.Event(), threading.Semaphore(0)

    def http(*a):
        dentro.release()
        solta.wait(5)
        return 200, {"choices": [{"message": {"content": "oi"}}], "usage": {"cost": 0.06}}
    o = OpenRouter(CHAVE, "a", "b", http=http, limites=Limites(teto_dia_usd=0.12))  # cabe uma reserva (0.05), a segunda passa de 0.12? 0.10<=0.12: cabem duas
    res = []

    def chamar():
        try:
            o.completar("p", forte=False)
            res.append("ok")
        except ErroOpenRouter as e:
            res.append(str(e))
    ts = [threading.Thread(target=chamar) for _ in range(4)]
    for t in ts:
        t.start()
    dentro.acquire(timeout=5)
    dentro.acquire(timeout=5)
    import time
    time.sleep(0.2)
    solta.set()
    for t in ts:
        t.join()
    assert res.count("ok") == 2 and res.count("teto diário") == 2  # as outras duas foram recusadas com as primeiras ainda em voo
    assert o._gasto <= 0.12 + 1e-9


def test_teto_zero_bloqueia_tudo():
    for lim in (Limites.do_ambiente({"OPENROUTER_TETO_DIA_USD": "0"}), Limites.do_ambiente({"OPENROUTER_MAX_CHAMADAS_MIN": "0"})):
        o = OpenRouter(CHAVE, "a", "b", http=lambda *a: pytest.fail("rede"), limites=lim)
        with pytest.raises(ErroOpenRouter):
            o.completar("p", forte=False)
    for ruim in ("-1", "nan", "inf", "x"):
        assert Limites.do_ambiente({"OPENROUTER_TETO_DIA_USD": ruim, "OPENROUTER_MAX_CHAMADAS_MIN": ruim}) == Limites()
    assert Limites.do_ambiente({"OPENROUTER_MAX_TOKENS_FAST": "0"}).max_tokens_rapido == 1024  # outras seguem validando


def test_janela_por_minuto_usa_relogio_monotonico():
    mono, parede = Relogio(100.0), Relogio(1_000_000.0)
    o = OpenRouter(CHAVE, "a", "b", http=_bom(0.0001), relogio=parede, monotonico=mono, limites=Limites(max_chamadas_min=1))
    o.completar("p", forte=False)
    parede.t -= 3600  # relógio de parede voltou: não pode liberar a janela
    with pytest.raises(ErroOpenRouter, match="muitas chamadas"):
        o.completar("p", forte=False)
    mono.t += 61
    o.completar("p", forte=False)
