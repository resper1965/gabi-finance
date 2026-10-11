"""Regras sem modelo do correio: endereço do remetente e quem NUNCA vai para a lixeira (pessoa conhecida, VIP, já respondido).
Sem texto de e-mail em log nem exceção."""
import json
import re
from email.utils import parseaddr

from gabi.cobrar.cadastro import dados

_ENDERECO = re.compile(r"^[a-z0-9._%+'-]{1,64}@[a-z0-9.-]{1,190}\.[a-z]{2,}$")
SEM_REMETENTE = "sem_remetente"


def endereco(texto) -> str | None:
    """Endereço puro e minúsculo do cabeçalho `From`; None se não houver um válido."""
    if not isinstance(texto, str):
        return None
    a = parseaddr(texto)[1].strip().lower()
    return a if _ENDERECO.match(a) else None


def _vips(con) -> set[str]:
    r = con.execute("select valor from parametro where chave='email.vips'").fetchone()
    try:
        lista = json.loads(r[0]) if r else []
    except (ValueError, TypeError):
        return set()
    return {a for x in lista if isinstance(lista, list) and (a := endereco(x))}


def _pessoa_conhecida(con, a: str) -> bool:
    """Pessoa ativa com o canal `email:<endereço>` (o dono cadastrou esse e-mail deliberadamente)."""
    for p in con.execute("select dados from pessoa where excluido_em is null"):
        for c in dados(p).get("canais") or []:
            if isinstance(c, str) and c.lower() == f"email:{a}":
                return True
    return False


def protegido(con, fonte_id: int, remetente) -> str | None:
    """Motivo pelo qual este remetente NUNCA vai para a lixeira, ou None: `aprovado` (pessoa cadastrada), `vip`, `respondido` (o dono já lhe escreveu
    nesta conta) ou `sem_remetente` (não há endereço válido para conferir: na dúvida fica na caixa)."""
    a = endereco(remetente)
    if a is None:
        return SEM_REMETENTE
    if _pessoa_conhecida(con, a):
        return "aprovado"
    if a in _vips(con):
        return "vip"
    if con.execute("select 1 from email_respondido where fonte_id=? and endereco=?", (fonte_id, a)).fetchone():
        return "respondido"
    return None
