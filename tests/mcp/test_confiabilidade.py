"""Confiabilidade (Parte C): vazio explícito no MCP, SOUL do Hermes versionado e script de instalação.
Consome: gabi.mcp.servidor (criar_mcp, AVISO_VAZIO), deploy/hermes/SOUL.md, deploy/instalar-hermes-soul.sh. Sem rede."""
import os
import subprocess
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from gabi.db import conectar
from gabi.mcp.servidor import AVISO_VAZIO, criar_mcp
from gabi.mcp.tokens import emitir
from tests.mcp.test_servidor import AGORA, HOST, banco, chamar  # noqa: F401  (fixtures e helpers)

RAIZ = Path(__file__).resolve().parent.parent.parent
SOUL = RAIZ / "deploy" / "hermes" / "SOUL.md"
SCRIPT = RAIZ / "deploy" / "instalar-hermes-soul.sh"
TEXTO_AVISO = "Nenhum resultado para esta consulta. Diga ao Ricardo que não encontrou; não suponha nem estime."
REGRAS = [
    "Fato sobre dinheiro só com dado devolvido por ferramenta nesta conversa. Sem resultado, diga 'não encontrei' e o que procurou. Dois dados diferentes: mostre os dois, com a origem.",
]


@pytest.fixture
def tok(banco):
    c = conectar(banco)
    t = {"fin": emitir(c, "fin", ["fin"])}
    c.close()
    return t


@pytest.fixture
def cli(banco):
    app = criar_mcp(banco, hosts=[HOST], relogio=lambda: AGORA)
    with TestClient(app, base_url=f"http://{HOST}") as c:
        yield c


def test_aviso_vazio_tem_o_texto_exato_da_spec():
    assert AVISO_VAZIO == TEXTO_AVISO


def test_lancamentos_vazio_traz_aviso_sem_perder_outras_chaves(cli, tok):
    r = chamar(cli, tok["fin"], "financeiro_lancamentos", texto="nada-assim-existe")
    d = r["dados"]
    assert d["itens"] == [] and d["vazio"] is True and d["aviso"] == TEXTO_AVISO
    assert len(d) > 3  # as demais chaves do resultado continuam (Review Focus 5)
    assert "dados_ate" in r


def test_lancamentos_com_resultado_nao_traz_vazio_nem_aviso(cli, tok, banco):
    c = conectar(banco)
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b9','C6','BANK','Conta x','sim')")
    cid = c.execute("select id from conta where externo_id='b9'").fetchone()[0]
    c.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original) values (?, 'conf-l1', '2026-10-01', -1000, 'padaria')", (cid,))
    c.commit()
    c.close()
    d = chamar(cli, tok["fin"], "financeiro_lancamentos", texto="padaria")["dados"]
    assert d["itens"] and "vazio" not in d and "aviso" not in d


def test_soul_do_repositorio_tem_as_tres_regras_e_nao_promete_fluxo_de_exames_nem_de_reembolso():
    t = SOUL.read_text()
    for r in REGRAS:
        assert r in t
    # o SOUL antigo prometia que o PDF "entra no fluxo (exames, contas, reembolso)"; esses fluxos saíram (ADR-023).
    # "reembolso" só aparece como a Empresa marcada na compra (financeiro_marcar_reembolso), que alimenta despesas_por_empresa
    assert "exames" not in t.lower() and "fluxo (" not in t.lower()
    assert all("financeiro_marcar_reembolso" in linha or "despesas_por_empresa" in linha for linha in t.splitlines() if "reembolso" in linha.lower())


def _rodar(home: Path):
    return subprocess.run(["bash", str(SCRIPT)], env={**os.environ, "HOME": str(home)}, capture_output=True, text=True)


def test_script_instala_com_backup_do_soul_existente(tmp_path):
    (tmp_path / ".hermes").mkdir()
    (tmp_path / ".hermes" / "SOUL.md").write_text("antigo")
    r = _rodar(tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / ".hermes" / "SOUL.md").read_text() == SOUL.read_text()
    baks = list((tmp_path / ".hermes").glob("SOUL.md.bak-*"))
    assert len(baks) == 1 and baks[0].read_text() == "antigo"
    assert "sudo systemctl restart hermes-gateway" in r.stdout


def test_script_sem_soul_previo_instala_sem_backup(tmp_path):
    r = _rodar(tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / ".hermes" / "SOUL.md").read_text() == SOUL.read_text()
    assert not list((tmp_path / ".hermes").glob("SOUL.md.bak-*"))


def test_script_nao_usa_sudo_nem_reinicia_nada():
    exec_ = [l for l in SCRIPT.read_text().splitlines() if l.strip() and not l.lstrip().startswith(("#", "echo"))]
    assert not any("sudo" in l or "systemctl" in l for l in exec_)


def test_soul_despesas_nao_reabre_encerrada():
    # ADR-032: não existe reabrir; para voltar, cria de novo
    t = SOUL.read_text()
    linha = next(l for l in t.splitlines() if "despesa_encerrar" in l and "→" in l)
    assert "despesa_criar" in linha and "reabrir" in linha
