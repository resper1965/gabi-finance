"""Regras sem modelo do correio: endereço do remetente e quem NUNCA vai para a lixeira (pessoa conhecida, VIP, já respondido).
Sem texto de e-mail em log nem exceção."""
import json
import re
import unicodedata
from email.utils import parseaddr

from gabi.cobrar.cadastro import dados

_ENDERECO = re.compile(r"^[a-z0-9._%+'-]{1,64}@[a-z0-9.-]{1,190}\.[a-z]{2,}$")
SEM_REMETENTE = "sem_remetente"
# E-mail transacional/financeiro quase sempre vem com sinal de lista (List-Unsubscribe, Auto-Submitted): sem esta guarda só o modelo, com a confiança
# que ele mesmo declara, decidiria sobre fatura, boleto ou cobrança. O dono troca a lista pelo painel (`email.palavras_protegidas`); a de baixo é o padrão.
PALAVRAS_PADRAO = ["fatura", "boleto", "vencimento", "cobrança", "pagamento", "nota fiscal", "nfs-e", "nf-e", "dae", "darf", "imposto", "receita federal",
                   "intimação", "contrato", "senha", "código de verificação", "token", "extrato", "cancelamento", "multa"]
PALAVRA_MAX = 60


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


def regra_valida(texto) -> str | None:
    """Regra "sempre lixo" normalizada: endereço puro (`a@x.com`) ou domínio exato (`@x.com`); None se não for nenhum dos dois."""
    if not isinstance(texto, str):
        return None
    t = texto.strip().lower()
    if t.startswith("@"):
        return t if _ENDERECO.match("x" + t) else None
    return endereco(t)


def regra_lixo(con, remetente) -> str | None:
    """A regra do dono ("sempre lixo", parâmetro `email.regras_lixo`) que casa com este remetente, ou None. Endereço exato ou domínio exato (sem subdomínio)."""
    a = endereco(remetente)
    if a is None:
        return None
    r = con.execute("select valor from parametro where chave='email.regras_lixo'").fetchone()
    try:
        lista = json.loads(r[0]) if r else []
    except (ValueError, TypeError):
        return None
    if not isinstance(lista, list):
        return None
    regras = {x for t in lista if (x := regra_valida(t))}
    for candidata in (a, "@" + a.split("@", 1)[1]):
        if candidata in regras:
            return candidata
    return None


def _pessoa_conhecida(con, a: str) -> bool:
    """Pessoa ativa com o canal `email:<endereço>` ou o endereço em `emails` (o dono cadastrou esse e-mail deliberadamente)."""
    for p in con.execute("select dados from pessoa where excluido_em is null"):
        d = dados(p)
        for c in d.get("canais") or []:
            if isinstance(c, str) and c.lower() == f"email:{a}":
                return True
        if any(isinstance(e, str) and endereco(e) == a for e in d.get("emails") or []):
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


def _normal(texto) -> str:
    """Minúsculas e sem acento: 'COBRANÇA' e 'cobranca' são a mesma palavra."""
    d = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in d if not unicodedata.combining(c)).casefold()


def palavras(con) -> list[str]:
    """Palavras que protegem o e-mail de ir para a lixeira: o parâmetro do dono (lista vazia vale) ou, se ausente ou corrompido, o padrão."""
    r = con.execute("select valor from parametro where chave='email.palavras_protegidas'").fetchone()
    try:
        v = json.loads(r[0]) if r else None
    except (ValueError, TypeError):
        v = None
    if not isinstance(v, list):
        v = PALAVRAS_PADRAO
    return [_normal(x.strip()) for x in v if isinstance(x, str) and x.strip() and len(x) <= PALAVRA_MAX]


def texto_protegido(con, remetente, assunto, trecho) -> str | None:
    """`palavra` se remetente, assunto ou trecho começam alguma palavra protegida (fatura, boleto, cobrança...); a busca ignora acento e caixa."""
    texto = _normal(" ".join(str(x or "") for x in (remetente, assunto, trecho)))
    for p in palavras(con):
        if re.search(r"(?<![a-z0-9])" + re.escape(p), texto):
            return "palavra"
    return None

