def test_fabrica_do_mcp_monta_o_paperless_do_ambiente(tmp_path, monkeypatch):
    from gabi.mcp.servidor import fabrica
    monkeypatch.setenv("GABI_BANCO", str(tmp_path / "g.db"))
    monkeypatch.setenv("PAPERLESS_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "t")
    assert fabrica().paperless is not None
    monkeypatch.delenv("PAPERLESS_TOKEN")
    assert fabrica().paperless is None


def test_fabrica_do_mcp_monta_o_graph_pela_ponte_so_com_socket(tmp_path, monkeypatch):
    from gabi.fontes.ponte import PonteGraph
    from gabi.mcp.servidor import fabrica
    monkeypatch.setenv("GABI_BANCO", str(tmp_path / "g.db"))
    monkeypatch.delenv("GABI_FONTES_SOCKET", raising=False)
    assert fabrica().graph is None
    monkeypatch.setenv("GABI_FONTES_SOCKET", str(tmp_path / "fontes.sock"))
    assert isinstance(fabrica().graph, PonteGraph)


def test_fabrica_do_mcp_monta_o_correio_pela_ponte_so_com_socket(tmp_path, monkeypatch):
    from gabi.fontes.ponte import PonteEmail
    from gabi.mcp.servidor import fabrica
    monkeypatch.setenv("GABI_BANCO", str(tmp_path / "g.db"))
    monkeypatch.delenv("GABI_FONTES_SOCKET", raising=False)
    assert fabrica().correio is None
    monkeypatch.setenv("GABI_FONTES_SOCKET", str(tmp_path / "fontes.sock"))
    correio = fabrica().correio
    assert set(correio) == {"google", "graph"} and all(isinstance(p, PonteEmail) for p in correio.values())
