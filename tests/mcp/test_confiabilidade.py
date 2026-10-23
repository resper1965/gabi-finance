"""Confiabilidade (Parte C): vazio explícito no MCP, SOUL do Hermes versionado e script de instalação.
Consome: gabi.mcp.servidor (criar_mcp, AVISO_VAZIO), deploy/hermes/SOUL.md, deploy/instalar-hermes-soul.sh. Sem rede."""
import os
import subprocess
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from gabi.db import conectar
from gabi.fontes.paperless import Paperless
from gabi.mcp.servidor import AVISO_VAZIO, criar_mcp
from gabi.mcp.tokens import emitir
from tests.cobrar.paperless_falso import PaperlessFalso
from tests.mcp.test_servidor import AGORA, HOST, banco, chamar  # noqa: F401  (fixtures e helpers)

RAIZ = Path(__file__).resolve().parent.parent.parent
SOUL = RAIZ / "deploy" / "hermes" / "SOUL.md"
SCRIPT = RAIZ / "deploy" / "instalar-hermes-soul.sh"
TEXTO_AVISO = "Nenhum resultado para esta consulta. Diga ao Ricardo que não encontrou; não suponha nem estime."
REGRAS = [
    "Fato sobre dinheiro, documento ou pessoa só com dado devolvido por ferramenta nesta conversa. Sem resultado, diga 'não encontrei' e o que procurou. Dois dados diferentes: mostre os dois, com a origem.",
    "Para ler um documento do Paperless, use `documentos_texto`; cite o título e a data.",
    "Número de documento só quando o Ricardo pedir aquela pessoa e aquele documento.",
]


@pytest.fixture
def tok(banco):
    c = conectar(banco)
    t = {"fin": emitir(c, "fin", ["fin"]), "docs": emitir(c, "docs", ["docs"])}
    c.close()
    return t


@pytest.fixture
def cli(banco):
    app = criar_mcp(banco, hosts=[HOST], relogio=lambda: AGORA, paperless=Paperless("http://p", "tok", http=PaperlessFalso(docs=[])))
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


def test_documentos_buscar_vazio_traz_aviso(cli, tok):
    d = chamar(cli, tok["docs"], "documentos_buscar", texto="nada")["dados"]
    assert d["itens"] == [] and d["vazio"] is True and d["aviso"] == TEXTO_AVISO


def test_soul_do_repositorio_tem_as_tres_regras_e_nao_tem_reembolso_nem_exames():
    t = SOUL.read_text()
    for r in REGRAS:
        assert r in t
    assert "reembolso" not in t.lower() and "exames" not in t.lower()
    assert "vai para o Paperless" in t or "foi para o Paperless" in t


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
