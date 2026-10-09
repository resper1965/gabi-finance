"""Sugestões de regra por favorecido de PIX enviado. Consome: db (lancamento, regra, sugestao), regras.criar_sugestao.

Um favorecido (`Pix enviado <NOME>`) com `minimo` ou mais lançamentos SEM categoria vira UMA sugestão de regra (R1: só vale se o Ricardo
aprovar). A categoria vem dos lançamentos já categorizados do mesmo favorecido quando ela é única; senão a sugestão chega sem categoria
(`categoria_id: null`) para ele escolher na tela Regras. Se os irmãos divergem, não se sugere nada."""
import json
import re

from gabi.dinheiro.regras import casa, criar_sugestao

_PIX = re.compile(r"^pix enviado(?: para)?\s+(.+?)\s*$", re.I)


def _nome(descricao: str) -> str | None:
    m = _PIX.match(descricao or "")
    return re.sub(r"\s+", " ", m.group(1)).upper().strip() if m else None


def sugerir_por_favorecido(con, minimo: int = 3) -> int:
    sem: dict[str, int] = {}
    cats: dict[str, set] = {}
    for l in con.execute("select descricao_original, categoria_id from lancamento where descricao_original like 'Pix enviado%'"):
        nome = _nome(l["descricao_original"])
        if not nome:
            continue
        if l["categoria_id"] is None:
            sem[nome] = sem.get(nome, 0) + 1
        else:
            cats.setdefault(nome, set()).add(l["categoria_id"])
    regras = []
    for r in con.execute("select padrao, acao from regra where ativa=1"):
        try:
            if json.loads(r["acao"]).get("categoria_id") is not None:
                regras.append(re.compile(r["padrao"], re.I))
        except (ValueError, re.error):
            continue
    abertas = {json.loads(r["payload"]).get("padrao") for r in con.execute("select payload from sugestao where tipo='regra' and estado='pendente'")}
    novas = 0
    for nome, qtd in sorted(sem.items(), key=lambda x: -x[1]):
        irmaos = cats.get(nome, set())
        padrao = re.escape(nome)
        if qtd < minimo or len(irmaos) > 1 or padrao in abertas or any(casa(rx, f"Pix enviado {nome}", None) for rx in regras):
            continue
        motivo = f"{qtd} PIX para {nome} sem categoria" + ("; os demais já têm a categoria sugerida" if irmaos else "; escolha a categoria")
        criar_sugestao(con, "regra", None, {"padrao": padrao, "acao": {"categoria_id": next(iter(irmaos)) if irmaos else None}}, motivo)
        novas += 1
    return novas
