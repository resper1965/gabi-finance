"""Exames: do texto do laudo (Paperless) a PROPOSTAS de marcador; só entram em `exame` quando alguém confirma DE QUEM é o laudo (T4.2).
O extrator é heurístico e conservador: uma linha vira proposta só se tiver nome, valor numérico e unidade; o Ricardo confere antes de confirmar.
Consome: familia.saude."""
import datetime as dt
import re
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from gabi.familia.marcadores import normalizar
from gabi.familia.saude import Cofre, _agora, _log, registrar_exame

if TYPE_CHECKING:  # extrair.py importa as regras daqui; o import real seria circular
    from gabi.familia.extrair import Laudo

BRT = ZoneInfo("America/Sao_Paulo")
_NUM = r"\d+(?:[.,]\d+)?"
_LINHA = re.compile(
    rf"^\s*(?P<m>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 .\-/()]*?[A-Za-zÀ-ÿ)])\s*[:.\s]*?\s+(?P<v>{_NUM})\s*(?P<u>[A-Za-zµ%/³0-9]*[A-Za-zµ%/³][A-Za-zµ%/³0-9]*(?:/[A-Za-z0-9µ]+)?)"
    rf"(?:.*?(?:ref\w*\.?|refer[eê]ncia)[^0-9]{{0,12}}(?P<a>{_NUM})\s*(?:a|-|–|até)\s*(?P<b>{_NUM}))?", re.I)
_DATA = re.compile(r"(?:coleta|data|realizad[oa])\D{0,20}(\d{2})/(\d{2})/(\d{4})", re.I)
_IGNORAR = re.compile(r"^(paciente|data|observa|m[eé]dico|crm|cpf|rg|nascimento|idade|telefone|p[aá]gina|laborat[oó]rio|conv[eê]nio|material|m[eé]todo)", re.I)


def extrair_marcadores(texto: str) -> list[dict]:
    d = _DATA.search(texto or "")
    em = f"{d.group(3)}-{d.group(2)}-{d.group(1)}" if d else None
    saida = []
    for linha in (texto or "").splitlines():
        if _IGNORAR.match(linha.strip()):
            continue
        m = _LINHA.match(linha)
        if not m:
            continue
        nome = re.sub(r"[\s.]+$", "", m["m"]).strip()
        saida.append({"marcador": nome, "valor": m["v"], "unidade": m["u"], "em": em, "ref_min": m["a"], "ref_max": m["b"]})
    return saida


def _ponto(m: dict) -> tuple:
    return (m["valor"], m["unidade"], m["ref_min"], m["ref_max"])


def _versao_atual(s: Cofre, paperless_id: int) -> int:
    """Maior versão já gravada do documento (propostas ou exames); 0 = nunca extraído."""
    return s.con.execute("select max(coalesce((select max(versao) from proposta_exame where paperless_id=?),0), coalesce((select max(versao) from exame where paperless_id=?),0))",
                         (paperless_id, paperless_id)).fetchone()[0]


def _marcadores_da_versao(s: Cofre, paperless_id: int, versao: int) -> list[dict]:
    return [dict(r) for r in s.con.execute("select * from proposta_exame where paperless_id=? and versao=? order by id", (paperless_id, versao))]


def _normalizados(s: Cofre, laudo: 'Laudo') -> list[dict]:
    return [{**m, "marcador": normalizar(s, m["marcador"])} for m in laudo.marcadores]


def _comparar(anteriores: list[dict], novos: list[dict]) -> dict:
    """Por (marcador, data): iguais, diferentes (mudou valor, unidade ou faixa) e novos (não existia)."""
    antes = {(m["marcador"], m["em"]): _ponto(m) for m in anteriores}
    r = {"novos": 0, "iguais": 0, "diferentes": 0}
    for m in novos:
        chave = (m["marcador"], m["em"])
        r["novos" if chave not in antes else "iguais" if antes[chave] == _ponto(m) else "diferentes"] += 1
    return r


def _gravar_propostas(s: Cofre, paperless_id: int, versao: int, laudo: 'Laudo', itens: list[dict], pessoa_sugerida: str | None) -> None:
    for m in itens:
        s.con.execute("insert into proposta_exame(paperless_id, pessoa_sugerida, marcador, valor, unidade, em, ref_min, ref_max, criado_em, versao, origem, qualitativo, observacao) "
                      "values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (paperless_id, pessoa_sugerida, m["marcador"], m["valor"], m["unidade"], m["em"], m["ref_min"], m["ref_max"], _agora(),
                       versao, laudo.origem, int(bool(m.get("qualitativo"))), m.get("observacao")))


def propor_exames(s: Cofre, paperless_id: int, laudo: 'Laudo', pessoa_sugerida: str | None = None) -> int:
    """Grava as propostas do documento como a PRÓXIMA versão; idêntica à versão mais recente não cria nada (idempotente). Devolve quantas entraram."""
    itens, atual = _normalizados(s, laudo), _versao_atual(s, paperless_id)
    if atual and {(m["marcador"], m["em"], *_ponto(m)) for m in _marcadores_da_versao(s, paperless_id, atual)} == {(m["marcador"], m["em"], *_ponto(m)) for m in itens}:
        return 0
    _gravar_propostas(s, paperless_id, atual + 1, laudo, itens, pessoa_sugerida)
    return len(itens)


def dono_confirmado(s: Cofre, paperless_id: int) -> str | None:
    r = s.con.execute("select pessoa_id from exame where paperless_id=? order by versao desc, id desc limit 1", (paperless_id,)).fetchone()
    return r["pessoa_id"] if r else None


def _registrar_proposta(s: Cofre, p, pessoa_id: str, por: str, laboratorio: str | None = None) -> None:
    em = dt.date.fromisoformat(p["em"]) if p["em"] else dt.datetime.now(BRT).date()
    ref = (p["ref_min"], p["ref_max"]) if p["ref_min"] and p["ref_max"] else None
    registrar_exame(s, pessoa_id, p["marcador"], p["valor"], p["unidade"], em, ref, p["paperless_id"], por,
                    versao=p["versao"], qualitativo=bool(p["qualitativo"]), observacao=p["observacao"], laboratorio=laboratorio)
    s.con.execute("update proposta_exame set estado='confirmada' where id=?", (p["id"],))


def _pendentes_da_versao_atual(s: Cofre, paperless_id: int) -> list:
    return s.con.execute("select * from proposta_exame where paperless_id=? and estado='proposta' and versao=(select max(versao) from proposta_exame where paperless_id=?) order by id",
                         (paperless_id, paperless_id)).fetchall()


def confirmar_laudo(s: Cofre, paperless_id: int, pessoa_id: str, por: str) -> int:
    """"Confirme de quem é o laudo": só aqui as propostas (da versão mais recente) viram exame. Sem pessoa ou sem quem confirma, nada entra."""
    if not pessoa_id or not pessoa_id.strip() or not por or not por.strip():
        raise ValueError("informe de quem é o laudo e quem confirmou")
    ps = _pendentes_da_versao_atual(s, paperless_id)
    for p in ps:
        _registrar_proposta(s, p, pessoa_id, por)
    return len(ps)


def reprocessar(s: Cofre, paperless_id: int, laudo: 'Laudo', por: str) -> dict:
    """Extração nova do mesmo documento = versão nova; a anterior fica. Se o dono já estava confirmado, a versão nova entra como exame com o mesmo dono.
    Resultado idêntico ao da versão atual não cria versão (rodar duas vezes seguidas não duplica). Devolve {versao, novos, iguais, diferentes}."""
    if not por or not por.strip():
        raise ValueError("informe quem pediu o reprocessamento")
    itens, atual = _normalizados(s, laudo), _versao_atual(s, paperless_id)
    anteriores = _marcadores_da_versao(s, paperless_id, atual) if atual else []
    r = _comparar(anteriores, itens)
    if atual and not r["novos"] and not r["diferentes"] and len(anteriores) == len(itens):
        return {"versao": atual, **r}
    dono = dono_confirmado(s, paperless_id)
    sugerida = dono or (anteriores[0]["pessoa_sugerida"] if anteriores else None)
    _gravar_propostas(s, paperless_id, atual + 1, laudo, itens, sugerida)
    if dono:
        for p in _pendentes_da_versao_atual(s, paperless_id):
            _registrar_proposta(s, p, dono, por, laudo.laboratorio)
    return {"versao": atual + 1, **r}


def versoes(s: Cofre, paperless_id: int, quem: str | None = None) -> list[dict]:
    """Todas as versões da extração do documento, para comparar; com `quem`, a leitura entra no log."""
    if quem:
        _log(s, quem, None, f"versoes:{paperless_id}")
    saida: dict[int, dict] = {}
    for p in s.con.execute("select * from proposta_exame where paperless_id=? order by versao, id", (paperless_id,)):
        v = saida.setdefault(p["versao"], {"versao": p["versao"], "origem": p["origem"], "criado_em": p["criado_em"], "marcadores": []})
        v["marcadores"].append({"marcador": p["marcador"], "valor": p["valor"], "unidade": p["unidade"], "em": p["em"], "ref_min": p["ref_min"], "ref_max": p["ref_max"],
                                "qualitativo": bool(p["qualitativo"]), "observacao": p["observacao"]})
    return list(saida.values())


def diferencas(s: Cofre, paperless_id: int, de: int, para: int) -> list[dict]:
    """Lista o que mudou entre duas versões: [{marcador, em, antes, depois}] (antes/depois None quando só existe numa delas)."""
    por_versao = {v["versao"]: {(m["marcador"], m["em"]): m for m in v["marcadores"]} for v in versoes(s, paperless_id)}
    a, b = por_versao.get(de, {}), por_versao.get(para, {})
    saida = []
    for chave in sorted(set(a) | set(b), key=lambda k: (k[0], k[1] or "")):
        x, y = a.get(chave), b.get(chave)
        if x is None or y is None or _ponto(x) != _ponto(y):
            saida.append({"marcador": chave[0], "em": chave[1], "antes": x and x["valor"], "depois": y and y["valor"]})
    return saida


def rejeitar_laudo(s: Cofre, paperless_id: int) -> int:
    return s.con.execute("update proposta_exame set estado='rejeitada' where paperless_id=? and estado='proposta' and versao=(select max(versao) from proposta_exame where paperless_id=?)",
                         (paperless_id, paperless_id)).rowcount


def laudos_pendentes(s: Cofre) -> list[dict]:
    """Documentos com propostas (da versão mais recente) esperando a confirmação de quem é o laudo."""
    saida: dict[int, dict] = {}
    for p in s.con.execute("select * from proposta_exame p where estado='proposta' and versao=(select max(versao) from proposta_exame where paperless_id=p.paperless_id) order by paperless_id, id"):
        l = saida.setdefault(p["paperless_id"], {"paperless_id": p["paperless_id"], "pessoa_sugerida": p["pessoa_sugerida"], "versao": p["versao"], "origem": p["origem"], "marcadores": []})
        l["marcadores"].append({"marcador": p["marcador"], "valor": p["valor"], "unidade": p["unidade"], "em": p["em"], "ref_min": p["ref_min"], "ref_max": p["ref_max"],
                                "qualitativo": bool(p["qualitativo"]), "observacao": p["observacao"]})
    return list(saida.values())
