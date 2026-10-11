"""Comparador do paralelo da escuta: fixtures sintéticas (números e textos inventados; o agente antigo só tem nome)."""
import json
import os
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from tools.comparar_escuta import comparar, main, mascarar

MIGR = Path(__file__).parent.parent / "migrations"
NUM = "+5511987655678"


@pytest.fixture
def banco(tmp_path):
    p = tmp_path / "t.db"
    c = conectar(p)
    migrar(c, MIGR)
    c.close()
    return p


@pytest.fixture
def fila(tmp_path):
    p = tmp_path / "fila"
    (p / "feitas").mkdir(parents=True)
    return p


def _msg(banco, tipo, de=NUM, quando="2026-10-05T15:00:00+00:00", n=[0]):
    n[0] += 1
    c = conectar(banco)
    c.execute("insert into escuta_msg(id_externo, de, recebida_em, estado, tipo) values (?,?,?,?,?)",
              (f"x{n[0]}{os.urandom(3).hex()}", de, quando, "processada", tipo))
    c.commit()
    c.close()


def _nome(banco, nome="Fulano Teste", numero=NUM):
    c = conectar(banco)
    c.execute("insert into escuta_remetente(numero, nome, estado) values (?,?, 'aprovado')", (numero, nome))
    c.commit()
    c.close()


def _pista(fila, quem="Fulano Teste", em="2026-10-05T12:00:00-03:00", nome="pista-aa.json", sub=""):
    (fila / sub / nome).write_text(json.dumps({"quem": quem, "criado_em": em, "caso": "consulta"}))


def _aviso(fila, texto, em="2026-10-05T12:00:00-03:00", nome="aviso-bb.json", sub="feitas"):
    (fila / sub / nome).write_text(json.dumps({"texto": texto, "criado_em": em}))


def _rodar(banco, fila, **kw):
    con = conectar(banco)
    try:
        return comparar(con, fila, **kw)
    finally:
        con.close()


def test_igual_nao_gera_divergencia(banco, fila):
    _nome(banco)
    _msg(banco, "saude")
    _pista(fila)
    r = _rodar(banco, fila)
    assert r.divergencias == [] and r.ilegiveis == 0


def test_so_um_lado_e_reportado(banco, fila):
    _nome(banco)
    _msg(banco, "pedido")
    _pista(fila, em="2026-10-06T12:00:00-03:00")
    r = _rodar(banco, fila)
    assert sorted(d["divergencia"] for d in r.divergencias) == ["so_no_agente", "so_no_brain"]


def test_tipo_diferente_mostra_os_dois(banco, fila):
    _nome(banco)
    _msg(banco, "pedido")
    _pista(fila)
    r = _rodar(banco, fila)
    assert len(r.divergencias) == 1
    d = r.divergencias[0]
    assert d["divergencia"] == "tipo_diferente" and d["brain"] == ["pedido"] and d["agente"] == ["saude"]


def test_aviso_de_pedido_e_de_crise_do_agente(banco, fila):
    _nome(banco)
    _msg(banco, "pedido")
    _msg(banco, "crise")
    _aviso(fila, "💸 Pedido de Fulano Teste — R$ 10,00 — falta a chave Pix")
    _aviso(fila, "🚨 vida: Fulano Teste — “trecho”", nome="aviso-cc.json")
    assert _rodar(banco, fila).divergencias == []


def test_numeros_em_formatos_diferentes_se_normalizam(banco, fila):
    _msg(banco, "crise", de="+5511987655678")
    _aviso(fila, "🚨 seguranca: +55 (11) 98765-5678 — “t”")
    assert _rodar(banco, fila).divergencias == []


def test_tipo_nada_e_ignorado(banco, fila):
    _msg(banco, "nada")
    c = conectar(banco)
    c.execute("insert into escuta_msg(id_externo, de, recebida_em) values ('s1', ?, '2026-10-05T15:00:00+00:00')", (NUM,))
    c.commit()
    c.close()
    assert _rodar(banco, fila).divergencias == []


def test_formato_desconhecido_e_contado_sem_quebrar(banco, fila):
    (fila / "pista-x.json").write_text("{não é json")
    (fila / "cmd-y.json").write_text(json.dumps({"qualquer": 1}))
    _aviso(fila, "texto que não é de escuta", nome="aviso-z.json")
    (fila / "feitas" / "aviso-w.json").write_text(json.dumps([1, 2]))
    r = _rodar(banco, fila)
    assert r.ilegiveis == 4 and r.divergencias == []


def test_desde_filtra_os_dois_lados(banco, fila):
    _nome(banco)
    _msg(banco, "pedido", quando="2026-10-01T15:00:00+00:00")
    _pista(fila, em="2026-10-01T12:00:00-03:00")
    assert len(_rodar(banco, fila).divergencias) == 1
    assert _rodar(banco, fila, desde="2026-10-02").divergencias == []


def test_dia_e_em_brasilia(banco, fila):
    _nome(banco)
    _msg(banco, "saude", quando="2026-10-06T01:30:00+00:00")  # 05/10 22:30 BRT
    _pista(fila, em="2026-10-05T22:35:00")                    # sem fuso = BRT
    assert _rodar(banco, fila).divergencias == []


def test_nome_sem_numero_conhecido_vira_so_no_agente(banco, fila):
    _pista(fila, quem="Ninguem Conhecido")
    r = _rodar(banco, fila)
    assert [d["divergencia"] for d in r.divergencias] == ["so_no_agente"] and r.divergencias[0]["remetente"] == "?"


def test_mascara_do_numero():
    assert mascarar("+5511987655678") == "+55119****5678"
    assert "?" == mascarar(None)


def test_saida_sem_texto_nem_numero_completo(banco, fila, capsys):
    _nome(banco)
    _msg(banco, "pedido")
    rc = main(["--banco", str(banco), "--fila-antiga", str(fila)])
    out = capsys.readouterr().out
    assert rc == 1 and "+55119****5678" in out and NUM not in out and "Fulano" not in out
    assert "so_no_brain=1" in out and "total" in out


def test_sem_divergencia_sai_zero(banco, fila, capsys):
    assert main(["--banco", str(banco), "--fila-antiga", str(fila)]) == 0


def test_banco_e_aberto_somente_leitura(banco, fila):
    _nome(banco)
    _msg(banco, "pedido")
    antes = banco.read_bytes()
    main(["--banco", str(banco), "--fila-antiga", str(fila)])
    assert banco.read_bytes() == antes
    from tools.comparar_escuta import abrir_somente_leitura
    con = abrir_somente_leitura(banco)
    with pytest.raises(Exception):
        con.execute("delete from escuta_msg")
    con.close()


def test_fila_inexistente_e_erro_claro(banco, tmp_path, capsys):
    assert main(["--banco", str(banco), "--fila-antiga", str(tmp_path / "nao")]) == 2
