"""Regras de reembolso do plano de saúde, PURAS (sem banco, sem cofre, sem Paperless): portadas de `dossies.py` do gabi-fin.
Documento = dict: id (do Paperless), estado, documento (nf, recibo...), caso (consulta|tratamento), campos {paciente, prestador, valor, doc_prestador,
conselho, especialidade}, data (date do atendimento), adicionado (date), pedido_em (date|None). Estados: a_pedir, sem_nf, sem_aprovacao, a_conferir,
autorizacao (só apoio), pedido, recebido. Itens obrigatórios, portões e prazos vêm dos requisitos (dados editáveis)."""
import datetime as dt
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from gabi.reembolso_saude.tipos import CAMPOS

SEM = {"nf": "sem_nf", "autorizacao": "sem_aprovacao"}
ESTADOS_SEM = tuple(SEM.values())
_TITULO = re.compile(r"^(dra?|sra?)\.?\s+")


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return _TITULO.sub("", re.sub(r"\s+", " ", s).strip()).strip()


def par(doc: dict) -> tuple[str, str]:
    return norm(doc["campos"].get("paciente")), norm(doc["campos"].get("prestador"))


def chave(doc: dict) -> str:
    pac, prest = par(doc)
    return f"{pac}|{prest}|{doc['data']:%Y-%m}"


def centavos(v) -> int | None:
    """'312.45' / 'BRL312.45' / '1.234,56' / 10 -> centavos; ilegível = None."""
    if isinstance(v, bool) or v is None:
        return None
    s = re.sub(r"[^\d.,\-]", "", str(v))
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return int((d * 100).to_integral_value())


def itens_do_doc(doc: dict) -> set[str]:
    itens = {"data"}
    if doc.get("documento"):
        itens.add(doc["documento"])
    itens |= {c for c in CAMPOS if doc["campos"].get(c) not in (None, "")}
    return itens


def estado_pelo_portao(caso: str, itens_par: set[str], req: dict) -> str:
    for item in req[f"{caso}_exige"]:
        if item not in itens_par:
            return SEM[item]
    return "a_pedir"


def itens_portao(doc: dict, docs_par: list[dict]) -> set[str]:
    """Itens que contam para os portões de `doc`: NF só do mesmo dossiê (mês do atendimento); aprovação da operadora vale para o par (paciente, prestador)."""
    mesmo = [x for x in docs_par if chave(x) == chave(doc)]
    itens = set().union(*(itens_do_doc(x) for x in mesmo)) if mesmo else set()
    if any(x.get("documento") == "autorizacao" for x in docs_par):
        itens.add("autorizacao")
    return itens


def reabrir(docs_par: list[dict], hoje: dt.date, req: dict) -> list[dict]:
    """Documentos `sem_nf`/`sem_aprovacao` (dentro do prazo de guarda) cujo item que faltava já chegou."""
    prazo = req["dias_guarda_nao_reembolsavel"]
    return [x for x in docs_par
            if x["estado"] in ESTADOS_SEM and x.get("caso") in ("consulta", "tratamento") and (hoje - x["adicionado"]).days <= prazo
            and estado_pelo_portao(x["caso"], itens_portao(x, docs_par), req) == "a_pedir"]


def faltando(docs_dossie: list[dict], req: dict) -> list[str]:
    """Códigos dos itens que ainda faltam (na ordem do arquivo de requisitos); tratamento acrescenta os seus."""
    exig = list(req["todos"])
    if any(x.get("caso") == "tratamento" for x in docs_dossie):
        exig += [i for i in req["tratamento"] if i not in exig]
    tem = set().union(*(itens_do_doc(x) for x in docs_dossie)) if docs_dossie else set()
    return [i for i in exig if i not in tem]


def resumo(docs_a_pedir: list[dict], hoje: dt.date, req: dict) -> list[dict]:
    grupos: dict[str, list[dict]] = {}
    for x in docs_a_pedir:
        grupos.setdefault(chave(x), []).append(x)
    saida = []
    for k in sorted(grupos):
        ds = sorted(grupos[k], key=lambda x: x["id"])
        recente = max(ds, key=lambda x: (x["adicionado"], x["id"]))
        falta = faltando(ds, req)
        saida.append({"id": k, "paciente": recente["campos"].get("paciente"), "prestador": recente["campos"].get("prestador"),
                      "mes": f"{ds[0]['data']:%Y-%m}", "faltam": falta, "pronto": not falta, "docs": [x["id"] for x in ds],
                      "parado_dias": (hoje - recente["adicionado"]).days})
    return saida


def casar_credito(doc: dict, txs: list[dict], operadora_extrato: str) -> int | None:
    """Id do ÚNICO crédito da operadora que cabe no pedido: positivo, descrição com o nome da operadora, data igual ou depois do pedido,
    valor até o total do documento. Zero ou mais de um candidato = None (o Ricardo decide)."""
    total = centavos(doc["campos"].get("valor"))
    if total is None or total <= 0:
        return None
    alvo = re.sub(r"[^A-Z]", "", operadora_extrato.upper())
    desde = doc.get("pedido_em")
    cand = [t for t in txs if t["valor_centavos"] > 0 and t["valor_centavos"] <= total and alvo in re.sub(r"[^A-Z]", "", t["descricao"].upper())
            and (desde is None or dt.date.fromisoformat(str(t["data"])[:10]) >= desde)]
    return cand[0]["id"] if len(cand) == 1 else None
