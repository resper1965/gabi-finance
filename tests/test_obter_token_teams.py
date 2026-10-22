import os
import stat

import pytest

from gabi.fontes.graph_ness import LOGIN
from gabi.fontes.graph_ness_envios import ESCOPO_TEAMS
from tools import obter_token_teams as t

TENANT = "11111111-2222-3333-4444-555555555555"
CLIENTE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
REFRESH = "0.REFRESH-SECRETO-XYZ"


def _http(respostas, chamadas):
    it = iter(respostas)

    def http(url, corpo):
        chamadas.append((url, corpo))
        return next(it)
    return http


def test_pedir_codigo_usa_escopos_da_task_4_e_nao_manda_segredo():
    ch = []
    http = _http([(200, {"device_code": "D", "user_code": "U", "verification_uri": "https://microsoft.com/devicelogin", "interval": 5})], ch)
    r = t.pedir_codigo(http, TENANT, CLIENTE)
    assert r["user_code"] == "U"
    url, corpo = ch[0]
    assert url == f"{LOGIN}/{TENANT}/oauth2/v2.0/devicecode"
    assert corpo == {"client_id": CLIENTE, "scope": ESCOPO_TEAMS}


def test_pedir_codigo_recusado_levanta_systemexit_sem_texto_do_provedor():
    http = _http([(400, {"error": "invalid_client", "error_description": "segredo do provedor"})], [])
    with pytest.raises(SystemExit) as e:
        t.pedir_codigo(http, TENANT, CLIENTE)
    assert "segredo do provedor" not in str(e.value)


def test_esperar_token_pending_pending_ok():
    ch, sono = [], []
    http = _http([(400, {"error": "authorization_pending"}), (400, {"error": "authorization_pending"}),
                  (200, {"refresh_token": REFRESH, "access_token": "x"})], ch)
    assert t.esperar_token(http, TENANT, CLIENTE, "DEV", 5, sono.append) == REFRESH
    assert sono == [5, 5, 5] and len(ch) == 3
    url, corpo = ch[0]
    assert url == f"{LOGIN}/{TENANT}/oauth2/v2.0/token"
    assert corpo == {"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "client_id": CLIENTE, "device_code": "DEV"}


def test_esperar_token_slow_down_soma_5s():
    sono = []
    http = _http([(400, {"error": "slow_down"}), (200, {"refresh_token": REFRESH})], [])
    t.esperar_token(http, TENANT, CLIENTE, "DEV", 5, sono.append)
    assert sono == [5, 10]


def test_esperar_token_expirado_levanta_systemexit_sem_segredo():
    http = _http([(400, {"error": "expired_token", "error_description": "texto do provedor"})], [])
    with pytest.raises(SystemExit) as e:
        t.esperar_token(http, TENANT, CLIENTE, "DEV-SEGREDO", 5, lambda s: None)
    msg = str(e.value)
    assert "expired_token" in msg and "DEV-SEGREDO" not in msg and "texto do provedor" not in msg


def test_esperar_token_sem_refresh_levanta_systemexit():
    http = _http([(200, {"access_token": "x"})], [])
    with pytest.raises(SystemExit):
        t.esperar_token(http, TENANT, CLIENTE, "DEV", 5, lambda s: None)


def test_gravar_no_env_substitui_a_linha_e_preserva_o_resto_e_o_modo(tmp_path):
    env = tmp_path / "graph-ness.env"
    env.write_text(f"M365_TENANT_ID={TENANT}\nGRAPH_NESS_TEAMS_REFRESH=antigo\nM365_CLIENT_ID={CLIENTE}\n")
    env.chmod(0o600)
    t.gravar_no_env(env, REFRESH)
    assert env.read_text().splitlines() == [f"M365_TENANT_ID={TENANT}", f"M365_CLIENT_ID={CLIENTE}", f"GRAPH_NESS_TEAMS_REFRESH={REFRESH}"]
    assert stat.S_IMODE(os.stat(env).st_mode) == 0o600


def test_gravar_no_env_acrescenta_quando_nao_existe_a_linha(tmp_path):
    env = tmp_path / "g.env"
    env.write_text("A=1")
    env.chmod(0o640)
    t.gravar_no_env(env, REFRESH)
    assert env.read_text() == f"A=1\nGRAPH_NESS_TEAMS_REFRESH={REFRESH}\n"
    assert stat.S_IMODE(os.stat(env).st_mode) == 0o640


def _env(tmp_path):
    env = tmp_path / "g.env"
    env.write_text(f"M365_TENANT_ID = {TENANT}\nM365_CLIENT_ID={CLIENTE}\n")
    env.chmod(0o600)
    return env


def _http_fluxo():
    return _http([(200, {"device_code": "D", "user_code": "UC123", "verification_uri": "https://v/devicelogin", "interval": 1}),
                  (200, {"refresh_token": REFRESH})], [])


def test_main_sem_gravar_nao_escreve_e_imprime_a_linha(tmp_path, capsys):
    env = _env(tmp_path)
    antes = env.read_text()
    assert t.main(["--env", str(env)], http=_http_fluxo(), dormir=lambda s: None) == 0
    out = capsys.readouterr().out
    assert "UC123" in out and f"GRAPH_NESS_TEAMS_REFRESH={REFRESH}" in out
    assert env.read_text() == antes


def test_main_com_gravar_escreve_e_nao_mostra_o_token(tmp_path, capsys):
    env = _env(tmp_path)
    assert t.main(["--env", str(env), "--gravar"], http=_http_fluxo(), dormir=lambda s: None) == 0
    cap = capsys.readouterr()
    assert REFRESH not in cap.out + cap.err
    assert f"GRAPH_NESS_TEAMS_REFRESH={REFRESH}" in env.read_text()


def test_main_sem_ids_no_env_falha_com_codigo_2(tmp_path, capsys):
    env = tmp_path / "vazio.env"
    env.write_text("A=1\n")
    assert t.main(["--env", str(env)], http=_http([], []), dormir=lambda s: None) == 2
