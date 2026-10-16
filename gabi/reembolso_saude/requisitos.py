"""Requisitos do reembolso de saúde, EDITÁVEIS: `parametro` `reembolso_saude.requisitos` (JSON); sem ele, `seeds/reembolso-saude-requisitos.json`.
Lido a cada rodada. Inválido -> RequisitosInvalidos: quem chama avisa e para; nunca inventa regra. Consome: parametro."""
import json
from pathlib import Path

from gabi.reembolso_saude.tipos import ITENS, PORTOES, ROTULOS

CHAVE = "reembolso_saude.requisitos"
SEED = Path(__file__).resolve().parent.parent.parent / "seeds" / "reembolso-saude-requisitos.json"


class RequisitosInvalidos(ValueError):
    pass


def _lista(d: dict, chave: str, permitidos) -> None:
    v = d.get(chave)
    if not isinstance(v, list) or not all(isinstance(i, str) for i in v):
        raise RequisitosInvalidos(f"{chave}: precisa ser lista de textos")
    fora = [i for i in v if i not in permitidos]
    if fora:
        raise RequisitosInvalidos(f"{chave}: item desconhecido {', '.join(fora)}")


def validar(d) -> dict:
    if not isinstance(d, dict):
        raise RequisitosInvalidos("requisitos: precisa ser objeto")
    for k in ("operadora", "operadora_extrato"):
        if not isinstance(d.get(k), str) or not d[k].strip():
            raise RequisitosInvalidos(f"{k}: ausente")
    for k in ("dias_guarda_nao_reembolsavel", "dias_sem_credito"):
        if not isinstance(d.get(k), int) or isinstance(d[k], bool) or d[k] <= 0:
            raise RequisitosInvalidos(f"{k}: precisa ser inteiro > 0")
    for k in ("consulta_exige", "tratamento_exige"):
        _lista(d, k, PORTOES)
    for k in ("todos", "tratamento"):
        _lista(d, k, ITENS)
    if not isinstance(d.get("rotulos", {}), dict) or not all(isinstance(v, str) for v in d.get("rotulos", {}).values()):
        raise RequisitosInvalidos("rotulos: precisa ser objeto de textos")
    return {**d, "rotulos": dict(d.get("rotulos", {}))}


def carregar(con) -> dict:
    r = con.execute("select valor from parametro where chave=?", (CHAVE,)).fetchone()
    try:
        bruto = json.loads(r[0]) if r else json.loads(SEED.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as e:
        raise RequisitosInvalidos(f"{CHAVE}: {type(e).__name__}") from None
    return validar(bruto)


def rotulo(req: dict, item: str) -> str:
    return req["rotulos"].get(item) or ROTULOS.get(item) or item.replace("_", " ")
