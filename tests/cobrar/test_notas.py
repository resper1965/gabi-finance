import json
from datetime import datetime, timezone

import pytest

from gabi.cobrar.notas import importar, normalizar
from gabi.db import conectar, migrar

AGORA = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
MIGR = __import__("pathlib").Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def nota(id_="n1", status=3, numero="123", valor=3900.0, pdf="pdf1", xml="xml1", sched="s1", **kw):
    return {"id": id_, "number": numero, "rpsNumber": "7", "rpsSeries": "1", "verificationCode": "ABC123", "serviceProviderDocumentNumber": "28811817000169",
            "authorizeDate": "2026-10-04T13:00:00Z", "createDate": "2026-10-03T10:00:00Z", "status": {"code": status, "description": "x"},
            "value": valor, "deductions": 0.0, "discounts": 0.0,
            "customer": {"cpfCnpj": "35594747000108", "name": "IONIC HEALTH TECHNOLOGIES S.A.", "email": "fin@x.com"},
            "stakeholder": {"id": "st1", "name": "IONIC HEALTH TECHNOLOGIES S.A."},
            "service": {"description": "CONTRATO MENSAL", "iss": {"value": 195.0}, "ir": None},
            "schedule": {"id": sched, "dueDate": "2026-10-15T00:00:00Z", "value": 3660.15},
            "pdfFileId": pdf, "pdfFileUrl": f"https://arquivos.nibo.com.br/download/{pdf}" if pdf else None,
            "xmlFileId": xml, "xmlFileUrl": f"https://arquivos.nibo.com.br/download/{xml}" if xml else None, "updateDate": "2026-10-04T14:00:00Z", **kw}


CRED = {"s1": {"scheduleId": "s1", "isPaid": False, "paidValue": 0.0, "openValue": 3660.15, "value": 3660.15, "dueDate": "2026-10-15T00:00:00Z"}}


class Baixador:
    def __init__(self, falha=()):
        self.urls, self.falha = [], set(falha)

    def __call__(self, url):
        self.urls.append(url)
        if url in self.falha:
            raise RuntimeError("falhou")
        return b"%PDF-" + url.encode() if "pdf" in url else b"<xml/>"


def test_normalizar_converte_centavos_status_e_datas():
    r = normalizar(nota(), CRED["s1"])
    assert (r["status"], r["valor_bruto_centavos"], r["valor_liquido_centavos"]) == ("autorizada", 390000, 366015)
    assert (r["emissao"], r["vencimento"], r["tomador_doc"], r["numero"]) == ("2026-10-04", "2026-10-15", "35594747000108", "123")
    assert json.loads(r["retencoes"])["iss"] == {"value": 195.0}
    assert normalizar(nota(status=-4), None)["status"] == "cancelada" and normalizar(nota(status=-1), None)["status"] == "negada"


def test_normalizar_status_desconhecido_levanta():
    with pytest.raises(ValueError):
        normalizar(nota(status=99), None)


def test_centavos_sem_erro_de_ponto_flutuante():
    assert normalizar(nota(valor=858.05), None)["valor_bruto_centavos"] == 85805 and normalizar(nota(valor=0.29), None)["valor_bruto_centavos"] == 29


def test_importar_grava_baixa_arquivos_e_e_idempotente(con, tmp_path):
    baixar = Baixador()
    r1 = importar(con, [nota()], CRED, baixar, tmp_path / "notas", AGORA)
    assert (r1.lidas, r1.novas, r1.alteradas, r1.arquivos, r1.falhas) == (1, 1, 0, 2, [])
    l = con.execute("select * from nota_fiscal").fetchone()
    assert (tmp_path / "notas" / l["pdf_arquivo"]).read_bytes().startswith(b"%PDF-") and (tmp_path / "notas" / l["xml_arquivo"]).exists()
    assert l["pdf_arquivo"].startswith("2026/") and ".." not in l["pdf_arquivo"]
    r2 = importar(con, [nota()], CRED, baixar, tmp_path / "notas", AGORA)
    assert (r2.novas, r2.alteradas, r2.arquivos) == (0, 0, 0) and len(baixar.urls) == 2  # nada baixado de novo
    assert con.execute("select count(*) from nota_fiscal").fetchone()[0] == 1


def test_importar_atualiza_quando_o_nibo_muda(con, tmp_path):
    importar(con, [nota()], CRED, Baixador(), tmp_path, AGORA)
    r = importar(con, [nota(status=-4, updateDate="2026-10-08T00:00:00Z")], {"s1": {**CRED["s1"], "isPaid": True, "paidValue": 3660.15}}, Baixador(), tmp_path, AGORA)
    l = con.execute("select status, nibo_pago, nibo_pago_centavos from nota_fiscal").fetchone()
    assert r.alteradas == 1 and tuple(l) == ("cancelada", 1, 366015)


def test_negada_nao_baixa_arquivo_e_nao_exige_credito(con, tmp_path):
    baixar = Baixador()
    r = importar(con, [nota(status=-1, pdf=None, xml=None, sched="s9")], {}, baixar, tmp_path, AGORA)
    assert r.novas == 1 and baixar.urls == [] and con.execute("select vencimento, pdf_arquivo from nota_fiscal").fetchone()[1] is None


def test_falha_de_um_arquivo_nao_aborta_e_e_reportada(con, tmp_path):
    ruim = "https://arquivos.nibo.com.br/download/pdf1"
    r = importar(con, [nota(), nota("n2", pdf="pdf2", xml="xml2", numero="124", sched="s2")], CRED, Baixador(falha={ruim}), tmp_path, AGORA)
    assert r.novas == 2 and len(r.falhas) == 1 and "123" in r.falhas[0]
    assert con.execute("select pdf_arquivo from nota_fiscal where id='n1'").fetchone()[0] is None
    r2 = importar(con, [nota(), nota("n2", pdf="pdf2", xml="xml2", numero="124", sched="s2")], CRED, Baixador(), tmp_path, AGORA)
    assert r2.falhas == [] and con.execute("select pdf_arquivo from nota_fiscal where id='n1'").fetchone()[0]  # a próxima rodada completa


def test_numero_estranho_nao_escapa_da_pasta(con, tmp_path):
    importar(con, [nota(numero="../../etc/x")], CRED, Baixador(), tmp_path / "notas", AGORA)
    l = con.execute("select pdf_arquivo from nota_fiscal").fetchone()[0]
    assert (tmp_path / "notas" / l).resolve().is_relative_to((tmp_path / "notas").resolve())
