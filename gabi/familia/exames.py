"""Exames: do texto do laudo (Paperless) a PROPOSTAS de marcador; só entram em `exame` quando alguém confirma DE QUEM é o laudo (T4.2).
O extrator é heurístico e conservador: uma linha vira proposta só se tiver nome, valor numérico e unidade; o Ricardo confere antes de confirmar.
Consome: familia.saude."""
import datetime as dt
import re

from gabi.familia.saude import Cofre, _agora, registrar_exame

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


def propor_exames(s: Cofre, paperless_id: int, texto: str, pessoa_sugerida: str | None = None) -> int:
    """Grava as propostas do documento (idempotente por documento). Devolve quantas entraram."""
    if s.con.execute("select 1 from proposta_exame where paperless_id=?", (paperless_id,)).fetchone():
        return 0
    ms = extrair_marcadores(texto)
    for m in ms:
        s.con.execute("insert into proposta_exame(paperless_id, pessoa_sugerida, marcador, valor, unidade, em, ref_min, ref_max, criado_em) values (?,?,?,?,?,?,?,?,?)",
                      (paperless_id, pessoa_sugerida, m["marcador"], m["valor"], m["unidade"], m["em"], m["ref_min"], m["ref_max"], _agora()))
    return len(ms)


def confirmar_laudo(s: Cofre, paperless_id: int, pessoa_id: str, por: str) -> int:
    """"Confirme de quem é o laudo": só aqui as propostas viram exame. Sem pessoa ou sem quem confirma, nada entra."""
    if not pessoa_id or not pessoa_id.strip() or not por or not por.strip():
        raise ValueError("informe de quem é o laudo e quem confirmou")
    n = 0
    for p in s.con.execute("select * from proposta_exame where paperless_id=? and estado='proposta' order by id", (paperless_id,)).fetchall():
        em = dt.date.fromisoformat(p["em"]) if p["em"] else dt.date.today()
        ref = (p["ref_min"], p["ref_max"]) if p["ref_min"] and p["ref_max"] else None
        registrar_exame(s, pessoa_id, p["marcador"], p["valor"], p["unidade"], em, ref, paperless_id, por)
        s.con.execute("update proposta_exame set estado='confirmada' where id=?", (p["id"],))
        n += 1
    return n


def rejeitar_laudo(s: Cofre, paperless_id: int) -> int:
    return s.con.execute("update proposta_exame set estado='rejeitada' where paperless_id=? and estado='proposta'", (paperless_id,)).rowcount


def laudos_pendentes(s: Cofre) -> list[dict]:
    """Documentos com propostas esperando a confirmação de quem é o laudo."""
    saida: dict[int, dict] = {}
    for p in s.con.execute("select * from proposta_exame where estado='proposta' order by paperless_id, id"):
        l = saida.setdefault(p["paperless_id"], {"paperless_id": p["paperless_id"], "pessoa_sugerida": p["pessoa_sugerida"], "marcadores": []})
        l["marcadores"].append({"marcador": p["marcador"], "valor": p["valor"], "unidade": p["unidade"], "em": p["em"], "ref_min": p["ref_min"], "ref_max": p["ref_max"]})
    return list(saida.values())
