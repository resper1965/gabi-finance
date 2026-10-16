import datetime as dt

from gabi.familia import marcadores
from gabi.familia.saude import abrir_saude, registrar_exame

CHAVE = bytes(range(32))
D = dt.date


def _cofre(tmp_path):
    return abrir_saude(tmp_path / "s.enc", CHAVE)


def test_variacoes_viram_um_marcador(tmp_path):
    with _cofre(tmp_path) as s:
        marcadores.definir_apelido(s, "Col. total", "Colesterol total")
        assert {marcadores.normalizar(s, n) for n in ("Colesterol Total", "COLESTEROL TOTAL", "Col. total", "colesterol  total:")} == {"Colesterol total"}


def test_sem_apelido_nao_junta_marcadores_diferentes(tmp_path):
    with _cofre(tmp_path) as s:
        assert marcadores.normalizar(s, "HDL") == "HDL" and marcadores.normalizar(s, "LDL") == "LDL"
        assert marcadores.normalizar(s, "Colesterol HDL") != marcadores.normalizar(s, "Colesterol LDL")
        assert marcadores.normalizar(s, "Glicose em jejum") == "Glicose em jejum"


def test_reaplicar_atualiza_exames_e_propostas(tmp_path):
    with _cofre(tmp_path) as s:
        registrar_exame(s, "p1", "Col. total", "190", "mg/dL", D(2026, 1, 1), None, 1, "boss")
        s.con.execute("insert into proposta_exame(paperless_id, marcador, valor, criado_em) values (1,'Col total','190','x')")
        marcadores.definir_apelido(s, "col total", "Colesterol total")
        assert marcadores.reaplicar(s) == 2
        assert s.con.execute("select marcador from exame").fetchone()[0] == "Colesterol total"
        assert s.con.execute("select marcador from proposta_exame").fetchone()[0] == "Colesterol total"


def test_reaplicar_idempotente(tmp_path):
    with _cofre(tmp_path) as s:
        registrar_exame(s, "p1", "Col. total", "190", "mg/dL", D(2026, 1, 1), None, 1, "boss")
        marcadores.definir_apelido(s, "Col. total", "Colesterol total")
        assert marcadores.reaplicar(s) == 1
        assert marcadores.reaplicar(s) == 0


def test_sugestoes_acham_grafias_parecidas_e_nao_hdl_com_ldl(tmp_path):
    with _cofre(tmp_path) as s:
        for m in ("Colesterol total", "Colesterol-total", "Colesterol HDL", "Colesterol LDL", "Hemoglobina glicada", "Hemoglobina glicosilada"):
            registrar_exame(s, "p1", m, "1", "x", D(2026, 1, 1), None, 1, "boss")
        sug = marcadores.sugestoes(s)
        assert "Colesterol HDL" not in sug and "Colesterol LDL" not in sug
        assert {"Hemoglobina glicada", "Hemoglobina glicosilada"} <= set(sug)
