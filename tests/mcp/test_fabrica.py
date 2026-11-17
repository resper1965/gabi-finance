def test_fabrica_do_mcp_nao_monta_fontes_de_fora_do_financeiro(tmp_path, monkeypatch):
    """O MCP do gabi-finance não fala com Paperless, Graph nem correio: a fábrica só abre o banco, migra e monta o servidor."""
    from gabi.mcp.servidor import fabrica
    monkeypatch.setenv("GABI_BANCO", str(tmp_path / "g.db"))
    monkeypatch.setenv("GABI_FONTES_SOCKET", str(tmp_path / "fontes.sock"))
    monkeypatch.setenv("PAPERLESS_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "t")
    app = fabrica()
    assert not any(hasattr(app, n) for n in ("paperless", "graph", "correio"))
    assert app.servidor is not None
