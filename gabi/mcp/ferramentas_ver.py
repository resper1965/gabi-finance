"""Ferramentas MCP de leitura da Onda 2 (Hermes completo): ver o que o brain já guarda. Só leitura; nada é escrito além de `chamada_mcp`.
`contatos_buscar` (escopo `contatos`): contatos do Google e do Graph da ness juntos, por nome, e-mail ou pedaço do telefone. Consome: contato_google, contato_google_email, contato_graph."""
import re
import unicodedata

from gabi.mcp.ferramentas_dia import _inteiro

ESCOPOS = {"contatos_buscar": "contatos"}


def _simples(s) -> str:
    """Sem acento e em caixa baixa."""
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).casefold()


def buscar_contatos(con, texto: str, limite: int = 10) -> dict:
    """Contatos (Google e Microsoft da ness) cujo nome ou e-mail contém o texto, sem acento nem caixa, ou cujo telefone contém os dígitos dele (4 ou mais).
    Um item por telefone normalizado (o nome do Google vence); e-mail sem telefone vira item próprio. Ordenado por nome e telefone."""
    if not isinstance(texto, str) or len(texto.strip()) < 2:
        raise ValueError("texto deve ter ao menos 2 caracteres")
    limite = _inteiro(limite, 1, 50, "limite")
    q, digitos = _simples(texto.strip()), re.sub(r"\D", "", texto)
    por: dict[str, dict] = {}

    def item(chave: str, tel: str | None) -> dict:
        return por.setdefault(chave, {"nome": None, "graph": None, "telefones": [tel] if tel else [], "emails": set(), "origens": set()})

    def nomear(d, nome, campo="nome"):
        if d[campo] is None and isinstance(nome, str) and nome.strip():
            d[campo] = nome

    for r in con.execute("select conta, telefone, nome from contato_google order by conta, telefone"):
        d = item(r["telefone"], r["telefone"])
        nomear(d, r["nome"])
        d["origens"].add(f"google:{r['conta']}")
    for r in con.execute("select conta, email, telefone, nome from contato_google_email order by conta, email"):
        d = item(r["telefone"] or f"email:{r['email']}", r["telefone"] or None)
        nomear(d, r["nome"])
        d["emails"].add(r["email"])
        d["origens"].add(f"google:{r['conta']}")
    for r in con.execute("select conta, telefone, nome from contato_graph where coalesce(telefone, '')<>'' order by conta, telefone"):  # sem telefone: nada a juntar
        d = item(r["telefone"], r["telefone"])
        nomear(d, r["nome"], "graph")
        d["origens"].add(f"graph:{r['conta']}")

    achados = []
    for chave, d in por.items():
        nome = d["nome"] or d["graph"]
        casa = q in _simples(nome) or any(q in _simples(e) for e in d["emails"])
        if not casa and len(digitos) >= 4:
            casa = any(digitos in re.sub(r"\D", "", t) for t in d["telefones"])
        if casa:
            achados.append((((nome or "~").casefold(), chave), {"nome": nome, "telefones": d["telefones"], "emails": sorted(d["emails"]), "origens": sorted(d["origens"])}))
    achados.sort(key=lambda x: x[0])
    return {"texto": texto.strip(), "itens": [i for _, i in achados[:limite]]}


def registrar(srv, executar) -> None:
    @srv.tool()
    def contatos_buscar(texto: str, limite: int = 10) -> dict:
        """Contatos do Ricardo (Google e Microsoft da ness) por nome, e-mail ou pedaço do telefone: nome, telefones, e-mails e de onde veio. Só leitura."""
        def f(con, agora):
            return buscar_contatos(con, texto, limite)
        return executar("contatos_buscar", f)
