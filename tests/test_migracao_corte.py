"""Migração 0090 (corte do gabi-finance): derruba as tabelas das áreas que saíram e deixa as que o código que fica ainda lê ou grava.
As duas listas abaixo são EXPLÍCITAS e juntas cobrem todas as tabelas e visões que existem na 0089: tabela nova exige decidir se fica ou sai.
KEEP foi derivada por `grep` de nomes de tabela nas strings SQL de gabi/ e tools/ (e conferida aqui por `test_nenhum_modulo_que_fica_le_tabela_derrubada`)."""
import re
import shutil
from pathlib import Path

import pytest

from gabi.db import conectar, migrar

MIGR = Path(__file__).parent.parent / "migrations"
RAIZ = Path(__file__).parent.parent

# fica: finanças, base/auth/MCP (acesso, matriz_acesso, token_agente, chamada, chamada_mcp, aviso, rodada, parametro, decisao, pergunta, schema_versao)
# e as que código que fica ainda usa: agenda_evento/agenda_fonte (dinheiro.sugestoes_agenda), pet/allowlist_vip/memoria/agenda_estado/agenda_eventos/
# compromisso_fixo/conta_estado (importar, o carregador do staging) e custo_modelo (dinheiro.modelo). `pessoa` fica com todas as linhas.
KEEP = {
    "acesso", "agenda_estado", "agenda_evento", "agenda_eventos", "agenda_fonte", "allowlist_vip", "assinatura", "aviso", "captura_conta", "categoria",
    "chamada", "chamada_mcp", "compromisso", "compromisso_fixo", "compromisso_linha", "compromisso_padrao", "conciliacao", "conferencia", "conta",
    "conta_estado", "custo_modelo", "decisao", "empresa", "equivalencia_categoria", "fatura", "gastador_regra", "lancamento", "matriz_acesso", "memoria",
    "nota_fiscal", "parametro", "pergunta", "pessoa", "pet", "receber_manual", "receber_manual_proposta", "recebimento_nota", "regra", "rodada", "saldo",
    "schema_versao", "sugestao", "token_agente", "valor_do_mes",
}
# sai: agenda/e-mail sincronizados (e-mail, caixa), Teams, contatos, envios, escuta, família/documentos/bens/pets-documento, projetos, atividades, anexos, legados
DROP = {
    "anexo", "atividade", "bem", "caixa_email", "contato_google", "contato_google_email", "contato_graph", "contato_proposta", "documento", "documento_data",
    "documento_leitura", "documento_numero", "documento_proposta", "email_fonte", "email_msg", "email_respondido", "envio_proposta", "escuta_remetente",
    "familia_documento", "familia_proposta", "pessoa_documento_legado", "pessoa_historico", "pessoa_proposta_legado", "projeto", "projeto_fato",
    "projeto_gasto", "projeto_pessoa", "teams_conversa", "teams_fonte",
}
OBRIGATORIAS = {"pessoa", "conta", "gastador_regra", "decisao", "acesso", "matriz_acesso", "token_agente", "chamada_mcp", "aviso", "rodada"}


def _ate(tmp_path: Path, limite: str) -> Path:
    pasta = tmp_path / f"ate{limite}"
    pasta.mkdir()
    for arq in MIGR.glob("[0-9][0-9][0-9][0-9]_*.sql"):
        if arq.name < limite:
            shutil.copy(arq, pasta / arq.name)
    return pasta


def _nomes(con) -> set[str]:
    return {r[0] for r in con.execute("select name from sqlite_master where type in ('table','view') and name not like 'sqlite_%'")}


def test_keep_e_drop_cobrem_tudo_o_que_existe_na_0089(tmp_path):
    con = conectar(tmp_path / "a.db")
    migrar(con, _ate(tmp_path, "0090"))
    assert not KEEP & DROP and _nomes(con) == KEEP | DROP


def test_depois_da_0090_so_ficam_as_que_ficam(tmp_path):
    con = conectar(tmp_path / "g.db")
    migrar(con, MIGR)
    assert "0090_corte_financeiro.sql" in {r[0] for r in con.execute("select nome from schema_versao")}
    assert _nomes(con) == KEEP
    assert not _nomes(con) & DROP and OBRIGATORIAS <= _nomes(con)


def test_nenhum_modulo_que_fica_le_tabela_derrubada():
    achados = []
    padrao = re.compile(r"\b(?:from|join|into|update|table|exists)\s+(" + "|".join(sorted(DROP)) + r")\b", re.I)
    for pasta in ("gabi", "tools"):
        for arq in (RAIZ / pasta).rglob("*.py"):
            for m in padrao.finditer(arq.read_text(encoding="utf-8")):
                achados.append((arq.relative_to(RAIZ).as_posix(), m.group(1)))
    assert achados == []


def test_nao_sobra_chave_estrangeira_para_tabela_derrubada(tmp_path):
    con = conectar(tmp_path / "g.db")
    migrar(con, MIGR)
    for t in _nomes(con):
        for fk in con.execute(f"pragma foreign_key_list({t})"):
            assert fk[2] in KEEP, (t, fk[2])
    assert con.execute("pragma foreign_key_check").fetchall() == []


def test_migra_banco_com_dados_nas_tabelas_que_saem_sem_tocar_em_pessoa(tmp_path):
    """Com foreign_keys=ON e linhas em filhas e mães: a ordem do drop tem de respeitar as chaves; `pessoa` e o dinheiro passam intactos."""
    con = conectar(tmp_path / "g.db")
    assert con.execute("pragma foreign_keys").fetchone()[0] == 1
    migrar(con, _ate(tmp_path, "0090"))
    con.execute("insert into pessoa(id, nome, papel, telefone, dados) values ('p1','Ana','filha','+5511900000001','{\"x\":1}')")
    con.execute("insert into pessoa(id, nome) values ('p2','Beto')")
    con.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b1','C6','BANK','C6 PJ','sim')")
    con.execute("insert into gastador_regra(conta_id, estabelecimento, pessoa_id, criado_em) values (1, 'PADARIA','p1','2026-10-01')")
    con.execute("insert into compromisso(id, origem, nome, vencimento, estado) values ('c1','linha','Luz','2026-10-10','aberto')")
    # mães e filhas que saem
    pid = con.execute("insert into projeto(nome, criado_em, origem) values ('P','2026-10-01','hermes')").lastrowid
    aid = con.execute("insert into anexo(tipo, recebido_em, projeto_id) values ('documento','2026-10-01',?)", (pid,)).lastrowid
    con.execute("insert into projeto_fato(projeto_id, texto, registrado_em, origem, anexo_id) values (?, 'f','2026-10-01','hermes',?)", (pid, aid))
    con.execute("insert into projeto_gasto(projeto_id, criado_em) values (?, '2026-10-01')", (pid,))
    con.execute("insert into projeto_pessoa(projeto_id, nome, pessoa_id) values (?, 'Ana', 'p1')", (pid,))
    con.execute("insert into atividade(texto, origem, criada_em, projeto_id) values ('x','hermes','2026-10-01',?)", (pid,))
    did = con.execute("insert into documento(titular_tipo, titular_id, tipo, origem) values ('pessoa','p1','cpf','carga')").lastrowid
    con.execute("insert into documento_numero(documento_id, nome, valor) values (?, 'numero', '1')", (did,))
    con.execute("insert into pessoa_documento_legado(pessoa_id, tipo, numero, origem) values ('p1','cpf','1','carga')")
    con.execute("insert into pessoa_historico(pessoa_id, campo, quem) values ('p1','nome','x')")
    fid = con.execute("insert into email_fonte(conta, provedor) values ('a@x.com','google')").lastrowid
    con.execute("insert into email_msg(fonte_id, externo_id, recebida_em) values (?, 'm1', '2026-10-01T00:00:00Z')", (fid,))
    con.execute("insert into email_respondido(fonte_id, endereco, em) values (?, 'r@x.com', '2026-10-01T00:00:00Z')", (fid,))
    antes_pessoa = [tuple(r) for r in con.execute("select * from pessoa order by id")]
    antes_conta = [tuple(r) for r in con.execute("select * from conta")]
    migrar(con, MIGR)
    assert [tuple(r) for r in con.execute("select * from pessoa order by id")] == antes_pessoa
    assert [tuple(r) for r in con.execute("select * from conta")] == antes_conta
    assert con.execute("select count(*) from gastador_regra").fetchone()[0] == 1 and con.execute("select count(*) from compromisso").fetchone()[0] == 1
    assert _nomes(con) == KEEP and con.execute("pragma foreign_key_check").fetchall() == []


def test_a_0090_e_idempotente_em_banco_parcial(tmp_path):
    """`drop ... if exists`: rodar o SQL de novo (banco já cortado, ou sem alguma das tabelas) não falha."""
    con = conectar(tmp_path / "g.db")
    migrar(con, MIGR)
    sql = (MIGR / "0090_corte_financeiro.sql").read_text(encoding="utf-8")
    for instrucao in [i.strip() for i in sql.split(";") if re.search(r"^drop", i.strip(), re.M)]:
        con.execute(re.sub(r"(?s)^.*?(drop )", r"\1", instrucao, count=1))
    assert _nomes(con) == KEEP


@pytest.mark.parametrize("tabela", sorted(OBRIGATORIAS))
def test_obrigatorias_continuam_com_as_colunas_de_base(tmp_path, tabela):
    con = conectar(tmp_path / "g.db")
    migrar(con, MIGR)
    assert {r[1] for r in con.execute(f"pragma table_info({tabela})")}
