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
# e as que código que fica ainda usa: agenda_evento/agenda_fonte (dinheiro.sugestoes_agenda), agenda_estado/agenda_eventos/
# compromisso_fixo/conta_estado (importar, o carregador do staging) e custo_modelo (dinheiro.modelo). `pessoa` fica com todas as linhas.
KEEP = {
    "acesso", "agenda_estado", "agenda_evento", "agenda_eventos", "agenda_fonte", "assinatura", "aviso", "captura_conta", "categoria",
    "chamada", "chamada_mcp", "compromisso", "compromisso_fixo", "compromisso_linha", "compromisso_padrao", "conciliacao", "conferencia", "conta",
    "conta_estado", "custo_modelo", "decisao", "empresa", "equivalencia_categoria", "fatura", "gastador_regra", "lancamento", "matriz_acesso",
    "nota_fiscal", "parametro", "pergunta", "pessoa", "receber_manual", "receber_manual_proposta", "recebimento_nota", "regra", "rodada", "saldo",
    "schema_versao", "sugestao", "token_agente", "valor_do_mes",
}
# sai: agenda/e-mail sincronizados (e-mail, caixa), Teams, contatos, envios, escuta, família/documentos/bens/pets-documento, projetos, atividades, anexos, legados
DROP = {
    "anexo", "atividade", "bem", "caixa_email", "contato_google", "contato_google_email", "contato_graph", "contato_proposta", "documento", "documento_data",
    "documento_leitura", "documento_numero", "documento_proposta", "email_fonte", "email_msg", "email_respondido", "envio_proposta", "escuta_remetente",
    "familia_documento", "familia_proposta", "pessoa_documento_legado", "pessoa_historico", "pessoa_proposta_legado", "projeto", "projeto_fato",
    "projeto_gasto", "projeto_pessoa", "teams_conversa", "teams_fonte",
}
# sai na 0091 (minimização de dados): só o carregador do staging as gravava e nada financeiro as lê
DROP_0091 = {"pet", "allowlist_vip", "memoria"}
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
    assert not KEEP & DROP and not (KEEP | DROP) & DROP_0091 and _nomes(con) == KEEP | DROP | DROP_0091


def test_depois_da_0090_so_ficam_as_que_ficam(tmp_path):
    con = conectar(tmp_path / "g.db")
    migrar(con, MIGR)
    assert "0090_corte_financeiro.sql" in {r[0] for r in con.execute("select nome from schema_versao")}
    assert _nomes(con) == KEEP
    assert not _nomes(con) & DROP and OBRIGATORIAS <= _nomes(con)


def test_nenhum_modulo_que_fica_le_tabela_derrubada():
    achados = []
    padrao = re.compile(r"\b(?:from|join|into|update|table|exists)\s+(" + "|".join(sorted(DROP | DROP_0091)) + r")\b", re.I)
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
    migrar(con, _ate(tmp_path, "0092"))  # a 0092 reduz `pessoa` de propósito (teste próprio abaixo); aqui vale o corte 0090/0091
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


def test_a_0091_derruba_pet_allowlist_e_memoria_sem_tocar_em_pessoa_nem_no_dinheiro(tmp_path):
    con = conectar(tmp_path / "g.db")
    migrar(con, _ate(tmp_path, "0091"))
    assert DROP_0091 <= _nomes(con)
    con.execute("insert into pessoa(id, nome, papel) values ('p1','Ana','filha')")
    con.execute("insert into pet(id, nome) values ('t1','Thor')")
    con.execute("insert into allowlist_vip(chave, pessoa) values ('k','p1')")
    con.execute("insert into memoria(chave, tipo, texto) values ('m1','nota','x')")
    con.execute("insert into compromisso(id, origem, nome, vencimento, estado) values ('c1','linha','Luz','2026-10-10','aberto')")
    antes = [tuple(r) for r in con.execute("select * from pessoa")], [tuple(r) for r in con.execute("select * from compromisso")]
    migrar(con, _ate(tmp_path, "0092"))
    assert not _nomes(con) & DROP_0091 and _nomes(con) == KEEP
    assert ([tuple(r) for r in con.execute("select * from pessoa")], [tuple(r) for r in con.execute("select * from compromisso")]) == antes
    assert con.execute("pragma foreign_key_check").fetchall() == []
    sql = (MIGR / "0091_minimizar_dados.sql").read_text(encoding="utf-8")
    for instrucao in [i for i in re.findall(r"^drop .*?;", sql, re.M | re.S)]:
        con.execute(instrucao)  # idempotente: já caíram e `if exists` não falha


# ---- 0092: limpeza das linhas herdadas do brain (avisos, perguntas, pessoa, agenda, parâmetros) ----
TIPOS_AVISO_0092 = {"vence_hoje", "vence_em_breve", "valor_diferente", "rodada_parada", "saldo_divergente", "banco_desatualizado", "conta_atrasada",
                    "cobrada_apos_cancelar", "servico_falhou", "lancamento_sem_conversao", "exportacao_parada"}


def _sql_0092() -> str:
    return (MIGR / "0092_limpar_herdados.sql").read_text(encoding="utf-8")


def test_a_0092_conhece_exatamente_os_tipos_de_aviso_que_o_codigo_grava():
    fonte = (RAIZ / "gabi" / "avisos.py").read_text(encoding="utf-8")
    gravados = set(re.findall(r'\bnovo\("([a-z_]+)"', fonte)) | set(re.findall(r'_novo\(con, agora, "([a-z_]+)"', fonte))
    assert gravados == TIPOS_AVISO_0092
    lista = re.search(r"delete from aviso where tipo not in \((.*?)\);", _sql_0092(), re.S).group(1)
    assert set(re.findall(r"'([a-z_]+)'", lista)) == TIPOS_AVISO_0092


def test_a_0092_conhece_exatamente_os_efeitos_de_pergunta_do_codigo():
    from gabi.decisoes import EFEITOS
    lista = re.search(r"not in\s*\(('registrar_nota'.*?)\)", _sql_0092(), re.S).group(1)
    assert set(re.findall(r"'([a-z_]+)'", lista)) == set(EFEITOS)


def test_a_0092_so_apaga_parametro_que_o_codigo_nao_le():
    import sqlite3
    apagadas = ("email.vips", "teams.expediente", "agenda.fuso", "contatos.escrita", "envios.escrita", "escuta.contas_contatos", "documentos.avisar_dias",
                "avisos.vigiar_google", "avisos.vigiar_hermes", "avisos.google_horas", "avisos.hermes_unidade", "mcp.url", "painel.url", "paperless.url")
    ficam = ("avisos.antecedencia_dias", "fontes.em_espera", "dinheiro.sync_banco", "categorias_assinatura", "categorias_habito", "cambio_usd_brl",
             "teto_modelo_dia_usd", "teto_modelo_mes_usd", "nibo_socio_id", "horas_envio", "bancos_pj", "telegram_destino")
    con = sqlite3.connect(":memory:")
    con.execute("create table parametro(chave text primary key, valor text)")
    con.executemany("insert into parametro values (?, '1')", [(k,) for k in apagadas + ficam])
    con.execute(re.search(r"(delete from parametro.*?);", _sql_0092(), re.S).group(1))
    assert {r[0] for r in con.execute("select chave from parametro")} == set(ficam)
    # nenhum módulo que fica lê as chaves apagadas (mcp.url fica de fora: gabi.agentes cai no URL_PADRAO quando ela não existe)
    texto = "\n".join(p.read_text(encoding="utf-8") for pasta in ("gabi", "tools") for p in (RAIZ / pasta).rglob("*.py"))
    assert [k for k in apagadas if k != "mcp.url" and (f"'{k}'" in texto or f'"{k}"' in texto)] == []


def _banco_0091(tmp_path):
    con = conectar(tmp_path / "g.db")
    migrar(con, _ate(tmp_path, "0092"))
    return con


def test_a_0092_limpa_o_herdado_e_deixa_o_que_o_dinheiro_usa(tmp_path):
    import datetime as dt
    import json
    con = _banco_0091(tmp_path)
    agora = "2026-11-17T10:00:00+00:00"
    for tipo, chave in [("vence_hoje", "2026-11-17"), ("banco_desatualizado", "C6"), ("google_parado", "x"), ("convite_agenda", "y"),
                        ("servico_falhou", "gabi-brain-correio.service"), ("servico_falhou", "gabi-finance-api.service")]:
        con.execute("insert into aviso(tipo, payload, criado_em) values (?,?,?)", (tipo, json.dumps({"chave": chave}), agora))
    opc = lambda efeito: json.dumps([{"n": 1, "rotulo": "a", "efeito": efeito, "parametros": {}}])  # noqa: E731
    for titulo, opcoes, estado in [("email", opc("adicionar_canal_email"), "aberta"), ("nota", opc("registrar_nota"), "aberta"),
                                   ("velha", opc("adicionar_canal_email"), "respondida"), ("quebrada", "nao é json", "aberta"),
                                   ("mista", json.dumps([{"n": 1, "rotulo": "a", "efeito": "registrar_nota"}, {"n": 2, "rotulo": "b", "efeito": "x"}]), "aberta")]:
        con.execute("insert into pergunta(tipo, titulo, opcoes, estado, criada_em) values ('t', ?, ?, ?, ?)", (titulo, opcoes, estado, agora))
    con.execute("insert into pessoa(id, nome, telefone, dados) values ('carla','Carla','+5511900000001',?)",
                (json.dumps({"responsavel_por": ["giovanna"], "beneficiario": False, "cpf": "123", "email": "c@x.com"}),))
    con.execute("insert into pessoa(id, nome, telefone, dados) values ('ana','Ana','+5511900000002','{\"apelido\":\"Aninha\",\"nascimento\":\"2000-01-01\"}')")
    con.execute("insert into pessoa(id, nome, dados) values ('casa','Casa','{}')")
    con.execute("insert into pessoa(id, nome, dados) values ('lixo','Lixo','não é json')")
    con.execute("insert into pessoa(id, nome) values ('nulo','Nulo')")
    con.execute("insert into agenda_fonte(id, conta, provedor, estado) values (1,'a@x.com','google','sim'), (2,'b@x.com','google','nao')")
    futuro = (dt.date.today() + dt.timedelta(days=30)).isoformat()
    passado = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    for ext, fonte, dia, privado, status in [("ok", 1, futuro, 0, "confirmed"), ("passado", 1, passado, 0, "confirmed"), ("privado", 1, futuro, 1, None),
                                             ("cancelado", 1, futuro, 0, "cancelled"), ("fonte_nao", 2, futuro, 0, None)]:
        con.execute("insert into agenda_evento(fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local, titulo, link_reuniao, organizador_nome, resposta, "
                    "privado, status) values (?,?,?,?,?,?, 'Aluguel', 'https://meet/x', 'Fulano', 'accepted', ?, ?)", (fonte, ext, dia, dia, dia, dia, privado, status))
    con.execute("insert into parametro(chave, valor) values ('email.vips', '[\"a@x.com\"]'), ('avisos.antecedencia_dias', '5'), ('mcp.url', '\"https://brain\"')")

    assert migrar(con, MIGR) == ["0092_limpar_herdados.sql"]

    assert sorted((r[0], json.loads(r[1])["chave"]) for r in con.execute("select tipo, payload from aviso")) == [
        ("banco_desatualizado", "C6"), ("servico_falhou", "gabi-finance-api.service"), ("vence_hoje", "2026-11-17")]
    assert dict(con.execute("select titulo, estado from pergunta").fetchall()) == {
        "email": "expirada", "nota": "aberta", "velha": "respondida", "quebrada": "expirada", "mista": "expirada"}
    pessoas = {r[0]: (r[1], r[2]) for r in con.execute("select id, telefone, dados from pessoa")}
    assert all(t is None for t, _ in pessoas.values())
    assert json.loads(pessoas["carla"][1]) == {"responsavel_por": ["giovanna"], "beneficiario": False}
    assert pessoas["ana"][1] == "{}" and pessoas["casa"][1] == "{}" and pessoas["lixo"][1] == "{}" and pessoas["nulo"][1] is None
    assert [tuple(r) for r in con.execute("select externo_id, link_reuniao, organizador_nome, resposta, titulo from agenda_evento")] == [
        ("ok", None, None, None, "Aluguel")]
    assert dict(con.execute("select chave, valor from parametro").fetchall()) == {"avisos.antecedencia_dias": "5"}
    assert _nomes(con) == KEEP and con.execute("pragma foreign_key_check").fetchall() == []

    # o dinheiro continua lendo o que precisa: o responsável por uma filha ainda resolve o "para quem"
    from gabi.dinheiro.classificar import _responsavel
    assert _responsavel(con, {"valor_centavos": -100, "descricao_original": "PIX CARLA", "estabelecimento": ""}) == "giovanna"

    # idempotente: rodar o SQL inteiro de novo não muda nada
    antes = [[tuple(r) for r in con.execute(f"select * from {t} order by 1")] for t in ("aviso", "pergunta", "pessoa", "agenda_evento", "parametro")]
    from gabi.db import _instrucoes
    for instrucao in _instrucoes(_sql_0092()):
        con.execute(instrucao)
    assert [[tuple(r) for r in con.execute(f"select * from {t} order by 1")] for t in ("aviso", "pergunta", "pessoa", "agenda_evento", "parametro")] == antes


def test_a_0092_em_banco_novo_nao_falha(tmp_path):
    con = conectar(tmp_path / "n.db")
    assert "0092_limpar_herdados.sql" in migrar(con, MIGR)
    assert _nomes(con) == KEEP
