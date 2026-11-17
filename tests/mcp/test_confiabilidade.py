"""Confiabilidade (Parte C): vazio explícito no MCP, bloco de referência do SOUL versionado e o script que edita o SOUL na virada.
Consome: gabi.mcp.servidor (criar_mcp, AVISO_VAZIO), deploy/hermes/SOUL.md, deploy/hermes/editar_soul.py. Sem rede."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from gabi.db import conectar
from gabi.mcp.servidor import AVISO_VAZIO, criar_mcp
from gabi.mcp.tokens import emitir
from tests.mcp.test_servidor import AGORA, HOST, banco, chamar  # noqa: F401  (fixtures e helpers)

RAIZ = Path(__file__).resolve().parent.parent.parent
SOUL = RAIZ / "deploy" / "hermes" / "SOUL.md"
SCRIPT = RAIZ / "deploy" / "hermes" / "editar_soul.py"
_spec = importlib.util.spec_from_file_location("editar_soul", SCRIPT)
editar_soul = importlib.util.module_from_spec(_spec)
_antes, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # sem __pycache__ em deploy/ (tests/test_deploy.py lê tudo como texto)
_spec.loader.exec_module(editar_soul)
sys.dont_write_bytecode = _antes
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


SOUL_DO_BRAIN = """Regras fixas:
- Exceção: valor a receber vai para `financeiro_registrar_a_receber`; "lembra de X" vai para `atividade_criar`.
- "saldo?" → `mcp__gabi_brain__financeiro_saldo`; "que avisos tenho?" → `avisos_abertos`; resumo → `resumo_manha`.
- gasto → `financeiro_marcar_gasto(ids, "nao" | "sim")`; despesa → `despesa_mes(X, mes)`; lista → `despesas_listar`.
- e-mail → `email_lixeira`; decisão → `decisao_responder`, `decisoes_abertas`, `decisoes_recentes`.
- texto solto financeiro_saldo sem crase não muda; `financeiro_saldos_extra` não é ferramenta.
"""


def _rodar(soul: Path, data: str = "2026-11-18-0600"):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), "--soul", str(soul), "--data", data], capture_output=True, text=True)


def test_editar_soul_conhece_exatamente_as_28_so_de_dinheiro():
    from tools.gerar_hermes import tirar_do_brain
    assert list(editar_soul.DINHEIRO) == tirar_do_brain() and len(editar_soul.DINHEIRO) == 28


def test_editar_soul_troca_so_as_28_dentro_de_crases_e_guarda_backup(tmp_path):
    soul = tmp_path / "SOUL.md"
    soul.write_text(SOUL_DO_BRAIN, encoding="utf-8")
    r = _rodar(soul)
    assert r.returncode == 0, r.stderr
    bak = tmp_path / "SOUL.md.bak-antes-finance-2026-11-18-0600"
    assert bak.read_text(encoding="utf-8") == SOUL_DO_BRAIN
    novo = soul.read_text(encoding="utf-8")
    for nome in ("financeiro_registrar_a_receber", "financeiro_saldo", "despesas_listar"):
        assert f"`mcp__gabi_finance__{nome}`" in novo
    assert '`mcp__gabi_finance__financeiro_marcar_gasto(ids, "nao" | "sim")`' in novo and "`mcp__gabi_finance__despesa_mes(X, mes)`" in novo
    assert "mcp__gabi_brain__financeiro_saldo" not in novo
    for fica in ("`atividade_criar`", "`avisos_abertos`", "`resumo_manha`", "`email_lixeira`", "`decisao_responder`", "`decisoes_abertas`",
                 "`decisoes_recentes`", "`financeiro_saldos_extra`", "texto solto financeiro_saldo sem crase"):
        assert fica in novo, fica
    # fora a seção nova, só mudaram as linhas com nome de dinheiro, e só pelo prefixo
    corpo = novo.split("\n" + editar_soul.MARCA)[0]
    assert corpo.rstrip("\n").replace("mcp__gabi_finance__", "").replace("mcp__gabi_brain__", "") == SOUL_DO_BRAIN.rstrip("\n").replace("mcp__gabi_brain__", "")
    assert novo.count(editar_soul.MARCA) == 1 and "Resumo da manhã: chame os dois e junte, dinheiro primeiro." in novo
    assert "sudo systemctl restart hermes-gateway" in r.stdout


def test_editar_soul_e_idempotente_e_nao_cria_outro_backup(tmp_path):
    soul = tmp_path / "SOUL.md"
    soul.write_text(SOUL_DO_BRAIN, encoding="utf-8")
    assert _rodar(soul).returncode == 0
    uma = soul.read_text(encoding="utf-8")
    r = _rodar(soul, "2026-11-18-0700")
    assert r.returncode == 0 and "nada a mudar" in r.stdout
    assert soul.read_text(encoding="utf-8") == uma and len(list(tmp_path.glob("SOUL.md.bak-*"))) == 1
    assert editar_soul.editar(uma) == (uma, 0)


def test_editar_soul_nao_sobrescreve_backup_existente_nem_age_sem_soul(tmp_path):
    soul = tmp_path / "SOUL.md"
    soul.write_text(SOUL_DO_BRAIN, encoding="utf-8")
    (tmp_path / "SOUL.md.bak-antes-finance-2026-11-18-0600").write_text("outro", encoding="utf-8")
    assert _rodar(soul).returncode == 1 and soul.read_text(encoding="utf-8") == SOUL_DO_BRAIN
    assert _rodar(tmp_path / "nao-existe.md").returncode == 1


def test_editar_soul_so_usa_biblioteca_padrao_e_nao_reinicia_nada():
    texto = SCRIPT.read_text(encoding="utf-8")
    assert "import gabi" not in texto and "from gabi" not in texto and "subprocess" not in texto and "systemctl restart" in texto  # só no lembrete
    assert not [linha for linha in texto.splitlines() if "systemctl" in linha and "print(" not in linha]


def test_soul_despesas_nao_reabre_encerrada():
    # ADR-032: não existe reabrir; para voltar, cria de novo
    t = SOUL.read_text()
    linha = next(l for l in t.splitlines() if "despesa_encerrar" in l and "→" in l)
    assert "despesa_criar" in linha and "reabrir" in linha
