import pytest

from gabi.fontes.mcpai import BASE, Cliente, ErroMcpAi, RotaDesconhecida, RotaProibida, chamar

CHAVE = "sk_live_SEGREDO_NAO_VAZAR_123"


class Post:
    """Transporte falso: devolve respostas em fila e registra o que foi pedido."""

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.pedidos = []

    def __call__(self, url, corpo, cabecalhos):
        self.pedidos.append((url, corpo, cabecalhos))
        return self.respostas.pop(0)


def _ok(result):
    return 200, {"ok": True, "tool": "x", "result": result}, {}


@pytest.mark.parametrize("rota", ["transactions/category", "connections/disconnect"])
def test_rotas_proibidas_nao_chegam_a_rede(rota):
    post = Post()
    with pytest.raises(RotaProibida):
        chamar(rota, {}, post=post, chave=CHAVE)
    assert post.pedidos == []


@pytest.mark.parametrize("ferramenta", ["openfinance_disconnect_bank", "openfinance_update_transaction_category"])
def test_ferramentas_proibidas_pelo_nome_tambem(ferramenta):
    post = Post()
    with pytest.raises(RotaProibida):
        Cliente(post=post, chave=CHAVE, dorme=lambda s: None)(ferramenta, {})
    assert post.pedidos == []


def test_ferramenta_desconhecida_e_recusada_sem_rede():
    post = Post()
    with pytest.raises(RotaDesconhecida):
        Cliente(post=post, chave=CHAVE, dorme=lambda s: None)("openfinance_inventada", {})
    assert post.pedidos == []


def test_envia_bearer_json_na_url_certa_e_devolve_result():
    post = Post(_ok({"connections": []}))
    r = chamar("connections/list", {}, post=post, chave=CHAVE)
    url, corpo, cab = post.pedidos[0]
    assert url == f"{BASE}/connections/list" and corpo == {}
    assert cab["Authorization"] == f"Bearer {CHAVE}" and cab["Content-Type"] == "application/json"
    assert r == {"connections": []}


def test_sem_chave_nao_chama_a_rede(monkeypatch):
    monkeypatch.delenv("MCPAI_KEY", raising=False)
    post = Post()
    with pytest.raises(ErroMcpAi) as e:
        chamar("connections/list", {}, post=post)
    assert e.value.codigo == "sem_chave" and post.pedidos == []


def test_chave_vem_da_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv("MCPAI_KEY", CHAVE)
    post = Post(_ok({}))
    chamar("provider/status", {}, post=post)
    assert post.pedidos[0][2]["Authorization"] == f"Bearer {CHAVE}"


def test_409_vira_nao_conectado_com_url_para_reconectar():
    post = Post((409, {"error": {"code": "not_connected", "message": "x", "connect_url": "https://mcp.ai/connect/abc"}}, {}))
    with pytest.raises(ErroMcpAi) as e:
        chamar("accounts/list", {}, post=post, chave=CHAVE)
    assert e.value.codigo == "nao_conectado" and e.value.connect_url == "https://mcp.ai/connect/abc"


@pytest.mark.parametrize("status,corpo,codigo", [
    (401, {"error": {"code": "unauthorized"}}, "nao_autenticado"),
    (403, {"error": {"code": "key_scope_mismatch"}}, "escopo_da_chave"),
    (402, {"error": {"code": "no_credits"}}, "sem_creditos"),
])
def test_erros_definitivos_nao_sao_repetidos(status, corpo, codigo):
    post = Post((status, corpo, {}), _ok({}))
    with pytest.raises(ErroMcpAi) as e:
        Cliente(post=post, chave=CHAVE, dorme=lambda s: None)("openfinance_list_accounts", {})
    assert e.value.codigo == codigo and len(post.pedidos) == 1


def test_429_respeita_retry_after_e_tenta_de_novo():
    esperas = []
    post = Post((429, {"error": {"code": "rate_limited"}}, {"Retry-After": "7"}), _ok({"ok": 1}))
    r = Cliente(post=post, chave=CHAVE, dorme=esperas.append)("openfinance_list_accounts", {})
    assert r == {"ok": 1} and len(post.pedidos) == 2
    assert 7 in esperas  # esperou o que o servidor pediu


def test_erro_no_corpo_com_retry_after_ms_e_repetido():
    esperas = []
    erro = (200, {"ok": False, "error": {"code": "busy", "message": "x", "details": {"retry_after_ms": 3000}}}, {})
    post = Post(erro, _ok({"v": 1}))
    assert Cliente(post=post, chave=CHAVE, dorme=esperas.append)("openfinance_list_accounts", {}) == {"v": 1}
    assert 3.0 in esperas


def test_5xx_e_repetido_e_depois_desiste_devolvendo_none():
    post = Post(*[(503, {}, {})] * 3)
    assert Cliente(post=post, chave=CHAVE, dorme=lambda s: None)("openfinance_list_accounts", {}, tent=3) is None
    assert len(post.pedidos) == 3


def test_falha_de_rede_e_repetida():
    class Cai:
        n = 0

        def __call__(self, *a):
            self.n += 1
            if self.n < 2:
                raise OSError("sem rede")
            return _ok({"v": 1})

    c = Cai()
    assert Cliente(post=c, chave=CHAVE, dorme=lambda s: None)("openfinance_list_accounts", {}) == {"v": 1}


def test_chave_nunca_aparece_em_erro():
    post = Post((401, {"error": {"code": "unauthorized", "message": f"chave {CHAVE} invalida"}}, {}))
    with pytest.raises(ErroMcpAi) as e:
        chamar("accounts/list", {}, post=post, chave=CHAVE)
    assert CHAVE not in str(e.value) and CHAVE not in repr(e.value)


def test_throttle_entre_chamadas_do_cliente():
    esperas = []
    post = Post(_ok({}), _ok({}))
    c = Cliente(post=post, chave=CHAVE, dorme=esperas.append, intervalo=1.2)
    c("openfinance_list_accounts", {})
    c("openfinance_list_accounts", {})
    assert esperas.count(1.2) == 2
