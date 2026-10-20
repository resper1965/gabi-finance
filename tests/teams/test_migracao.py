from pathlib import Path

from gabi.db import conectar, migrar

PERMITIDAS = {
    "teams_fonte": {"id", "conta", "estado", "coletada_em", "ultimo_erro"},
    "teams_conversa": {"conta", "chat_id", "tipo", "de_nome", "ultima_para_mim_em", "minha_ultima_resposta_em", "ultimo_aviso_em", "cursor"},
}


def test_tabelas_sem_coluna_de_texto(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, Path(__file__).parent.parent.parent / "migrations")
    for tabela, ok in PERMITIDAS.items():
        cols = {r[1] for r in c.execute(f"pragma table_info({tabela})")}
        assert cols and cols <= ok, tabela
