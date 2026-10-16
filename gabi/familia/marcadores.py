"""Apelidos e normalização dos marcadores de exame (no cofre; ADR-014). "Colesterol Total", "COLESTEROL TOTAL" e "Col. total" viram um marcador só
quando o Ricardo define o apelido. Sem apelido, só se junta o que difere por caixa, acento e pontuação; HDL e LDL nunca se misturam.
Consome: familia.saude."""
import difflib
import re
import unicodedata

from gabi.familia.saude import Cofre

_MINUSCULAS = {"de", "da", "do", "das", "dos", "em", "e", "a", "o", "com", "por"}


def _chave(nome: str) -> str:
    """Sem acento, caixa nem pontuação; espaços colapsados."""
    sem = "".join(c for c in unicodedata.normalize("NFD", nome or "") if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sem.lower()).split())


def _limpo(nome: str) -> str:
    """Forma de exibição: primeira palavra capitalizada, siglas curtas (HDL, TSH) mantidas, o resto em minúsculas."""
    palavras = re.sub(r"[\s.:;]+", " ", (nome or "").strip(" .:;-")).split()
    saida = []
    for i, p in enumerate(palavras):
        if p.isupper() and len(p) <= 4 and p.lower() not in _MINUSCULAS:
            saida.append(p)
        elif i == 0:
            saida.append(p[:1].upper() + p[1:].lower())
        else:
            saida.append(p.lower())
    return " ".join(saida)


def normalizar(s: Cofre, nome: str) -> str:
    achado = s.con.execute("select marcador from marcador_apelido where apelido=?", (_chave(nome),)).fetchone()
    return achado["marcador"] if achado else _limpo(nome)


def definir_apelido(s: Cofre, apelido: str, marcador: str) -> None:
    chave, canonico = _chave(apelido), (marcador or "").strip()
    if not chave or not canonico:
        raise ValueError("informe o apelido e o marcador")
    s.con.execute("insert into marcador_apelido(apelido, marcador) values (?,?) on conflict(apelido) do update set marcador=excluded.marcador", (chave, canonico))


def apelidos(s: Cofre) -> list[dict]:
    return [{"apelido": r["apelido"], "marcador": r["marcador"]} for r in s.con.execute("select apelido, marcador from marcador_apelido order by marcador, apelido")]


def reaplicar(s: Cofre) -> int:
    """Reescreve o marcador de `exame` e `proposta_exame` conforme os apelidos, sem chamar modelo. Devolve quantas linhas mudaram."""
    n = 0
    for tabela in ("exame", "proposta_exame"):
        for r in s.con.execute(f"select id, marcador from {tabela}").fetchall():
            novo = normalizar(s, r["marcador"])
            if novo != r["marcador"]:
                s.con.execute(f"update {tabela} set marcador=? where id=?", (novo, r["id"]))
                n += 1
    return n


def _parecidos(a: str, b: str) -> bool:
    ca, cb = _chave(a), _chave(b)
    if ca == cb:
        return False  # já se juntam sozinhos
    if ca.replace(" ", "") == cb.replace(" ", ""):
        return True
    dif = set(ca.split()) ^ set(cb.split())
    if all(len(t) <= 4 for t in dif):
        return False  # só siglas curtas diferem (HDL x LDL): marcadores distintos
    return difflib.SequenceMatcher(None, ca, cb).ratio() >= 0.85


def sugestoes(s: Cofre) -> list[str]:
    """Marcadores com grafias parecidas e ainda sem apelido (candidatos a juntar)."""
    nomes = sorted({r[0] for t in ("exame", "proposta_exame") for r in s.con.execute(f"select marcador from {t}")})
    com_apelido = {r["apelido"] for r in s.con.execute("select apelido from marcador_apelido")}
    nomes = [n for n in nomes if _chave(n) not in com_apelido]
    return sorted({n for i, a in enumerate(nomes) for b in nomes[i + 1:] if _parecidos(a, b) for n in (a, b)})
