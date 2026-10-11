import json
import os
import pathlib
import shutil
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.escuta.caixa import ingerir_spool, normalizar_telefone, registrar_remetente_visto

MIGR = Path(__file__).parent.parent.parent / "migrations"
AGORA = "2026-10-11T10:00:00"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def _msg(pasta, nome, **kw):
    pasta.mkdir(parents=True, exist_ok=True)
    d = {"id_externo": nome, "de": "5511912345678@s.whatsapp.net", "grupo": False, "id_grupo": None,
         "recebida_em": "2026-10-11T09:00:00", "texto": "oi", "anexo": None}
    d.update(kw)
    (pasta / f"{nome}.json").write_text(json.dumps(d))


def test_telefone_formatos_equivalentes():
    for bruto in ("5511912345678@s.whatsapp.net", "+55 11 91234-5678", "11912345678"):
        assert normalizar_telefone(bruto) == "+5511912345678"


def test_telefone_invalido_none():
    for bruto in ("", "abc", "123", "551191234567890123"):
        assert normalizar_telefone(bruto) is None


def test_ingerir_grava_uma_vez(con, tmp_path):
    pasta = tmp_path / "spool"
    _msg(pasta, "a1")
    assert ingerir_spool(con, pasta, AGORA) == 1
    assert not (pasta / "a1.json").exists() and not (pasta / "lidos").exists()   # C1: o json some do spool, sem lidos/
    _msg(pasta, "a1")                                                              # replay do mesmo id: deduplicado pelo id_externo
    assert ingerir_spool(con, pasta, AGORA) == 0 and not (pasta / "a1.json").exists()
    assert con.execute("select count(*) from escuta_msg").fetchone()[0] == 1
    assert con.execute("select estado from escuta_msg").fetchone()[0] == "nova"
    assert con.execute("select qtd from escuta_remetente").fetchone()[0] == 1


def test_grupo_marcado(con, tmp_path):
    pasta = tmp_path / "spool"
    _msg(pasta, "g1", grupo=True, id_grupo="123@g.us")
    ingerir_spool(con, pasta, AGORA)
    r = con.execute("select grupo, id_grupo from escuta_msg").fetchone()
    assert (r["grupo"], r["id_grupo"]) == (1, "123@g.us")
    assert con.execute("select count(*) from escuta_remetente").fetchone()[0] == 0


def test_bloqueado_nao_e_gravado(con, tmp_path):
    con.execute("insert into escuta_remetente(numero, estado, qtd) values ('+5511912345678','bloqueado',0)")
    pasta = tmp_path / "spool"
    _msg(pasta, "b1")
    assert ingerir_spool(con, pasta, AGORA) == 0
    assert con.execute("select count(*) from escuta_msg").fetchone()[0] == 0
    assert not (pasta / "b1.json").exists() and not (pasta / "lidos").exists()


def test_desconhecido_gravado_e_vira_pendente(con, tmp_path):
    pasta = tmp_path / "spool"
    _msg(pasta, "u1")
    assert ingerir_spool(con, pasta, AGORA) == 1
    r = con.execute("select estado, qtd from escuta_remetente where numero='+5511912345678'").fetchone()
    assert (r["estado"], r["qtd"]) == ("pendente", 1)


def test_malformado_vai_para_invalidos(con, tmp_path):
    pasta = tmp_path / "spool"
    _msg(pasta, "ok")
    (pasta / "a-ruim.json").write_text("{nao e json")
    _msg(pasta, "sem-campos")
    (pasta / "sem-campos.json").write_text(json.dumps({"id_externo": "x"}))
    assert ingerir_spool(con, pasta, AGORA) == 1
    assert (pasta / "invalidos" / "a-ruim.json").exists()
    assert (pasta / "invalidos" / "sem-campos.json").exists()


def test_anexo_caminho(con, tmp_path):
    pasta = tmp_path / "spool"
    _msg(pasta, "x1", anexo="foto.jpg")
    ingerir_spool(con, pasta, AGORA)
    assert con.execute("select anexo_caminho from escuta_msg").fetchone()[0] == str(pasta / "anexos" / "foto.jpg")


def test_visto_incrementa_e_nao_reabre_ignorado(con):
    registrar_remetente_visto(con, "+5511900000001", AGORA)
    registrar_remetente_visto(con, "+5511900000001", AGORA)
    r = con.execute("select estado, qtd from escuta_remetente").fetchone()
    assert (r["estado"], r["qtd"]) == ("pendente", 2)
    con.execute("update escuta_remetente set estado='ignorado'")
    registrar_remetente_visto(con, "+5511900000001", "2026-10-12T10:00:00")
    r = con.execute("select estado, qtd, vista_em from escuta_remetente").fetchone()
    assert (r["estado"], r["qtd"], r["vista_em"]) == ("ignorado", 3, "2026-10-12T10:00:00")


@pytest.mark.parametrize("anexo", ["../../x", "/etc/passwd", "a/b.jpg", "..", ".", "", "a\\b.jpg"])
def test_anexo_traversal_vai_para_invalidos(con, tmp_path, anexo):
    pasta = tmp_path / "spool"
    _msg(pasta, "t1", anexo=anexo)
    assert ingerir_spool(con, pasta, AGORA) == 0
    assert (pasta / "invalidos" / "t1.json").exists()
    assert con.execute("select count(*) from escuta_msg").fetchone()[0] == 0


@pytest.mark.parametrize("campo,valor", [("anexo", 5), ("anexo", ["a"]), ("texto", ["x"]), ("texto", {"a": 1}), ("id_grupo", ["g"])])
def test_tipo_errado_invalido_e_rodada_continua(con, tmp_path, campo, valor):
    pasta = tmp_path / "spool"
    _msg(pasta, "a-ruim", **{campo: valor})
    _msg(pasta, "b-ok")
    assert ingerir_spool(con, pasta, AGORA) == 1
    assert (pasta / "invalidos" / "a-ruim.json").exists()
    assert con.execute("select id_externo from escuta_msg").fetchone()[0] == "b-ok"


def test_bloqueado_vale_para_forma_whatsapp(con, tmp_path):
    con.execute("insert into escuta_remetente(numero, estado, qtd) values ('+5511912345678','bloqueado',0)")
    pasta = tmp_path / "spool"
    _msg(pasta, "w1", de="5511912345678@s.whatsapp.net")
    assert ingerir_spool(con, pasta, AGORA) == 0
    assert con.execute("select count(*) from escuta_msg").fetchone()[0] == 0


def test_json_tmp_do_ouvinte_e_ignorado(con, tmp_path):
    pasta = tmp_path / "spool"
    _msg(pasta, "x")
    (pasta / "x.json").rename(pasta / "x.json.tmp")
    assert ingerir_spool(con, pasta, AGORA) == 0
    assert (pasta / "x.json.tmp").exists() and not (pasta / "invalidos").exists()
    (pasta / "x.json.tmp").rename(pasta / "x.json")
    assert ingerir_spool(con, pasta, AGORA) == 1


def test_recebida_em_normalizada_para_utc(con, tmp_path):
    pasta = tmp_path / "spool"
    for nome, quando in (("a", "2026-10-11T09:00:00"), ("b", "2026-10-11T12:00:00Z"), ("c", "2026-10-11T12:00:00+00:00"), ("d", "2026-10-11T09:00:00-03:00")):
        _msg(pasta, nome, recebida_em=quando)
    assert ingerir_spool(con, pasta, AGORA) == 4
    assert {r[0] for r in con.execute("select recebida_em from escuta_msg")} == {"2026-10-11T12:00:00+00:00"}   # ingênuo = Brasília


def test_recebida_em_invalida_vai_para_invalidos(con, tmp_path):
    pasta = tmp_path / "spool"
    _msg(pasta, "z", recebida_em="ontem")
    assert ingerir_spool(con, pasta, AGORA) == 0 and (pasta / "invalidos" / "z.json").exists()


# ---- limpar_orfaos ----
def _velho(p, horas=48):
    import os, time
    t = time.time() - horas * 3600
    os.utime(p, (t, t), follow_symlinks=False)


def _spool_orfaos(tmp_path):
    pasta = tmp_path / "spool"
    (pasta / "anexos").mkdir(parents=True)
    con = conectar(tmp_path / "o.db")
    migrar(con, Path(__file__).parent.parent.parent / "migrations")
    return pasta, con


def test_limpar_orfaos_remove_so_orfao_antigo(tmp_path):
    from gabi.escuta.caixa import limpar_orfaos
    pasta, con = _spool_orfaos(tmp_path)
    orf, ref, novo = (pasta / "anexos" / n for n in ("orfao.pdf", "ref.pdf", "novo.pdf"))
    for a in (orf, ref, novo):
        a.write_bytes(b"x")
    _velho(orf); _velho(ref)
    con.execute("insert into escuta_msg(id_externo, de, grupo, recebida_em, anexo_caminho) values ('1','+5511912345678',0,'2026-10-11T10:00:00+00:00',?)", (str(ref),))
    assert limpar_orfaos(con, pasta) == 1
    assert not orf.exists() and ref.exists() and novo.exists()


def test_limpar_orfaos_nao_segue_symlink_nem_subpasta_nem_fora(tmp_path):
    from gabi.escuta.caixa import limpar_orfaos
    pasta, con = _spool_orfaos(tmp_path)
    fora = tmp_path / "fora.txt"
    fora.write_bytes(b"x"); _velho(fora)
    ln = pasta / "anexos" / "ln"
    ln.symlink_to(fora); _velho(ln)
    sub = pasta / "anexos" / "sub"
    sub.mkdir(); (sub / "dentro.pdf").write_bytes(b"x"); _velho(sub / "dentro.pdf"); _velho(sub)
    dirln = pasta / "anexos" / "dl"
    alvo = tmp_path / "alvo"; alvo.mkdir(); (alvo / "a.pdf").write_bytes(b"x"); _velho(alvo / "a.pdf")
    dirln.symlink_to(alvo, target_is_directory=True)
    assert limpar_orfaos(con, pasta) == 0
    assert fora.exists() and ln.is_symlink() and (sub / "dentro.pdf").exists() and (alvo / "a.pdf").exists() and dirln.is_symlink()


def test_limpar_orfaos_sem_pasta_anexos(tmp_path):
    from gabi.escuta.caixa import limpar_orfaos
    con = conectar(tmp_path / "o.db")
    migrar(con, Path(__file__).parent.parent.parent / "migrations")
    assert limpar_orfaos(con, tmp_path / "nada") == 0


# ---- listener comprometido: o brain não segue symlink nem abre FIFO no spool ----
def test_json_symlink_nao_e_lido_e_vai_para_invalidos(con, tmp_path):
    pasta = tmp_path / "spool"
    pasta.mkdir()
    vitima = tmp_path / "vitima.json"
    vitima.write_text(json.dumps({"id_externo": "VAZOU", "de": "5511912345678@s.whatsapp.net", "recebida_em": "2026-10-11T09:00:00+00:00", "texto": "segredo"}))
    (pasta / "x.json").symlink_to(vitima)
    assert ingerir_spool(con, pasta, AGORA) == 0
    assert con.execute("select count(*) from escuta_msg").fetchone()[0] == 0
    assert vitima.exists() and not (pasta / "x.json").exists() and (pasta / "invalidos" / "x.json").is_symlink()


def test_json_fifo_nao_trava_nem_e_lido(con, tmp_path):
    import os
    import signal
    pasta = tmp_path / "spool"
    pasta.mkdir()
    os.mkfifo(pasta / "f.json")
    signal.alarm(5)
    try:
        assert ingerir_spool(con, pasta, AGORA) == 0
    finally:
        signal.alarm(0)
    assert (pasta / "invalidos" / "f.json").exists()


def test_json_gigante_e_recusado(con, tmp_path):
    pasta = tmp_path / "spool"
    pasta.mkdir()
    (pasta / "g.json").write_bytes(b"[" + b"0," * (6 * 1024 * 1024) + b"0]")
    assert ingerir_spool(con, pasta, AGORA) == 0
    assert (pasta / "invalidos" / "g.json").exists()


def test_pasta_lidos_symlink_nao_recebe_arquivos_fora_do_spool(con, tmp_path):
    pasta = tmp_path / "spool"
    pasta.mkdir()
    fora = tmp_path / "fora"
    fora.mkdir()
    (pasta / "lidos").symlink_to(fora, target_is_directory=True)
    _msg(pasta, "a1")
    assert ingerir_spool(con, pasta, AGORA) == 1
    assert list(fora.iterdir()) == []
    assert not (pasta / "a1.json").exists()


def test_json_com_chave_extra_lid_e_aceito(con, tmp_path):
    pasta = tmp_path / "spool"
    _msg(pasta, "l1", de="123456789@lid", lid=True)
    assert ingerir_spool(con, pasta, AGORA) == 1
    assert con.execute("select de from escuta_msg").fetchone()[0] == "123456789@lid"


def test_limpar_orfaos_pasta_anexos_symlink_nao_apaga_fora(tmp_path):
    from gabi.escuta.caixa import limpar_orfaos
    pasta = tmp_path / "spool"
    pasta.mkdir()
    alvo = tmp_path / "dados-do-brain"
    alvo.mkdir()
    (alvo / "backup.db").write_bytes(b"x")
    _velho(alvo / "backup.db")
    (pasta / "anexos").symlink_to(alvo, target_is_directory=True)
    con = conectar(tmp_path / "o.db")
    migrar(con, MIGR)
    assert limpar_orfaos(con, pasta) == 0
    assert (alvo / "backup.db").exists()


def _vitima_dir(tmp_path):
    v = tmp_path / "dados-do-brain"
    v.mkdir()
    return v


@pytest.mark.parametrize("sub", ["lidos", "invalidos"])
def test_mover_troca_da_subpasta_por_symlink_depois_da_checagem_nao_escapa(con, tmp_path, monkeypatch, sub):
    """Corrida: o ouvinte troca lidos/invalidos por symlink DEPOIS de qualquer checagem por caminho, logo antes do rename."""
    pasta = tmp_path / "spool"
    vitima = _vitima_dir(tmp_path)
    if sub == "lidos":
        _msg(pasta, "a1")
    else:
        pasta.mkdir(exist_ok=True)
        (pasta / "a1.json").write_text("{quebrado")
    (pasta / sub).mkdir(exist_ok=True)

    real_rename = os.rename

    def troca():
        if os.path.islink(pasta / sub):
            return
        real_rename(pasta / sub, pasta / (sub + "-orig"))
        (pasta / sub).symlink_to(vitima, target_is_directory=True)

    def rename(*a, **k):  # e também logo antes do rename (código novo ancorado em fd)
        troca()
        return real_rename(*a, **k)
    monkeypatch.setattr(os, "rename", rename)
    monkeypatch.setattr(os, "replace", rename)
    ingerir_spool(con, pasta, AGORA)
    assert list(vitima.iterdir()) == []
    assert not (pasta / "a1.json").exists()


@pytest.mark.parametrize("sub", ["lidos", "invalidos"])
def test_subpasta_symlink_desde_o_inicio_apaga_o_json_e_nao_toca_a_vitima(con, tmp_path, sub):
    pasta = tmp_path / "spool"
    vitima = _vitima_dir(tmp_path)
    (vitima / "a1.json").write_text("ORIGINAL")
    pasta.mkdir()
    (pasta / sub).symlink_to(vitima, target_is_directory=True)
    if sub == "lidos":
        _msg(pasta, "a1")
    else:
        (pasta / "a1.json").write_text("{quebrado")
    ingerir_spool(con, pasta, AGORA)
    assert (vitima / "a1.json").read_text() == "ORIGINAL"
    assert not (pasta / "a1.json").exists()


def test_json_symlink_com_mesmo_nome_nunca_e_seguido_nem_movido_para_fora(con, tmp_path):
    pasta = tmp_path / "spool"
    pasta.mkdir()
    vitima = _vitima_dir(tmp_path)
    (vitima / "a1.json").write_text(json.dumps({"id_externo": "VAZOU", "de": "5511912345678@s.whatsapp.net", "recebida_em": "2026-10-11T09:00:00+00:00"}))
    (pasta / "a1.json").symlink_to(vitima / "a1.json")
    assert ingerir_spool(con, pasta, AGORA) == 0
    assert (vitima / "a1.json").exists() and con.execute("select count(*) from escuta_msg").fetchone()[0] == 0


def test_nao_cria_lidos_e_cria_invalidos_so_para_malformado(con, tmp_path):
    pasta = tmp_path / "spool"
    _msg(pasta, "ok")
    (pasta / "ruim.json").write_text("{")
    ingerir_spool(con, pasta, AGORA)
    assert not (pasta / "lidos").exists() and not (pasta / "ok.json").exists() and (pasta / "invalidos" / "ruim.json").is_file()


def test_nenhum_texto_de_mensagem_fica_no_spool_depois_da_ingestao(con, tmp_path):
    pasta = tmp_path / "spool"
    con.execute("insert into escuta_remetente(numero, estado, qtd) values ('+5511900000009','bloqueado',0)")
    _msg(pasta, "a", texto="SEGREDO-A")
    _msg(pasta, "b", texto="SEGREDO-B", de="5511900000009@s.whatsapp.net")
    _msg(pasta, "c", texto="SEGREDO-C", grupo=True, id_grupo="1@g.us")
    ingerir_spool(con, pasta, AGORA)
    for f in pasta.rglob("*"):
        if f.is_file():
            assert b"SEGREDO" not in f.read_bytes(), f.name


def test_limpar_orfaos_limpa_invalidos_antigos(tmp_path):
    from gabi.escuta.caixa import limpar_orfaos
    pasta, con = _spool_orfaos(tmp_path)
    inv = pasta / "invalidos"
    inv.mkdir()
    velho, novo = inv / "velho.json", inv / "novo.json"
    velho.write_text("{"); novo.write_text("{")
    _velho(velho)
    fora = tmp_path / "fora.json"
    fora.write_text("x"); _velho(fora)
    ln = inv / "ln.json"
    ln.symlink_to(fora); _velho(ln)
    sub = inv / "sub"
    sub.mkdir(); _velho(sub)
    limpar_orfaos(con, pasta)
    assert not velho.exists() and novo.exists() and not ln.is_symlink() and fora.exists() and sub.is_dir()


def test_limpar_orfaos_invalidos_symlink_nao_e_seguido(tmp_path):
    from gabi.escuta.caixa import limpar_orfaos
    pasta, con = _spool_orfaos(tmp_path)
    alvo = _vitima_dir(tmp_path)
    (alvo / "x.json").write_text("x"); _velho(alvo / "x.json")
    (pasta / "invalidos").symlink_to(alvo, target_is_directory=True)
    limpar_orfaos(con, pasta)
    assert (alvo / "x.json").exists()


# ---- I4: remetente que não vira telefone; celular antigo; I5: grupo visto ----
LID = "123456789012345@lid"


def test_i4_celular_antigo_ganha_o_nove_e_fixo_nao_muda():
    assert normalizar_telefone("551181234567@s.whatsapp.net") == "+5511981234567"
    assert normalizar_telefone("+55 11 8123-4567") == "+5511981234567"
    assert normalizar_telefone("551161234567") == "+5511961234567"
    for fixo in ("551131234567", "551121234567", "551151234567", "551141234567"):
        assert normalizar_telefone(fixo) == "+" + fixo


def test_i4_lid_nunca_vira_telefone():
    assert normalizar_telefone("11912345678@lid") is None and normalizar_telefone(LID) is None


def test_i4_remetente_cru_e_registrado(con, tmp_path):
    pasta = tmp_path / "spool"
    _msg(pasta, "l1", de=LID, lid=True)
    assert ingerir_spool(con, pasta, AGORA) == 1
    r = con.execute("select numero, estado, qtd from escuta_remetente").fetchone()
    assert (r["numero"], r["estado"], r["qtd"]) == (LID, "pendente", 1)
    assert con.execute("select de from escuta_msg").fetchone()[0] == LID


def test_i4_bloqueado_pelo_id_cru_nao_entra(con, tmp_path):
    con.execute("insert into escuta_remetente(numero, estado, qtd) values (?,'bloqueado',0)", (LID,))
    pasta = tmp_path / "spool"
    _msg(pasta, "l1", de=LID, lid=True)
    assert ingerir_spool(con, pasta, AGORA) == 0
    assert con.execute("select count(*) from escuta_msg").fetchone()[0] == 0


def test_i5_grupo_visto_entra_em_escuta_grupo_nao_aprovado(con, tmp_path):
    pasta = tmp_path / "spool"
    _msg(pasta, "g1", grupo=True, id_grupo="123@g.us", de="5511900000001@s.whatsapp.net")
    _msg(pasta, "g2", grupo=True, id_grupo="123@g.us", de="5511900000002@s.whatsapp.net")
    ingerir_spool(con, pasta, AGORA)
    assert [tuple(r) for r in con.execute("select id_grupo, nome, aprovado from escuta_grupo")] == [("123@g.us", None, 0)]
