"""tools/conferir_virada.py: a saída tem de ser a MESMA sobre a cópia do banco antigo (esquema 0089) e sobre o banco já migrado (0091),
porque é assim que a virada confere (docs/virada.md): rodar nos dois e comparar com diff."""
import datetime as dt
import shutil
import sqlite3
from pathlib import Path

from gabi.db import conectar, migrar
from tools import conferir_virada as cv

MIGR = Path(__file__).resolve().parents[2] / "migrations"
HOJE = dt.date(2026, 11, 17)


def _ate_0089(tmp_path: Path) -> Path:
    pasta = tmp_path / "ate0089"
    pasta.mkdir()
    for arq in MIGR.glob("[0-9][0-9][0-9][0-9]_*.sql"):
        if arq.name < "0090":
            shutil.copy(arq, pasta / arq.name)
    return pasta


def _banco_antigo(tmp_path: Path) -> Path:
    """Banco no esquema do gabi-brain (até a 0089), com dinheiro e com dado de áreas que vão sair."""
    antigo = tmp_path / "brain.db"
    con = conectar(antigo)
    migrar(con, _ate_0089(tmp_path))
    con.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b1','C6','BANK','C6 PJ','sim')")
    con.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b2','Itau','BANK','Itaú','sim')")
    con.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b3','XP','BANK','XP fora','nao')")
    con.execute("insert into saldo(conta_id, em, saldo_centavos) values (1, '2026-11-17T06:05:00', 150000)")
    con.execute("insert into saldo(conta_id, em, saldo_centavos) values (1, '2026-11-16T06:05:00', 90000)")
    con.execute("insert into saldo(conta_id, em, saldo_centavos) values (2, '2026-11-17T06:05:00', 25050)")
    con.execute("insert into saldo(conta_id, em, saldo_centavos) values (3, '2026-11-17T06:05:00', 999999)")
    for cid, nome, venc, valor, estado, forma in (("a:2026-11", "Aluguel", "2026-11-20", 300000, "aberto", "pix"),
                                                  ("b:2026-11", "Luz", "2026-11-10", 20000, "atrasado", "boleto"),
                                                  ("c:2026-11", "Escola", "2026-11-25", None, "aberto", "boleto"),
                                                  ("d:2026-11", "Gás", "2026-11-05", 8000, "pago", "pix"),
                                                  ("e:2026-12", "Seguro", "2026-12-05", 11000, "aberto", "boleto")):
        con.execute("insert into compromisso(id, origem, nome, vencimento, vencimento_util, valor_centavos, estado, forma) values (?,?,?,?,?,?,?,?)",
                    (cid, "planilha", nome, venc, venc, valor, estado, forma))
    # dado das áreas que saem: não pode mudar nada na conferência
    con.execute("insert into projeto(nome, criado_em, origem) values ('P','2026-10-01','hermes')")
    con.execute("insert into atividade(texto, origem, criada_em) values ('x','hermes','2026-10-01')")
    con.close()
    return antigo


def test_saida_e_identica_no_banco_antigo_e_no_migrado(tmp_path, capsys):
    antigo = _banco_antigo(tmp_path)
    novo = tmp_path / "finance.db"
    shutil.copy(antigo, novo)
    con = conectar(novo)
    migrar(con, MIGR)  # 0090 e 0091: as tabelas das áreas que saem somem
    assert not con.execute("select 1 from sqlite_master where name in ('projeto','atividade')").fetchall()
    con.close()
    assert cv.main(["--banco", str(antigo), "--hoje", HOJE.isoformat()]) == 0
    saida_antigo = capsys.readouterr().out
    assert cv.main(["--banco", str(novo), "--hoje", HOJE.isoformat()]) == 0
    saida_novo = capsys.readouterr().out
    assert saida_antigo == saida_novo and saida_antigo.endswith("\n")


def test_conteudo_da_conferencia(tmp_path, capsys):
    antigo = _banco_antigo(tmp_path)
    assert cv.main(["--banco", str(antigo), "--hoje", "2026-11-17"]) == 0
    linhas = capsys.readouterr().out.splitlines()
    assert linhas[0] == "conferencia-virada v1 hoje=2026-11-17"
    assert "C6 PJ\t1500.00\t2026-11-17T06:05:00" in linhas and "Itaú\t250.50\t2026-11-17T06:05:00" in linhas
    assert not any(l.startswith("XP fora") for l in linhas)  # conta não liberada fica fora do caixa único
    assert "total\t1750.50" in linhas
    # A pagar de novembro: aberto 3000.00 (+ 1 sem valor), atrasado 200.00; o pago e o de dezembro não entram
    assert "aberto\t2\t3000.00" in linhas and "atrasado\t1\t200.00" in linhas and "a_conferir\t0\t0.00" in linhas
    assert "total\t3\t3200.00" in linhas and "sem_valor\t1" in linhas
    projecao = [l for l in linhas if l.startswith("2026-") and l.count("\t") == 3]
    assert len(projecao) == 30 and projecao[0].startswith("2026-11-17\t")
    assert any(l.startswith("menor_saldo\t") for l in linhas)


def test_nao_escreve_no_banco(tmp_path):
    antigo = _banco_antigo(tmp_path)
    antes = antigo.read_bytes()
    assert cv.main(["--banco", str(antigo), "--hoje", "2026-11-17"]) == 0
    assert antigo.read_bytes() == antes
    con = sqlite3.connect(antigo)
    assert con.execute("select count(*) from compromisso").fetchone()[0] == 5


def test_banco_inexistente_falha_sem_criar_arquivo(tmp_path, capsys):
    assert cv.main(["--banco", str(tmp_path / "nao-existe.db")]) == 1
    assert not (tmp_path / "nao-existe.db").exists()
    assert "ERRO" in capsys.readouterr().err
