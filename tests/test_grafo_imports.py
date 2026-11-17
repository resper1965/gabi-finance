from tools.grafo_imports import analisar


def _pacote(tmp_path, arquivos):
    raiz = tmp_path / "pkg"
    raiz.mkdir()
    (raiz / "__init__.py").write_text("")
    for nome, corpo in arquivos.items():
        (raiz / nome).write_text(corpo)
    return raiz


def test_fecho_e_saem(tmp_path):
    raiz = _pacote(tmp_path, {
        "a.py": "from pkg import b\n", "b.py": "",
        "c.py": "import pkg.a\nimport pkg.d\n", "d.py": "",
    })
    fecho, fora, costuras = analisar(raiz, ["pkg.a"])
    assert set(fecho) == {"pkg", "pkg.a", "pkg.b"}
    assert set(fora) == {"pkg.c", "pkg.d"}
    assert costuras == []


def test_costura_com_arquivo_e_linha(tmp_path):
    raiz = _pacote(tmp_path, {
        "a.py": "x = 1\nfrom pkg.b import f\n", "b.py": "def f(): pass\n",
    })
    fecho, fora, costuras = analisar(raiz, ["pkg.a"], ["pkg.b"])
    assert "pkg.b" not in fecho and "pkg.b" in fora
    assert costuras == [("pkg.a", "pkg.b", f"{raiz / 'a.py'}:2")]


def test_import_relativo_e_importacao_tardia(tmp_path):
    raiz = _pacote(tmp_path, {
        "a.py": "def f():\n    from . import b\n", "b.py": "",
    })
    fecho, _, _ = analisar(raiz, ["pkg.a"])
    assert "pkg.b" in fecho
