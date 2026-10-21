def test_fabrica_do_mcp_monta_o_paperless_do_ambiente(tmp_path, monkeypatch):
    from gabi.mcp.servidor import fabrica
    monkeypatch.setenv("GABI_BANCO", str(tmp_path / "g.db"))
    monkeypatch.setenv("PAPERLESS_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "t")
    assert fabrica().paperless is not None
    monkeypatch.delenv("PAPERLESS_TOKEN")
    assert fabrica().paperless is None
