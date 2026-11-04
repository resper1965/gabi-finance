import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest

from tools import obter_token_google as t

SEGREDO = "CLIENT-SECRET-XYZ"


@pytest.fixture(autouse=True)
def _sem_env_real(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "ENV_PADRAO", str(tmp_path / "padrao-inexistente.env"))  # nunca lê o /etc/gabi/google.env de verdade
TOKEN = "1//refresh-token-123"


def test_pkce_o_desafio_e_o_hash_do_verificador():
    verificador, desafio = t.pkce()
    assert 43 <= len(verificador) <= 128
    esperado = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    assert desafio == esperado


def test_url_de_consentimento_pede_offline_consentimento_e_os_tres_escopos():
    q = parse_qs(urlparse(t.url_de_consentimento("cid.apps", "DESAFIO", "estado1")).query)
    assert q["client_id"] == ["cid.apps"] and q["response_type"] == ["code"] and q["access_type"] == ["offline"] and q["prompt"] == ["consent"]
    assert q["code_challenge"] == ["DESAFIO"] and q["code_challenge_method"] == ["S256"] and q["state"] == ["estado1"] and q["redirect_uri"] == [t.REDIRECT]
    assert set(q["scope"][0].split()) == set(t.ESCOPOS) and len(t.ESCOPOS) == 4
    assert "https://www.googleapis.com/auth/calendar.events" in t.ESCOPOS
    assert "gmail.modify" in q["scope"][0] and "calendar.readonly" in q["scope"][0] and "contacts.readonly" in q["scope"][0]


def test_extrai_o_codigo_da_url_final_ou_do_codigo_puro():
    assert t.extrair_codigo("http://localhost:8765/?state=e1&code=4%2F0AbC&scope=x", "e1") == "4/0AbC"
    assert t.extrair_codigo("  4/0AbC-def  ", "e1") == "4/0AbC-def"


@pytest.mark.parametrize("texto", ["http://localhost:8765/?state=OUTRO&code=abc", "http://localhost:8765/?state=e1&error=access_denied", "http://localhost:8765/?state=e1", "", "   "])
def test_url_com_estado_errado_erro_ou_sem_codigo_e_recusada(texto):
    with pytest.raises(ValueError):
        t.extrair_codigo(texto, "e1")


def test_troca_o_codigo_pelo_token_com_o_verificador_e_o_segredo_so_no_corpo():
    chamadas = []

    def http(url, corpo):
        chamadas.append((url, corpo))
        return 200, {"refresh_token": TOKEN, "scope": " ".join(t.ESCOPOS)}
    r = t.trocar("cid.apps", SEGREDO, "4/0AbC", "VERIF", http=http)
    assert r["refresh_token"] == TOKEN and chamadas[0][0] == "https://oauth2.googleapis.com/token"
    c = chamadas[0][1]
    assert c["grant_type"] == "authorization_code" and c["code"] == "4/0AbC" and c["code_verifier"] == "VERIF" and c["client_secret"] == SEGREDO and c["redirect_uri"] == t.REDIRECT


def test_erro_do_google_vira_mensagem_so_com_o_codigo_do_erro():
    with pytest.raises(ValueError) as e:
        t.trocar("cid.apps", SEGREDO, "x", "v", http=lambda u, c: (400, {"error": "invalid_grant", "error_description": "Bad Request"}))
    assert "invalid_grant" in str(e.value) and SEGREDO not in str(e.value)


def test_conferir_acusa_escopo_faltando_e_token_ausente():
    ok = {"refresh_token": TOKEN, "scope": " ".join(t.ESCOPOS)}
    assert t.conferir(ok) == (TOKEN, [])
    falta = {"refresh_token": TOKEN, "scope": "https://www.googleapis.com/auth/calendar.readonly"}
    assert t.conferir(falta)[1] == sorted(set(t.ESCOPOS) - {"https://www.googleapis.com/auth/calendar.readonly"})
    with pytest.raises(ValueError):
        t.conferir({"scope": " ".join(t.ESCOPOS)})  # sem refresh token (não veio offline)


def test_main_imprime_a_linha_do_env_sem_o_segredo_e_nao_grava_arquivo(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    respostas = iter(["cid.apps", "http://localhost:8765/?state=ESTADO&code=4%2F0AbC"])
    monkeypatch.setattr(t, "_estado", lambda: "ESTADO")
    rc = t.main(["resper@gmail.com"], entrada=lambda p="": next(respostas), segredo=lambda p="": SEGREDO,
                http=lambda u, c: (200, {"refresh_token": TOKEN, "scope": " ".join(t.ESCOPOS)}))
    saida = capsys.readouterr()
    assert rc == 0 and f"GOOGLE_REFRESH_RESPER_GMAIL_COM={TOKEN}" in saida.out
    assert SEGREDO not in saida.out + saida.err and list(tmp_path.iterdir()) == []


def test_main_com_escopo_faltando_avisa_e_sai_com_erro(monkeypatch, capsys):
    respostas = iter(["cid.apps", "http://localhost:8765/?state=ESTADO&code=abc"])
    monkeypatch.setattr(t, "_estado", lambda: "ESTADO")
    rc = t.main(["resper@gmail.com"], entrada=lambda p="": next(respostas), segredo=lambda p="": SEGREDO,
                http=lambda u, c: (200, {"refresh_token": TOKEN, "scope": "https://www.googleapis.com/auth/calendar.readonly"}))
    saida = capsys.readouterr()
    assert rc == 1 and "faltou" in saida.err.lower() and "gmail.modify" in saida.err and TOKEN not in saida.out


def test_main_recusa_conta_invalida_sem_pedir_nada(capsys):
    assert t.main(["isto-nao-e-email"], entrada=lambda p="": pytest.fail("não deveria perguntar"), segredo=lambda p="": pytest.fail("não deveria perguntar")) == 2
    assert t.main([]) == 2


def test_main_erro_na_troca_nao_imprime_segredo(monkeypatch, capsys):
    respostas = iter(["cid.apps", "http://localhost:8765/?state=ESTADO&code=abc"])
    monkeypatch.setattr(t, "_estado", lambda: "ESTADO")
    rc = t.main(["resper@gmail.com"], entrada=lambda p="": next(respostas), segredo=lambda p="": SEGREDO, http=lambda u, c: (400, {"error": "invalid_client"}))
    saida = capsys.readouterr()
    assert rc == 1 and "invalid_client" in saida.err and SEGREDO not in saida.out + saida.err


# ---- cliente lido de /etc/gabi/google.env e token gravado lá (--gravar) ----
def _env(tmp_path, texto="GOOGLE_CLIENT_ID=cid.apps\nGOOGLE_CLIENT_SECRET=" + SEGREDO + "\nOUTRA=1\n"):
    p = tmp_path / "google.env"
    p.write_text(texto)
    p.chmod(0o600)
    return p


def test_le_o_cliente_do_arquivo_e_ignora_o_resto(tmp_path):
    assert t.cliente_do_arquivo(_env(tmp_path)) == ("cid.apps", SEGREDO)
    assert t.cliente_do_arquivo(tmp_path / "nao-existe.env") is None
    assert t.cliente_do_arquivo(_env(tmp_path, "GOOGLE_CLIENT_ID=so-o-id\n")) is None  # incompleto: cai no pedido interativo


def test_main_usa_o_cliente_do_arquivo_sem_perguntar_id_nem_segredo(tmp_path, monkeypatch, capsys):
    env = _env(tmp_path)
    respostas = iter(["http://localhost:8765/?state=ESTADO&code=abc"])
    monkeypatch.setattr(t, "_estado", lambda: "ESTADO")
    rc = t.main(["resper@gmail.com", "--env", str(env)], entrada=lambda p="": next(respostas), segredo=lambda p="": pytest.fail("não deveria pedir o segredo"),
                http=lambda u, c: (200, {"refresh_token": TOKEN, "scope": " ".join(t.ESCOPOS)}) if c["client_secret"] == SEGREDO else (400, {"error": "invalid_client"}))
    assert rc == 0 and f"GOOGLE_REFRESH_RESPER_GMAIL_COM={TOKEN}" in capsys.readouterr().out


def test_gravar_acrescenta_a_linha_sem_imprimir_o_token_e_mantem_o_modo(tmp_path, monkeypatch, capsys):
    env = _env(tmp_path)
    respostas = iter(["http://localhost:8765/?state=ESTADO&code=abc"])
    monkeypatch.setattr(t, "_estado", lambda: "ESTADO")
    rc = t.main(["resper@gmail.com", "--env", str(env), "--gravar"], entrada=lambda p="": next(respostas), segredo=lambda p="": pytest.fail("x"),
                http=lambda u, c: (200, {"refresh_token": TOKEN, "scope": " ".join(t.ESCOPOS)}))
    saida = capsys.readouterr()
    assert rc == 0 and TOKEN not in saida.out + saida.err and "GOOGLE_REFRESH_RESPER_GMAIL_COM" in saida.out
    linhas = env.read_text().splitlines()
    assert f"GOOGLE_REFRESH_RESPER_GMAIL_COM={TOKEN}" in linhas and "OUTRA=1" in linhas and oct(env.stat().st_mode & 0o777) == "0o600"


def test_gravar_substitui_o_token_da_mesma_conta_sem_duplicar(tmp_path, monkeypatch):
    env = _env(tmp_path, "GOOGLE_CLIENT_ID=cid.apps\nGOOGLE_CLIENT_SECRET=" + SEGREDO + "\nGOOGLE_REFRESH_RESPER_GMAIL_COM=velho\nGOOGLE_REFRESH_OUTRA_CONTA_COM=fica\n")
    t.gravar_token(env, "resper@gmail.com", "novo")
    linhas = env.read_text().splitlines()
    assert linhas.count("GOOGLE_REFRESH_RESPER_GMAIL_COM=novo") == 1 and "GOOGLE_REFRESH_RESPER_GMAIL_COM=velho" not in linhas and "GOOGLE_REFRESH_OUTRA_CONTA_COM=fica" in linhas


def test_gravar_sem_permissao_de_escrita_falha_sem_perder_o_token_na_tela(tmp_path, monkeypatch, capsys):
    respostas = iter(["cid.apps", "http://localhost:8765/?state=ESTADO&code=abc"])
    monkeypatch.setattr(t, "_estado", lambda: "ESTADO")
    rc = t.main(["resper@gmail.com", "--env", str(tmp_path / "pasta-inexistente" / "google.env"), "--gravar"], entrada=lambda p="": next(respostas), segredo=lambda p="": SEGREDO,
                http=lambda u, c: (200, {"refresh_token": TOKEN, "scope": " ".join(t.ESCOPOS)}))
    saida = capsys.readouterr()
    assert rc == 1 and "não consegui gravar" in saida.err.lower() and f"GOOGLE_REFRESH_RESPER_GMAIL_COM={TOKEN}" in saida.out  # o token não se perde
