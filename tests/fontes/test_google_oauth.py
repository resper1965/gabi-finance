import pytest

from gabi.fontes import google_contatos as gc
from gabi.fontes import google_oauth as go

SEGREDO = "refresh-SEGREDO-123"


def _troca(chamadas, resp=None, status=200):
    def http(m, url, corpo=None, cab=None):
        chamadas.append((m, url, corpo))
        return status, resp if resp is not None else {"access_token": "ACC", "expires_in": 3600}
    return http


def test_token_troca_refresh_e_cacheia():
    chamadas = []
    t = go.TokenOAuth("cid", "csec", {"GOOGLE_REFRESH_A_GMAIL_COM": SEGREDO}, http=_troca(chamadas), relogio=lambda: 0.0)
    assert t("a@gmail.com") == "ACC" and t("a@gmail.com") == "ACC"
    assert len(chamadas) == 1 and chamadas[0][0] == "POST" and b"refresh_token" in chamadas[0][2]


def test_token_sem_refresh_da_conta_nao_autorizada_so_com_o_nome_da_conta():
    t = go.TokenOAuth("cid", "csec", {}, http=_troca([]))
    with pytest.raises(go.ErroGoogleOAuth) as e:
        t("a@gmail.com")
    assert str(e.value) == "conta não autorizada: a@gmail.com"


def test_400_do_token_vira_token_recusado_sem_segredo():
    t = go.TokenOAuth("cid", "csec", {"GOOGLE_REFRESH_A_GMAIL_COM": SEGREDO},
                      http=_troca([], {"error": f"invalid_grant {SEGREDO}"}, 400))
    with pytest.raises(go.ErroGoogleOAuth) as e:
        t("a@gmail.com")
    assert str(e.value) == "token recusado: a@gmail.com" and SEGREDO not in str(e.value) and "csec" not in str(e.value)


def test_contatos_reusa_o_mesmo_erro_e_o_mesmo_token():
    assert gc.ErroGoogleContatos is go.ErroGoogleOAuth
    assert gc.TokenOAuth is go.TokenOAuth and gc.nome_da_variavel is go.nome_da_variavel


def test_credenciais_aceitam_os_nomes_canonicos_e_os_legados():
    assert go.credenciais_do_ambiente({"GOOGLE_CLIENT_ID": "i", "GOOGLE_CLIENT_SECRET": "s"}) == ("i", "s")
    assert go.credenciais_do_ambiente({"GOOGLE_OAUTH_CLIENT_ID": "i2", "GOOGLE_OAUTH_CLIENT_SECRET": "s2"}) == ("i2", "s2")
    assert go.credenciais_do_ambiente({"GOOGLE_CLIENT_ID": "i"}) is None
    assert go.credenciais_do_ambiente({}) is None
