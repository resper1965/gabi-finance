import datetime as dt
import hashlib
import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.familia.obsidian import exportar_cofre, importar_edicoes
from gabi.familia.saude import abrir_saude, registrar_exame

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
CHAVE = bytes(range(32))


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into pessoa(id, nome, papel, telefone, dados) values ('p1','Ricardo','titular','+5511900000001','{\"documentos\":[{\"tipo\":\"CPF\",\"numero\":\"111.222.333-44\"}]}')")
    c.execute("insert into pessoa(id, nome, papel, dados) values ('p2','Maria','esposa','{\"documentos\":[{\"tipo\":\"CPF\",\"numero\":\"555.666.777-88\"}]}')")
    c.execute("insert into acesso(login, pessoa_id, nivel, criado_em) values ('boss@x.com','p1','boss','t'), ('maria@x.com','p2','familia_vip','t')")
    for info, b, f, t in (("família", "total", "parcial", "nenhum"), ("saúde", "total", "parcial", "nenhum"), ("frentes", "total", "nenhum", "nenhum"),
                          ("decisões", "total", "nenhum", "nenhum"), ("memória", "total", "nenhum", "nenhum")):
        c.execute("insert into matriz_acesso(informacao, boss, familia_vip, terceiros) values (?,?,?,?)", (info, b, f, t))
    c.execute("insert into frente(nome, tipo) values ('IONIC','cliente')")
    c.execute("insert into decisao(quando, quem, o_que, origem) values ('2026-10-01T10:00:00','boss@x.com','aprovou regra 1','api')")
    c.execute("insert into memoria(chave, tipo, texto) values ('m1','nota','Lembrar do seguro do carro')")
    return c


@pytest.fixture
def saude(tmp_path):
    arq = tmp_path / "s.enc"
    with abrir_saude(arq, CHAVE) as s:
        registrar_exame(s, "p1", "Glicose", "90", "mg/dL", dt.date(2026, 1, 1), ("70", "99"), 1, "boss@x.com")
        registrar_exame(s, "p2", "Colesterol total", "150", "mg/dL", dt.date(2026, 1, 1), ("0", "200"), 2, "boss@x.com")
    return arq


def _arquivos(raiz: Path):
    return {str(p.relative_to(raiz)): p.read_text(encoding="utf-8") for p in sorted(raiz.rglob("*.md"))}


def test_boss_recebe_tudo_com_cpf_e_saude(con, saude, tmp_path):
    with abrir_saude(saude, CHAVE) as s:
        exportar_cofre(con, s, tmp_path / "cofre", "p1")
    a = _arquivos(tmp_path / "cofre" / "p1")
    assert {"Familia/Maria.md", "Familia/Ricardo.md", "Saude/Maria.md", "Saude/Ricardo.md", "Frentes.md", "Decisoes.md", "Memoria/nota.md"} <= set(a)
    assert "111.222.333-44" in a["Familia/Ricardo.md"] and "555.666.777-88" in a["Familia/Maria.md"] and "Glicose" in a["Saude/Ricardo.md"]
    assert "IONIC" in a["Frentes.md"] and "aprovou regra 1" in a["Decisoes.md"] and "seguro do carro" in a["Memoria/nota.md"]


def test_cada_pessoa_recebe_so_a_propria_pasta(con, saude, tmp_path):
    with abrir_saude(saude, CHAVE) as s:
        exportar_cofre(con, s, tmp_path / "cofre", "p2")
    a = _arquivos(tmp_path / "cofre" / "p2")
    assert set(a) == {"Familia/Maria.md", "Saude/Maria.md"}  # grau parcial: só ela; frentes/decisões/memória não têm linha liberada
    assert "111.222.333-44" not in "".join(a.values()) and "Glicose" not in "".join(a.values())
    assert not (tmp_path / "cofre" / "p1").exists()


def test_sem_cofre_de_saude_a_pasta_sai_sem_saude(con, tmp_path):
    exportar_cofre(con, None, tmp_path / "cofre", "p1")
    assert not [k for k in _arquivos(tmp_path / "cofre" / "p1") if k.startswith("Saude")]


def test_exportacao_e_deterministica(con, saude, tmp_path):
    for nome in ("a", "b"):
        with abrir_saude(saude, CHAVE) as s:
            exportar_cofre(con, s, tmp_path / nome, "p1")
    assert _arquivos(tmp_path / "a" / "p1") == _arquivos(tmp_path / "b" / "p1")


def test_edicao_externa_vira_sugestao_e_nao_sobrescreve(con, tmp_path):
    exportar_cofre(con, None, tmp_path / "cofre", "p1")
    arq = tmp_path / "cofre" / "p1" / "Frentes.md"
    arq.write_text(arq.read_text(encoding="utf-8") + "\n- Nova frente que eu criei no Obsidian\n", encoding="utf-8")
    exportar_cofre(con, None, tmp_path / "cofre", "p1")  # exporta de novo: importa a edição antes e preserva o arquivo
    assert "Nova frente que eu criei" in arq.read_text(encoding="utf-8")
    s = con.execute("select pessoa_id, arquivo, texto, estado from edicao_externa").fetchall()
    assert len(s) == 1 and (s[0]["pessoa_id"], s[0]["arquivo"], s[0]["estado"]) == ("p1", "Frentes.md", "pendente") and "Nova frente" in s[0]["texto"]
    assert con.execute("select count(*) from frente").fetchone()[0] == 1  # o banco não mudou
    assert importar_edicoes(con, tmp_path / "cofre" / "p1", "p1") == 0  # mesma edição não duplica


def test_edicao_rejeitada_e_sobrescrita_na_proxima_exportacao(con, tmp_path):
    exportar_cofre(con, None, tmp_path / "cofre", "p1")
    arq = tmp_path / "cofre" / "p1" / "Frentes.md"
    original = arq.read_text(encoding="utf-8")
    arq.write_text(original + "lixo", encoding="utf-8")
    exportar_cofre(con, None, tmp_path / "cofre", "p1")
    con.execute("update edicao_externa set estado='rejeitada'")
    exportar_cofre(con, None, tmp_path / "cofre", "p1")
    assert arq.read_text(encoding="utf-8") == original
