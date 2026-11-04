import datetime as dt

from gabi.cobrar.notas_importar import main
from gabi.db import conectar
from gabi.fontes.nibo import ErroNibo
from tests.cobrar.test_notas import CRED, nota


class NiboFalso:
    def __init__(self, notas, falha=False):
        self.notas, self.falha = notas, falha

    def agendamentos_a_receber(self):
        if self.falha:
            raise ErroNibo("GET /schedules/credit -> 500")
        return list(CRED.values())

    def nfse(self, desde):
        return iter(self.notas)

    def obter_arquivo(self, url):
        return b"%PDF-x"


def test_rodada_grava_notas_e_registra_a_rodada(tmp_path, capsys):
    banco = tmp_path / "g.db"
    assert main(banco, tmp_path / "notas", dt.date(2017, 1, 1), NiboFalso([nota()])) == 0
    con = conectar(banco)
    assert con.execute("select count(*) from nota_fiscal").fetchone()[0] == 1
    r = con.execute("select fonte, status, lidos, novos from rodada").fetchone()
    assert tuple(r) == ("notas-nibo", "ok", 1, 1) and "lidas=1 novas=1" in capsys.readouterr().out


def test_erro_do_nibo_vira_codigo_1_e_rodada_em_erro(tmp_path):
    banco = tmp_path / "g.db"
    assert main(banco, tmp_path / "notas", dt.date(2017, 1, 1), NiboFalso([nota()], falha=True)) == 1
    assert conectar(banco).execute("select status from rodada").fetchone()[0] == "erro"
