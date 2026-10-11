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
    o = OpenRouter(CHAVE, "a", "b", http=http, relogio=r)
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
        assert e.value.__context__ is None or e.value.__suppress_context__
    assert CHAVE not in repr(OpenRouter(CHAVE, "a", "b"))


def test_sem_chave_levanta_chave_ausente():
    with pytest.raises(ErroOpenRouter, match="chave ausente"):
        OpenRouter("", "a", "b", http=lambda *a: pytest.fail("rede")).completar("p", forte=False)
