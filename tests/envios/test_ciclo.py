import datetime as dt
import json

from tests.envios.test_propostas import AGORA, NESS, _agenda, _codigo, _evento, con  # noqa: F401

from gabi.envios import propostas as p


def _ligar(con):
    con.execute("insert into parametro(chave, valor) values ('envios.escrita', ?) on conflict(chave) do update set valor=excluded.valor", (json.dumps("ligado"),))


def _estado(con, id):
    return con.execute("select * from envio_proposta where id=?", (id,)).fetchone()


def test_listar_marca_vencidas(con):
    _agenda(con)
    r = _evento(con, inicio="2026-10-22T12:00")  # vence 12:00 BRT
    assert [x["id"] for x in p.listar(con, AGORA)] == [r["id"]]
    depois = AGORA + dt.timedelta(hours=3)
    assert p.listar(con, depois) == []
    assert _estado(con, r["id"])["estado"] == "vencida"
    item = p.listar(con, depois, estado="decididas")[0]
    assert item["id"] == r["id"] and item["estado"] == "vencida" and isinstance(item["conteudo"], dict)
    assert set(item) == {"id", "tipo", "conta", "conteudo", "hash", "estado", "motivo", "criada_em", "vence_em", "decidida_em", "enviada_em"}


def test_listar_decididas_20_mais_recentes(con):
    _agenda(con)
    ids = [_evento(con)["id"] for _ in range(22)]
    for i, id in enumerate(ids):
        p.recusar(con, id, "ricardo", AGORA + dt.timedelta(minutes=i))
    lista = p.listar(con, AGORA, estado="decididas")
    assert len(lista) == 20 and lista[0]["id"] == ids[-1]


def test_recusar_so_pendente(con):
    _agenda(con)
    r = _evento(con)
    p.recusar(con, r["id"], "ricardo", AGORA)
    l = _estado(con, r["id"])
    assert l["estado"] == "recusada" and l["decidida_por"] == "ricardo" and l["decidida_em"]
    assert _codigo(p.recusar, con, r["id"], "ricardo", AGORA).codigo == "conflito"
    assert _codigo(p.recusar, con, 999, "ricardo", AGORA).codigo == "nao_encontrado"


def test_reservar_hash_diferente(con):
    _agenda(con)
    _ligar(con)
    r = _evento(con)
    assert _codigo(p.reservar, con, r["id"], "x" * 64, "ricardo", AGORA).codigo == "hash_diferente"
    assert _estado(con, r["id"])["estado"] == "pendente"


def test_reservar_ok_grava_quem_e_quando(con):
    _agenda(con)
    _ligar(con)
    r = _evento(con)
    h = _estado(con, r["id"])["hash"]
    linha = p.reservar(con, r["id"], h, "ricardo", AGORA)
    assert linha["estado"] == "enviando" and linha["decidida_por"] == "ricardo" and linha["decidida_em"]
    assert _estado(con, r["id"])["estado"] == "enviando"


def test_reservar_nao_encontrado_e_vencida(con):
    _agenda(con)
    _ligar(con)
    assert _codigo(p.reservar, con, 999, "h", "ricardo", AGORA).codigo == "nao_encontrado"
    r = _evento(con, inicio="2026-10-22T12:00")
    h = _estado(con, r["id"])["hash"]
    assert _codigo(p.reservar, con, r["id"], h, "ricardo", AGORA + dt.timedelta(hours=4)).codigo == "vencida"
    assert _estado(con, r["id"])["estado"] == "vencida"


def test_reservar_desligado_nao_muda_estado(con):
    _agenda(con)
    r = _evento(con)
    h = _estado(con, r["id"])["hash"]
    assert _codigo(p.reservar, con, r["id"], h, "ricardo", AGORA).codigo == "envios_desligados"
    assert _estado(con, r["id"])["estado"] == "pendente"


def test_reservar_duas_vezes_segunda_e_conflito(con):
    _agenda(con)
    _ligar(con)
    r = _evento(con)
    h = _estado(con, r["id"])["hash"]
    p.reservar(con, r["id"], h, "ricardo", AGORA)
    assert _codigo(p.reservar, con, r["id"], h, "ricardo", AGORA).codigo == "conflito"


def test_reservar_conta_removida_da_lista_vira_falhou(con):
    _agenda(con)
    _ligar(con)
    r = _evento(con)
    h = _estado(con, r["id"])["hash"]
    con.execute("update parametro set valor='[]' where chave='envios.contas_agenda'")
    assert _codigo(p.reservar, con, r["id"], h, "ricardo", AGORA).codigo == "conta_nao_permitida"
    l = _estado(con, r["id"])
    assert l["estado"] == "falhou" and l["motivo"] == "conta_nao_permitida"


def test_ligar_depois_de_criar_permite_enviar(con):
    _agenda(con)
    r = _evento(con)  # criada com a escrita desligada
    h = _estado(con, r["id"])["hash"]
    assert _codigo(p.reservar, con, r["id"], h, "ricardo", AGORA).codigo == "envios_desligados"
    _ligar(con)
    assert p.reservar(con, r["id"], h, "ricardo", AGORA)["estado"] == "enviando"


def test_concluir(con):
    _agenda(con)
    _ligar(con)
    r = _evento(con)
    p.reservar(con, r["id"], _estado(con, r["id"])["hash"], "ricardo", AGORA)
    p.concluir(con, r["id"], "enviada", externo_id="abc", agora=AGORA)
    l = _estado(con, r["id"])
    assert l["estado"] == "enviada" and l["externo_id"] == "abc" and l["enviada_em"]
    assert _codigo(p.concluir, con, r["id"], "enviada", agora=AGORA).codigo == "conflito"
    assert _codigo(p.concluir, con, r["id"], "recusada", agora=AGORA).codigo == "requisicao_invalida"


def test_concluir_falhou_com_motivo(con):
    _agenda(con)
    _ligar(con)
    r = _evento(con)
    p.reservar(con, r["id"], _estado(con, r["id"])["hash"], "ricardo", AGORA)
    p.concluir(con, r["id"], "falhou", motivo="provedor_indisponivel", agora=AGORA)
    l = _estado(con, r["id"])
    assert l["estado"] == "falhou" and l["motivo"] == "provedor_indisponivel" and l["enviada_em"] is None


def test_auditoria_sem_conteudo(con):
    _agenda(con)
    _ligar(con)
    r = _evento(con, titulo="Segredo Titular", descricao="texto sigiloso")
    p.reservar(con, r["id"], _estado(con, r["id"])["hash"], "ricardo", AGORA)
    p.concluir(con, r["id"], "enviada", agora=AGORA)
    r2 = _evento(con, titulo="Outro Segredo")
    p.recusar(con, r2["id"], "ricardo", AGORA)
    linhas = con.execute("select quem, o_que, origem from decisao").fetchall()
    assert len(linhas) >= 3 and all(l["origem"] == "envios" for l in linhas)
    todo = " ".join(l["o_que"] for l in linhas)
    for proibido in ("Segredo", "sigiloso", "ana@x.com", "Reunião"):
        assert proibido not in todo
    assert str(r["id"]) in todo and NESS in todo
