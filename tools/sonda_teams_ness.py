"""Sonda SOMENTE LEITURA do Teams da ness no Graph (3 GETs). Roda com o ambiente do serviço de fontes (runbook #graph-ness); não lê arquivo de segredo.
Imprime APENAS status HTTP, valores de chatType, contagens e NOMES de campo (e a forma, não o valor, dos ids). Nunca body, subject, displayName,
ids nem texto. Uso: python tools/sonda_teams_ness.py"""
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from gabi.fontes.graph_ness import BASE, ErroGraphNess, _ErroStatus, graph_ness_do_ambiente  # noqa: E402

_UUID = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
_SELECT = "id,createdDateTime,from,messageType,mentions,deletedDateTime"


def _status(erro: Exception):
    return erro.status if isinstance(erro, _ErroStatus) else "erro-de-rede"


def _forma(v) -> str:
    """Só a forma de um id: ausente, uuid ou outro (com tamanho). Nunca o valor."""
    if v is None:
        return "ausente"
    if isinstance(v, str):
        return "uuid" if _UUID.match(v) else f"texto({len(v)})"
    return type(v).__name__


def _campos(d) -> str:
    return ",".join(sorted(d)) if isinstance(d, dict) else "-"


def _get(g, url, extra=None):
    """(status, json|None). Falha vira só o status."""
    try:
        return 200, g._get(url, extra)
    except ErroGraphNess as e:
        return _status(e), None


def sondar(g, conta: str) -> list[str]:
    """Linhas de saída da sonda (3 GETs). Só status, chatType, contagens e nomes de campo."""
    base = f"{BASE}/users/{urllib.parse.quote(conta, safe='')}"
    out = []
    st, r = _get(g, f"{base}/chats?$expand=lastMessagePreview&$top=20")
    out.append(f"(a) GET /users/{{conta}}/chats?$expand=lastMessagePreview -> {st}")
    if r is None:
        return out + ["(b) não executada (sem chat)"]
    chats = [c for c in r.get("value") or [] if isinstance(c, dict)]
    tipos = sorted({str(c.get("chatType")) for c in chats})
    out += [f"    chats na página: {len(chats)}", f"    chatType: {','.join(tipos) or '-'}",
            f"    campos do chat: {_campos(chats[0]) if chats else '-'}",
            f"    campos de lastMessagePreview: {_campos(chats[0].get('lastMessagePreview')) if chats else '-'}"]
    alvo = next((c.get("id") for c in chats if isinstance(c.get("id"), str) and c["id"]), None)
    if not alvo:
        return out + ["(b) não executada (nenhum chat com id)"]
    st, r = _get(g, f"{BASE}/chats/{urllib.parse.quote(alvo, safe='')}/messages?$top=5&$select={_SELECT}")
    out.append(f"(b) GET /chats/{{id}}/messages?$top=5&$select=... -> {st}")
    if st in (402, 403):
        out.append(f"(c) endpoint exige licença/medição ou permissão: {st}")
    if r is None:
        return out
    msgs = [m for m in r.get("value") or [] if isinstance(m, dict)]
    out += [f"    mensagens: {len(msgs)}", f"    campos da mensagem: {_campos(msgs[0]) if msgs else '-'}"]
    de = [(m.get("from") or {}) for m in msgs if isinstance(m.get("from"), dict)]
    out.append(f"    from: {sorted({k for d in de for k in d})}")
    out.append(f"    from.user.id forma: {sorted({_forma((d.get('user') or {}).get('id') if isinstance(d.get('user'), dict) else None) for d in de})}")
    mencoes = [x for m in msgs for x in (m.get('mentions') or []) if isinstance(x, dict)]
    out.append(f"    mentions: {len(mencoes)}; campos: {_campos(mencoes[0]) if mencoes else '-'}")
    ids = {_forma((((x.get('mentioned') or {}).get('user') or {}).get('id')) if isinstance(x.get('mentioned'), dict) and isinstance((x['mentioned']).get('user'), dict) else None)
           for x in mencoes}
    out.append(f"    mentions[].mentioned.user.id forma: {sorted(ids) or '-'}")
    out.append(f"    messageType: {sorted({str(m.get('messageType')) for m in msgs}) or '-'}")
    return out


def main() -> int:
    g = graph_ness_do_ambiente(os.environ)
    if g is None:
        print("Graph da ness não configurado no ambiente (M365_TENANT_ID/CLIENT_ID/CLIENT_SECRET).")
        return 2
    for linha in sondar(g, g.contas()[0]):
        print(linha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
