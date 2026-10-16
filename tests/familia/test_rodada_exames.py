import json
import sqlite3
from pathlib import Path

import pytest

from gabi.dinheiro.modelo import Orcamento
from gabi.db import conectar, migrar
from gabi.familia import __main__ as programa
from gabi.familia import rodada_exames
from gabi.familia.rodada_exames import dono_proposto, rodar
from gabi.familia.saude import abrir_saude
from gabi.fontes.paperless import Paperless
from tests.cobrar.paperless_falso import PaperlessFalso

CHAVE = bytes(range(32))
AGORA = "2026-10-16T12:00:00+00:00"
LAUDO = """LABORATÓRIO EXEMPLO
Paciente: Maria Açaí    Data da coleta: 10/07/2026
Colesterol total ............ 215 mg/dL    Valor de referência: 0 a 200 mg/dL
Glicose em jejum: 92 mg/dL (Ref.: 70 - 99)
"""
TABELA = "Paciente: Bia Souza\nData da coleta: 03/05/2026\n| TSH | 2,5 | 0,4 a 4,0 |\n"


class Modelo:
    def __init__(self, resposta="{}"):
        self.resposta, self.prompts = resposta, []

    def completar(self, prompt, *, forte):
        self.prompts.append(prompt)
        return self.resposta, 0.01


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, Path(__file__).parent.parent.parent / "migrations")
    c.execute("insert into pessoa(id, nome) values ('p-maria', 'Maria Açaí'), ('p-bia', 'Bia Souza'), ('p-ric', 'Ricardo')")
    return c


def _sistema(docs, tmp_path):
    srv = PaperlessFalso(docs=docs, tags={"gabi:saude-exame": 1, "entrada-email": 2, "gabi:nao-exame": 3})
    return Paperless("http://p", "tok", http=srv), srv


def _doc(i, texto, tags=(1,), titulo="laudo"):
    return {"id": i, "title": titulo, "content": texto, "tags": list(tags)}


def _rodar(con, tmp_path, paperless, modelo=None, orc=None):
    return rodar(con, lambda: abrir_saude(tmp_path / "s.enc", CHAVE), paperless, modelo, orc or Orcamento(1, 10), AGORA)


def _propostas(tmp_path):
    with abrir_saude(tmp_path / "s.enc", CHAVE) as s:
        return [dict(r) for r in s.con.execute("select * from proposta_exame order by id")]


def test_documento_novo_vira_proposta_e_exame_doc_extraido(con, tmp_path):
    p, _ = _sistema([_doc(10, LAUDO)], tmp_path)
    r = _rodar(con, tmp_path, p)
    assert (r["novos"], r["extraidos"], r["falhos"]) == (1, 1, 0)
    ps = _propostas(tmp_path)
    assert {x["marcador"] for x in ps} == {"Colesterol total", "Glicose em jejum"} and {x["pessoa_sugerida"] for x in ps} == {"p-maria"}
    d = con.execute("select * from exame_doc where paperless_id=10").fetchone()
    assert (d["estado"], d["versao"], d["motivo"]) == ("extraido", 1, None)
    with abrir_saude(tmp_path / "s.enc", CHAVE) as s:  # nada entrou no histórico: só proposta
        assert s.con.execute("select count(*) from exame").fetchone()[0] == 0


def test_pdf_sem_texto_vira_falhou_com_motivo_e_o_lote_segue(con, tmp_path):
    p, _ = _sistema([_doc(10, ""), _doc(11, LAUDO)], tmp_path)
    r = _rodar(con, tmp_path, p)
    assert (r["novos"], r["extraidos"], r["falhos"]) == (2, 1, 1)
    d = con.execute("select estado, motivo from exame_doc where paperless_id=10").fetchone()
    assert (d["estado"], d["motivo"]) == ("falhou", "sem texto legível")
    assert con.execute("select estado from exame_doc where paperless_id=11").fetchone()[0] == "extraido"


def test_erro_inesperado_num_documento_nao_derruba_o_lote(con, tmp_path, monkeypatch):
    p, _ = _sistema([_doc(10, LAUDO), _doc(11, LAUDO.replace("Maria Açaí", "Bia Souza"))], tmp_path)
    original = rodada_exames.exames.propor_exames

    def quebra(s, pid, laudo, dono=None):
        if pid == 10:
            raise RuntimeError("Maria Açaí 215")  # a mensagem não pode vazar
        return original(s, pid, laudo, dono)

    monkeypatch.setattr(rodada_exames.exames, "propor_exames", quebra)
    _rodar(con, tmp_path, p)
    d = con.execute("select estado, motivo from exame_doc where paperless_id=10").fetchone()
    assert (d["estado"], d["motivo"]) == ("falhou", "erro ao extrair")
    assert {x["paperless_id"] for x in _propostas(tmp_path)} == {11}


def test_dono_unico_e_sugerido(con):
    assert dono_proposto(con, "MARIA ACAI") == "p-maria" and dono_proposto(con, "Maria Açaí Souza") == "p-maria"
    assert dono_proposto(con, "Fulano de Tal") is None and dono_proposto(con, None) is None


def test_dono_ambiguo_nao_e_sugerido(con, tmp_path):
    con.execute("insert into pessoa(id, nome) values ('p-maria2', 'Maria Açaí Souza')")
    assert dono_proposto(con, "Maria Açaí Souza") == "p-maria2"  # nome exato desempata
    con.execute("insert into pessoa(id, nome) values ('p-maria3', 'Maria Rocha')")
    assert dono_proposto(con, "Maria") is None  # várias Marias: o brain não escolhe
    p, _ = _sistema([_doc(10, LAUDO.replace("Maria Açaí", "Maria"))], tmp_path)
    r = _rodar(con, tmp_path, p)
    assert r["sem_dono"] == 1 and {x["pessoa_sugerida"] for x in _propostas(tmp_path)} == {None}


def test_email_classificado_como_exame_ganha_etiqueta_e_e_extraido(con, tmp_path):
    p, srv = _sistema([_doc(20, LAUDO, tags=(2,), titulo="Resultados")], tmp_path)
    m = Modelo(json.dumps({"tipo": "exame"}))
    r = _rodar(con, tmp_path, p, m)
    assert r["classificados"] == 1 and 1 in srv.docs[20]["tags"] and r["extraidos"] == 1
    assert len(m.prompts) == 1 and "DADO de terceiros" in m.prompts[0]


def test_documento_outro_nao_vira_exame(con, tmp_path):
    p, srv = _sistema([_doc(21, "Fatura da internet", tags=(2,))], tmp_path)
    r = _rodar(con, tmp_path, p, Modelo(json.dumps({"tipo": "outro"})))
    assert r["classificados"] == 1 and r["novos"] == 0 and 3 in srv.docs[21]["tags"] and 1 not in srv.docs[21]["tags"]
    m = Modelo(json.dumps({"tipo": "exame"}))
    _rodar(con, tmp_path, p, m)
    assert m.prompts == []  # já decidido: não pergunta de novo
    assert con.execute("select count(*) from exame_doc").fetchone()[0] == 0


def test_email_sem_modelo_fica_para_depois(con, tmp_path):
    p, srv = _sistema([_doc(22, LAUDO, tags=(2,))], tmp_path)
    assert _rodar(con, tmp_path, p)["classificados"] == 0 and srv.docs[22]["tags"] == [2]


def test_rodar_duas_vezes_nao_reextrai(con, tmp_path):
    p, _ = _sistema([_doc(10, LAUDO)], tmp_path)
    _rodar(con, tmp_path, p)
    r = _rodar(con, tmp_path, p)
    assert r["novos"] == 0 and len(_propostas(tmp_path)) == 2


def test_cofre_nao_abre_quando_nao_ha_documento_novo(con, tmp_path):
    p, _ = _sistema([], tmp_path)
    assert rodar(con, lambda: pytest.fail("abriu o cofre sem necessidade"), p, None, Orcamento(1, 10), AGORA)["novos"] == 0


def test_modelo_so_para_o_que_as_regras_nao_pegam(con, tmp_path):
    p, _ = _sistema([_doc(10, TABELA)], tmp_path)
    m = Modelo(json.dumps({"marcadores": [{"marcador": "TSH", "valor": 2.5, "unidade": "uUI/mL"}]}))
    r = _rodar(con, tmp_path, p, m)
    assert r["extraidos"] == 1 and _propostas(tmp_path)[0]["origem"] == "modelo" and _propostas(tmp_path)[0]["pessoa_sugerida"] == "p-bia"


def test_log_nao_tem_nome_nem_valor(con, tmp_path, capsys, monkeypatch):
    p, _ = _sistema([_doc(10, LAUDO), _doc(11, "")], tmp_path)
    monkeypatch.setenv("GABI_FONTES_SOCKET", "/nao/existe")
    banco = tmp_path / "g.db"
    con.commit()
    rc = programa.main(banco, paperless=p, cliente=None, cofre=(tmp_path / "s.enc", CHAVE))
    saida = capsys.readouterr()
    texto = saida.out + saida.err
    assert rc == 0 and "extraidos=1" in texto and "falhos=1" in texto
    for proibido in ("Maria", "Açaí", "Colesterol", "215", "Glicose", "92"):
        assert proibido not in texto
    c = sqlite3.connect(banco)
    assert c.execute("select erro from rodada where fonte='exames'").fetchone()[0] == "1 documento(s) de exame falharam"


def test_sem_chave_do_cofre_nao_roda_e_avisa(tmp_path, capsys):
    banco = tmp_path / "g.db"
    rc = programa.main(banco, paperless=object(), cliente=None, cofre=None)
    assert rc == 1
    c = sqlite3.connect(banco)
    assert c.execute("select count(*) from aviso where tipo='servico_falhou'").fetchone()[0] == 1
    assert c.execute("select count(*) from exame_doc").fetchone()[0] == 0
