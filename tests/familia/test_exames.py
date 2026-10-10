import datetime as dt

import pytest

from gabi.familia.exames import confirmar_laudo, extrair_marcadores, propor_exames, rejeitar_laudo
from gabi.familia.saude import abrir_saude, serie

CHAVE = bytes(range(32))
LAUDO = """LABORATÓRIO EXEMPLO
Paciente: Maria Açaí    Data da coleta: 10/07/2026
Colesterol total ............ 215 mg/dL    Valor de referência: 0 a 200 mg/dL
Glicose em jejum: 92 mg/dL (Ref.: 70 - 99)
Hemoglobina 13,5 g/dL
Observação: jejum de 12 horas
"""


def test_extrai_marcador_valor_unidade_e_faixa_quando_ha():
    ms = {m["marcador"]: m for m in extrair_marcadores(LAUDO)}
    assert ms["Colesterol total"]["valor"] == "215" and ms["Colesterol total"]["unidade"] == "mg/dL"
    assert (ms["Colesterol total"]["ref_min"], ms["Colesterol total"]["ref_max"]) == ("0", "200")
    assert ms["Glicose em jejum"]["valor"] == "92" and (ms["Glicose em jejum"]["ref_min"], ms["Glicose em jejum"]["ref_max"]) == ("70", "99")
    assert ms["Hemoglobina"]["valor"] == "13,5" and ms["Hemoglobina"]["ref_min"] is None
    assert "Observação" not in ms and "Paciente" not in ms


def test_data_da_coleta_vira_a_data_do_exame():
    assert {m["em"] for m in extrair_marcadores(LAUDO)} == {"2026-07-10"}


def test_propor_nao_registra_exame_e_confirmar_exige_a_pessoa(tmp_path):
    arq = tmp_path / "s.enc"
    with abrir_saude(arq, CHAVE) as s:
        n = propor_exames(s, 55, LAUDO, pessoa_sugerida="p2")
        assert n == 3 and s.con.execute("select count(*) from exame").fetchone()[0] == 0  # só proposta
        with pytest.raises(ValueError):
            confirmar_laudo(s, 55, "", "boss@x.com")
        assert confirmar_laudo(s, 55, "p2", "boss@x.com") == 3
        assert [p.valor for p in serie(s, "p2", "Colesterol total", "boss@x.com")] == ["215"]
        assert confirmar_laudo(s, 55, "p2", "boss@x.com") == 0  # idempotente: já confirmada


def test_exame_sem_confirmar_pessoa_nao_entra_e_rejeitar_descarta(tmp_path):
    arq = tmp_path / "s.enc"
    with abrir_saude(arq, CHAVE) as s:
        propor_exames(s, 56, LAUDO)
        assert rejeitar_laudo(s, 56) == 3
        assert confirmar_laudo(s, 56, "p1", "boss@x.com") == 0
        assert s.con.execute("select count(*) from exame").fetchone()[0] == 0


def test_propor_duas_vezes_nao_duplica(tmp_path):
    with abrir_saude(tmp_path / "s.enc", CHAVE) as s:
        propor_exames(s, 55, LAUDO)
        assert propor_exames(s, 55, LAUDO) == 0
