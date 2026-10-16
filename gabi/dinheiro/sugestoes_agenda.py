"""Compromissos sugeridos pela agenda (AR3): evento que se repete todo mês no mesmo dia e fala de pagar vira PERGUNTA (canal de decisão).
R1: só pergunta; o Ricardo escolhe 1) criar o compromisso ou 2) ignorar. R2: nada sai daqui. Só lê `agenda_evento` de calendário liberado e evento não privado.
Não sugere o que já existe (compromisso, conta ou cartão com o mesmo nome) nem fatura de cartão (vem do Open Finance).
Consome: agenda_evento, compromisso_linha, conta, decisoes."""
import datetime as dt
import re
import unicodedata

from gabi import decisoes

PALAVRAS = re.compile(r"\b(pagar|pagamento|adiantamento|boleto|vencimento)\b")
IGNORAR = re.compile(r"\b(cartao|fatura|credito)\b")  # fatura de cartão já vem do banco
SOLTAS = {"pagar", "pagamento", "adiantamento", "boleto", "vencimento", "de", "da", "do", "dos", "das", "e", "a", "o", "para"}
TIPO = "compromisso_agenda"
MIN_MESES = 2


def _norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


def _tokens(s: str) -> set[str]:
    return {t for t in _norm(s).split() if t not in SOLTAS and len(t) > 2}


def _ja_existe(con, titulo: str) -> bool:
    alvo = _tokens(titulo)
    if not alvo:
        return True
    textos = [r[0] + " " + (r[1] or "") for r in con.execute("select nome, extrato from compromisso_linha where excluido_em is null")]
    textos += [f"{r[0] or ''} {r[1] or ''}" for r in con.execute("select apelido, instituicao from conta where excluido_em is null")]
    return any(alvo <= _tokens(t) for t in textos)


def candidatas(con, hoje: dt.date) -> list[dict]:
    """Eventos futuros e vivos, agrupados por título, que repetem em ≥ 2 meses diferentes no mesmo dia do mês."""
    grupos: dict[str, dict] = {}
    for r in con.execute("select e.titulo, e.dia_local from agenda_evento e join agenda_fonte f on f.id=e.fonte_id "
            "where f.estado='sim' and e.status!='cancelled' and not coalesce(e.privado,0) and e.dia_local>=? and e.titulo is not null", (hoje.isoformat(),)):
        n = _norm(r["titulo"])
        if not PALAVRAS.search(n) or IGNORAR.search(n):
            continue
        g = grupos.setdefault(n, {"titulo": r["titulo"].strip(), "dias": [], "meses": set()})
        g["dias"].append(int(r["dia_local"][8:10]))
        g["meses"].add(r["dia_local"][:7])
    out = []
    for g in grupos.values():
        if len(g["meses"]) >= MIN_MESES and len(set(g["dias"])) == 1 and not _ja_existe(con, g["titulo"]):
            out.append({"titulo": g["titulo"], "dia": g["dias"][0], "meses": len(g["meses"])})
    return sorted(out, key=lambda c: c["titulo"])


def propor(con, hoje: dt.date, agora_iso: str) -> int:
    """Cria uma pergunta por candidata ainda sem pergunta (aberta ou respondida) com o mesmo título. Devolve quantas criou."""
    criadas = 0
    for c in candidatas(con, hoje):
        titulo = f"Criar compromisso '{c['titulo']}'? (todo dia {c['dia']} na agenda)"
        if con.execute("select 1 from pergunta where tipo=? and titulo=? and estado in ('aberta','respondida')", (TIPO, titulo)).fetchone():
            continue
        criar = {"nome": c["titulo"], "extrato": c["titulo"], "vencimento": f"dia:{c['dia']}", "ajuste_dia_util": "adia", "valor_tipo": "variavel",
                 "forma": "pix", "ativo": False, "obs": f"sugerido pela agenda em {hoje.isoformat()}; extrato e forma provisórios, complete antes de ativar"}
        decisoes.criar_pergunta(
            con, TIPO, titulo, f"Aparece em {c['meses']} meses seguidos na agenda. Nasce DESATIVADO, sem valor e com o extrato provisório (o título): complete e ative em Cadastros › Compromissos.",
            [{"n": 1, "rotulo": "Sim, criar (desativado até você completar)", "efeito": "criar_compromisso", "parametros": criar},
             {"n": 2, "rotulo": "Não, ignorar", "efeito": "registrar_nota"}], "claude", agora_iso)
        criadas += 1
    return criadas
