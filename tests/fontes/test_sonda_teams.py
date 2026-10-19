"""A sonda do Teams imprime só status, chatType, contagens e nomes de campo: nunca body, displayName nem ids."""
import importlib.util
import pathlib

from gabi.fontes.graph_ness import GraphNess

_spec = importlib.util.spec_from_file_location("sonda_teams_ness", pathlib.Path(__file__).parents[2] / "tools" / "sonda_teams_ness.py")
sonda = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sonda)

SEGREDOS = ["SEGREDO-CORPO", "Fulano Silva", "19:abc-id-do-chat@thread.v2", "11111111-2222-3333-4444-555555555555", "AAA-ID-MSG", "texto previa"]
UID = "11111111-2222-3333-4444-555555555555"


def _http(metodo, url, corpo=None, cab=None):
    assert metodo == "GET"
    if "/messages" in url:
        return 200, {"value": [{"id": "AAA-ID-MSG", "messageType": "message", "from": {"user": {"id": UID, "displayName": "Fulano Silva"}},
                                "body": {"content": "SEGREDO-CORPO"},
                                "mentions": [{"id": 0, "mentionText": "Fulano Silva", "mentioned": {"user": {"id": UID, "displayName": "Fulano Silva"}}}]}]}
    return 200, {"value": [{"id": "19:abc-id-do-chat@thread.v2", "chatType": "oneOnOne", "topic": "Fulano Silva",
                            "lastMessagePreview": {"body": {"content": "texto previa"}, "id": "AAA-ID-MSG"}}]}


def test_saida_sem_valores_sensiveis():
    saida = "\n".join(sonda.sondar(GraphNess(lambda: "tok", ["a@b.com"], http=_http), "a@b.com"))
    assert "oneOnOne" in saida and "-> 200" in saida and "uuid" in saida
    for s in SEGREDOS:
        assert s not in saida


def test_falha_imprime_so_status():
    def http(m, u, c=None, h=None):
        return 403, {}
    saida = "\n".join(sonda.sondar(GraphNess(lambda: "tok", ["a@b.com"], http=http), "a@b.com"))
    assert "403" in saida
