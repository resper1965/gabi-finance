"""Leitura da agenda (`agenda_evento`) para as superfícies: Hoje, resumo da manhã, MCP `agenda_listar`, rota e painel (spec 2026-10-11-agenda-design, §4).
Só lê. Tudo em horário local (`parametro agenda.fuso`), por `dia_local`/`dia_fim_local` (evento que cruza a meia-noite aparece nos dois dias).
O mesmo compromisso em duas contas (convidado em ambas) aparece UMA vez: trio (início, fim, título normalizado). Política de privados: `agenda.privados`."""
import datetime as dt
import json

from gabi.agenda import tempo
from gabi.trabalho.email import Conflito

FUSO_PADRAO = "America/Sao_Paulo"
MASCARA = "Compromisso privado"
POLITICAS = ("mostrar", "so_painel", "ocultar")


def _parametro(con, chave: str, padrao):
    r = con.execute("select valor from parametro where chave=?", (chave,)).fetchone()
    try:
        return json.loads(r[0]) if r else padrao
    except (ValueError, TypeError):
        return padrao


def fuso_da_agenda(con) -> str:
    f = _parametro(con, "agenda.fuso", FUSO_PADRAO)
    try:
        tempo._zona(f)
    except ValueError:
        return FUSO_PADRAO
    return f


def politica_privados(con) -> str:
    p = _parametro(con, "agenda.privados", "mostrar")
    return p if p in POLITICAS else "mostrar"


def dia_local(agora: dt.datetime, fuso: str) -> dt.date:
    """Data local de `agora`; um `agora` sem fuso já é tratado como local."""
    return agora.date() if agora.tzinfo is None else agora.astimezone(tempo._zona(fuso)).date()


def _normalizar(titulo) -> str:
    return " ".join((titulo or "").casefold().split())


def _linhas(con, de: str, ate: str) -> list[dict]:
    """Eventos das fontes liberadas que tocam [de, ate] (datas locais), sem duplicados, por início."""
    brutas = con.execute(
        "select e.id, e.inicio_utc, e.fim_utc, e.dia_local, e.dia_fim_local, e.dia_inteiro, e.titulo, e.link_reuniao, e.privado, f.conta as fonte "
        "from agenda_evento e join agenda_fonte f on f.id=e.fonte_id "
        "where f.estado='sim' and e.dia_local<=? and e.dia_fim_local>=? order by e.inicio_utc, e.dia_inteiro desc, e.id", (ate, de)).fetchall()
    vistos, saida = set(), []
    for r in brutas:
        chave = (r["inicio_utc"], r["fim_utc"], _normalizar(r["titulo"]))
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(dict(r))
    return saida


def agenda_intervalo(con, de: str, ate: str, fuso: str, *, painel: bool = False) -> list[dict]:
    """Itens `{id, titulo, inicio_local, fim_local, dia_local, dia_fim_local, dia_inteiro, link_reuniao, fonte, privado}`;
    `inicio_local`/`fim_local` são ISO local, `None` em dia inteiro. Privados mascarados conforme `agenda.privados` (`so_painel` só mostra a quem é o painel)."""
    politica = politica_privados(con)
    saida = []
    for r in _linhas(con, de, ate):
        mascarar = bool(r["privado"]) and (politica == "ocultar" or (politica == "so_painel" and not painel))
        inteiro = bool(r["dia_inteiro"])
        saida.append({"id": r["id"], "titulo": MASCARA if mascarar else r["titulo"],
                      "inicio_local": None if inteiro else tempo.para_local(r["inicio_utc"], fuso).isoformat(timespec="seconds"),
                      "fim_local": None if inteiro else tempo.para_local(r["fim_utc"], fuso).isoformat(timespec="seconds"),
                      "dia_local": r["dia_local"], "dia_fim_local": r["dia_fim_local"], "dia_inteiro": inteiro,
                      "link_reuniao": None if mascarar else r["link_reuniao"], "fonte": r["fonte"], "privado": bool(r["privado"])})
    return saida


def agenda_do_dia(con, dia: str, fuso: str, *, painel: bool = False) -> list[dict]:
    return agenda_intervalo(con, dia, dia, fuso, painel=painel)


def conflitos(con, de: str, ate: str, fuso: str | None = None) -> list[Conflito]:
    """Pares que se sobrepõem por INSTANTE (dia inteiro nunca conflita; encostar não é conflito; duplicado não conflita consigo).
    `sugestao_inicio` = quando os dois terminam (ISO local)."""
    fuso = fuso or fuso_da_agenda(con)
    ev = [r for r in _linhas(con, de, ate) if not r["dia_inteiro"]]
    jan = lambda r: tempo.Janela(r["inicio_utc"], r["fim_utc"], r["dia_local"], r["dia_fim_local"], False)  # noqa: E731
    achados = []
    for i, a in enumerate(ev):
        for b in ev[i + 1:]:
            if tempo.se_sobrepoem(jan(a), jan(b)):
                livre = max(a["fim_utc"], b["fim_utc"])
                achados.append(Conflito(a["id"], b["id"], tempo.para_local(livre, fuso).isoformat(timespec="seconds")))
    return achados
