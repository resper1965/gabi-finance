import datetime as dt

import pytest

from gabi.dinheiro.modelo import Orcamento
from gabi.familia import marcadores as apelidos
from gabi.familia.exames import (confirmar_laudo, diferencas, extrair_marcadores, laudos_pendentes, propor_exames, rejeitar_laudo, reprocessar, versoes)
from gabi.familia.extrair import Laudo, extrair
from gabi.familia.saude import abrir_saude, marcadores, resumo_para_consulta, serie

CHAVE = bytes(range(32))


def _laudo(texto=None, **mudar):
    """Laudo pelas regras (sem modelo); `mudar` troca o valor de um marcador: {"Colesterol total": "180"}."""
    l = extrair(texto or LAUDO, None, Orcamento(1, 10))
    return Laudo(l.paciente, l.laboratorio, l.data, [{**m, "valor": mudar.get(m["marcador"], m["valor"])} for m in l.marcadores], l.origem)
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
        n = propor_exames(s, 55, _laudo(), pessoa_sugerida="p2")
        assert n == 3 and s.con.execute("select count(*) from exame").fetchone()[0] == 0  # só proposta
        with pytest.raises(ValueError):
            confirmar_laudo(s, 55, "", "boss@x.com")
        assert confirmar_laudo(s, 55, "p2", "boss@x.com") == 3
        assert [p.valor for p in serie(s, "p2", "Colesterol total", "boss@x.com")] == ["215"]
        assert confirmar_laudo(s, 55, "p2", "boss@x.com") == 0  # idempotente: já confirmada


def test_exame_sem_confirmar_pessoa_nao_entra_e_rejeitar_descarta(tmp_path):
    arq = tmp_path / "s.enc"
    with abrir_saude(arq, CHAVE) as s:
        propor_exames(s, 56, _laudo())
        assert rejeitar_laudo(s, 56) == 3
        assert confirmar_laudo(s, 56, "p1", "boss@x.com") == 0
        assert s.con.execute("select count(*) from exame").fetchone()[0] == 0


def test_propor_duas_vezes_nao_duplica(tmp_path):
    with abrir_saude(tmp_path / "s.enc", CHAVE) as s:
        propor_exames(s, 55, _laudo())
        assert propor_exames(s, 55, _laudo()) == 0


def test_reprocessar_cria_versao_e_mantem_a_antiga(tmp_path):
    with abrir_saude(tmp_path / "s.enc", CHAVE) as s:
        propor_exames(s, 55, _laudo(), "p2")
        r = reprocessar(s, 55, _laudo(**{"Colesterol total": "180"}), "boss@x.com")
        assert r == {"versao": 2, "novos": 0, "iguais": 2, "diferentes": 1}
        vs = versoes(s, 55)
        assert [v["versao"] for v in vs] == [1, 2]
        assert {m["valor"] for m in vs[0]["marcadores"] if m["marcador"] == "Colesterol total"} == {"215"}
        assert s.con.execute("select count(*) from proposta_exame where paperless_id=55 and versao=1").fetchone()[0] == 3


def test_reprocessar_duas_vezes_nao_duplica_no_historico(tmp_path):
    with abrir_saude(tmp_path / "s.enc", CHAVE) as s:
        propor_exames(s, 55, _laudo(), "p2")
        confirmar_laudo(s, 55, "p2", "boss@x.com")
        reprocessar(s, 55, _laudo(**{"Colesterol total": "180"}), "boss@x.com")
        r = reprocessar(s, 55, _laudo(**{"Colesterol total": "180"}), "boss@x.com")
        assert r["versao"] == 2 and r["diferentes"] == 0
        assert [p.valor for p in serie(s, "p2", "Colesterol total", "boss@x.com")] == ["180"]
        assert s.con.execute("select count(*) from exame where paperless_id=55").fetchone()[0] == 6  # 3 de cada versão, nada a mais


def test_serie_mostra_so_a_versao_atual(tmp_path):
    with abrir_saude(tmp_path / "s.enc", CHAVE) as s:
        propor_exames(s, 55, _laudo(), "p2")
        confirmar_laudo(s, 55, "p2", "boss@x.com")
        reprocessar(s, 55, _laudo(**{"Colesterol total": "180"}), "boss@x.com")
        assert [(p.em, p.valor) for p in serie(s, "p2", "Colesterol total", "boss@x.com")] == [(dt.date(2026, 7, 10), "180")]
        assert [m["valor"] for m in marcadores(s, "p2", "boss@x.com") if m["marcador"] == "Colesterol total"] == ["180"]
        assert "180" in resumo_para_consulta(s, "p2", "boss@x.com") and "215" not in resumo_para_consulta(s, "p2", "boss@x.com")


def test_reprocessar_documento_confirmado_mantem_o_dono(tmp_path):
    with abrir_saude(tmp_path / "s.enc", CHAVE) as s:
        propor_exames(s, 55, _laudo(), "p2")
        confirmar_laudo(s, 55, "p2", "boss@x.com")
        reprocessar(s, 55, _laudo(**{"Glicose em jejum": "95"}), "outro@x.com")
        r = s.con.execute("select pessoa_id, confirmado_por, versao from exame where paperless_id=55 and versao=2 and marcador='Glicose em jejum'").fetchone()
        assert tuple(r) == ("p2", "outro@x.com", 2)
        assert laudos_pendentes(s) == []  # a versão nova já entrou: nada a confirmar de novo


def test_reprocessar_documento_nao_confirmado_fica_pendente_so_a_versao_nova(tmp_path):
    with abrir_saude(tmp_path / "s.enc", CHAVE) as s:
        propor_exames(s, 55, _laudo(), "p2")
        reprocessar(s, 55, _laudo(**{"Colesterol total": "180"}), "boss@x.com")
        (l,) = laudos_pendentes(s)
        assert l["versao"] == 2 and l["pessoa_sugerida"] == "p2" and len(l["marcadores"]) == 3
        assert confirmar_laudo(s, 55, "p2", "boss@x.com") == 3
        assert s.con.execute("select count(*) from exame").fetchone()[0] == 3


def test_comparar_versoes_lista_diferencas(tmp_path):
    with abrir_saude(tmp_path / "s.enc", CHAVE) as s:
        propor_exames(s, 55, _laudo())
        reprocessar(s, 55, _laudo(**{"Colesterol total": "180"}), "boss@x.com")
        assert diferencas(s, 55, 1, 2) == [{"marcador": "Colesterol total", "em": "2026-07-10", "antes": "215", "depois": "180"}]


def test_marcador_passa_pelo_apelido_ao_propor(tmp_path):
    with abrir_saude(tmp_path / "s.enc", CHAVE) as s:
        apelidos.definir_apelido(s, "Glicose em jejum", "Glicemia")
        propor_exames(s, 55, _laudo())
        assert "Glicemia" in {r[0] for r in s.con.execute("select marcador from proposta_exame")}


def test_qualitativo_fica_fora_da_serie(tmp_path):
    laudo = Laudo(None, None, "2026-05-03", [{"marcador": "HIV", "valor": "Não reagente", "unidade": None, "em": "2026-05-03", "ref_min": None, "ref_max": None,
                                              "qualitativo": True, "observacao": None}], "modelo")
    with abrir_saude(tmp_path / "s.enc", CHAVE) as s:
        propor_exames(s, 70, laudo, "p1")
        confirmar_laudo(s, 70, "p1", "boss@x.com")
        assert serie(s, "p1", "HIV", "boss@x.com") == []
        assert [(m["valor"], m["qualitativo"], m["fora_da_faixa"]) for m in marcadores(s, "p1", "boss@x.com")] == [("Não reagente", True, False)]
