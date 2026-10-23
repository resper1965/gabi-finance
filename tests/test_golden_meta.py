import json
import re
from pathlib import Path

import pytest

GOLDEN = Path(__file__).parent / "golden"
FUNCOES = {
    "finlib": {"norm", "num", "dono_tokens", "_w_natureza", "_w_aplica", "meses_atras", "_w_boleto", "_w_conferir",
               "_w_recorrentes", "_w_gastos", "_w_previsao", "_w_vazamentos"},
    "previstas": {"feriados", "dia_util", "forma"},
    "compromissos": {"vencimento_do_mes", "vencimento_util"},
    "extrator": {"pix_valido", "pix_valor", "achar_codigo", "achar_cnpj", "tipo_documento", "ler_comprovante_pix"},
    "emissores": {"chave_extrato", "generica", "chave_forte", "chave"},
    "planilha": {"_w_validar"},
}


def _carregar(modulo):
    return json.loads((GOLDEN / f"{modulo}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("modulo", sorted(FUNCOES))
def test_golden_cobre_toda_funcao_portada(modulo):
    assert {c["fn"] for c in _carregar(modulo)} == FUNCOES[modulo]


@pytest.mark.parametrize("modulo", sorted(FUNCOES))
def test_todo_caso_tem_saida_ou_excecao_esperada(modulo):
    for c in _carregar(modulo):
        assert ("saida" in c) != ("erro" in c), c
        if "erro" in c:  # exceção só onde o gabi-fin realmente levanta (regra de vencimento inválida)
            assert modulo == "compromissos" and c["erro"] == "ValueError", c


def test_golden_nao_contem_cpf_nem_segredo():
    texto = "".join((GOLDEN / f"{m}.json").read_text(encoding="utf-8") for m in FUNCOES)
    assert re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", texto) is None
    assert not re.search(r"sk[_-](live|test)|Bearer |/var/lib/gabi|/etc/gabi", texto)


def test_golden_e_sintetico_sem_caminho_de_producao():
    assert "inexistente" not in (GOLDEN / "finlib.json").read_text(encoding="utf-8")  # o desvio de REGRAS não vaza


@pytest.mark.skipif(not Path("/opt/gabi-fin/finlib.py").exists(), reason="gabi-fin não está nesta máquina")
def test_golden_atual_bate_com_o_gabi_fin(tmp_path, monkeypatch):
    """Se o gabi-fin mudar, os arquivos de referência precisam ser regenerados de propósito."""
    import tools.golden as g
    monkeypatch.setattr(g, "SAIDA", tmp_path)
    g.gerar()
    for m in FUNCOES:
        assert json.loads((tmp_path / f"{m}.json").read_text()) == _carregar(m), m
