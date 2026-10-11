import pytest

from gabi.fontes.openrouter import ErroOpenRouter, OpenRouter

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


def test_custo_ausente_ou_invalido_vira_zero():
    for usage in ({}, None, {"cost": "x"}, {"cost": None}, {"cost": -1}):
        http, _ = _ok({"choices": [{"message": {"content": "oi"}}], "usage": usage})
        assert OpenRouter(CHAVE, "a", "b", http=http).completar("p", forte=False) == ("oi", 0.0)


def test_chave_nunca_aparece_no_erro():
    def http_erro(*a):
        return 401, {"error": {"message": f"bad key {CHAVE}"}}

    def http_explode(*a):
        raise RuntimeError(f"Bearer {CHAVE}")
    for http in (http_erro, http_explode, _ok({"choices": [], "echo": CHAVE})[0]):
        with pytest.raises(ErroOpenRouter) as e:
            OpenRouter(CHAVE, "a", "b", http=http).completar("p", forte=False)
        assert CHAVE not in str(e.value) and CHAVE not in repr(e.value) and e.value.__cause__ is None
    assert CHAVE not in repr(OpenRouter(CHAVE, "a", "b"))


def test_sem_chave_levanta_chave_ausente():
    with pytest.raises(ErroOpenRouter, match="chave ausente"):
        OpenRouter("", "a", "b", http=lambda *a: pytest.fail("rede")).completar("p", forte=False)
