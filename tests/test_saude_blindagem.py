"""Blindagem do ADR-014 nos exames: o MCP não alcança o cofre, o gabi.db não guarda dado de exame e a medição só imprime contagens."""
import re
import subprocess
import sys
from pathlib import Path

from gabi.db import conectar, migrar
from gabi.dinheiro.modelo import Orcamento
from gabi.familia import __main__ as programa
from gabi.familia.exames import confirmar_laudo
from gabi.familia.saude import abrir_saude
from gabi.fontes.paperless import Paperless
from tests.cobrar.paperless_falso import PaperlessFalso
from tools import medir_exames

RAIZ = Path(__file__).parent.parent
CHAVE = bytes(range(32))
LAUDO = """Paciente: Maria Açaí Teixeira    Data da coleta: 10/07/2026
Colesterol total ............ 238,4 mg/dL    Valor de referência: 0 a 200 mg/dL
Glicose em jejum: 117 mg/dL (Ref.: 70 - 99)
"""


def test_nenhuma_ferramenta_mcp_le_o_cofre():
    # 1) nenhum arquivo do pacote MCP cita o cofre ou os exames
    for p in (RAIZ / "gabi" / "mcp").rglob("*.py"):
        codigo = "\n".join(l for l in p.read_text(encoding="utf-8").splitlines() if re.match(r"\s*(from|import)\s", l))  # só importações (comentário pode citar o cofre)
        assert not re.search(r"gabi\.familia|familia\.(saude|exames)", codigo), p.name
    # 2) e, carregado o servidor com todas as ferramentas registradas, o cofre não entrou em memória por nenhum caminho de importação
    codigo = ("import sys, tempfile, pathlib\nfrom gabi.mcp.servidor import criar_mcp\n"
              "criar_mcp(pathlib.Path(tempfile.mkdtemp())/'x.db', hosts=['127.0.0.1:8081'])\n"
              "sys.exit(1 if 'gabi.familia.saude' in sys.modules or 'gabi.familia.exames' in sys.modules else 0)")
    r = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, env={"PYTHONPATH": str(RAIZ), "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-500:]


def _rodada_completa(tmp_path):
    banco = tmp_path / "g.db"
    con = conectar(banco)
    migrar(con, RAIZ / "migrations")
    con.execute("insert into pessoa(id, nome) values ('p-maria', 'Maria')")
    con.commit()
    con.close()
    srv = PaperlessFalso(docs=[{"id": 10, "title": "laudo", "content": LAUDO, "tags": [1]}, {"id": 11, "title": "vazio", "content": "", "tags": [1]}],
                         tags={"gabi:saude-exame": 1})
    rc = programa.main(banco, paperless=Paperless("http://p", "t", http=srv), cliente=None, cofre=(tmp_path / "s.enc", CHAVE))
    assert rc == 0
    return banco


def test_banco_sem_valor_de_exame(tmp_path, capsys):
    banco = _rodada_completa(tmp_path)
    with abrir_saude(tmp_path / "s.enc", CHAVE) as s:  # a rodada gravou de verdade no cofre
        assert s.con.execute("select count(*) from proposta_exame").fetchone()[0] == 2
    con = conectar(banco)
    tudo = "\n".join(con.iterdump())  # esquema e dados de TODAS as tabelas
    for proibido in ("Teixeira", "Açaí", "Colesterol", "Glicose", "238", "117"):
        assert proibido not in tudo, proibido
    assert "paciente" not in " ".join(c[1] for t in con.execute("select name from sqlite_master where type='table'").fetchall() for c in con.execute(f"pragma table_info({t[0]})"))
    saida = capsys.readouterr()
    for proibido in ("Teixeira", "Açaí", "Colesterol", "238"):
        assert proibido not in saida.out + saida.err


def test_medir_exames_so_imprime_contagens(tmp_path, capsys, monkeypatch):
    banco = _rodada_completa(tmp_path)
    with abrir_saude(tmp_path / "s.enc", CHAVE) as s:
        confirmar_laudo(s, 10, "p-maria", "boss@x.com")  # dono sugerido = confirmado
    chave = tmp_path / "chave"
    chave.write_bytes(CHAVE)
    monkeypatch.setenv("GABI_BANCO", str(banco))
    monkeypatch.setenv("GABI_SAUDE_CHAVE_ARQUIVO", str(chave))
    monkeypatch.setenv("GABI_SAUDE_ARQUIVO", str(tmp_path / "s.enc"))
    capsys.readouterr()
    assert medir_exames.main() == 0
    out = capsys.readouterr().out.strip()
    assert re.fullmatch(r"exames: (\w+=\d+ ?)+", out), out
    assert "documentos=2" in out and "extraidos=1" in out and "confirmados=1" in out and "sem_correcao=1" in out and "falhos=1" in out and "origem_regras=1" in out
    for proibido in ("Maria", "Colesterol", "238"):
        assert proibido not in out
