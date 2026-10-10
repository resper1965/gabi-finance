"""Rodada do Trabalho: lê e-mail, agenda e tarefas das caixas liberadas (estado 'sim') e grava no banco. Só leitura nas origens (R2).
Uma caixa que falha não derruba as outras; credencial recusada ou ausente vira o aviso `caixa_reconectar` (fecha sozinho quando a caixa volta).
`cliente_de(caixa: dict) -> Graph | Google | None` vem de quem chama (o job monta os tokens do ambiente; aqui não há credencial, R5).
Consome: caixa_email, trabalho.{email,agenda,tarefas}, rodada, avisos."""
import datetime as dt
import json
import re
from dataclasses import dataclass
from typing import Callable

from gabi.avisos import _novo
from gabi.fontes.google import ErroGoogle
from gabi.fontes.graph import ErroGraph
from gabi.rodada import registrar_rodada
from gabi.trabalho.agenda import ingerir_eventos
from gabi.trabalho.email import ingerir_email
from gabi.trabalho.tarefas import ingerir_tarefas

CREDENCIAL = re.compile(r"-> (400|401|403)\b|invalid_grant")


@dataclass(frozen=True)
class ResumoTrabalho:
    caixas: int
    mensagens: int
    eventos: int
    tarefas: int
    falhas: int


def _fontes(cli, provedor: str):
    """(e-mail, eventos, tarefas) no formato que `trabalho.*` consome; o cliente do provedor muda, o resto não."""
    if provedor == "graph":
        return (lambda c, cur: cli.delta_mensagens(c["endereco"], cur), lambda c, cur: cli.delta_eventos(c["endereco"], cur),
                lambda c: cli.tarefas(c["endereco"]))
    return (lambda c, cur: cli.historico_gmail(c["endereco"], cur), lambda c, cur: cli.eventos(c["endereco"], cur),
            lambda c: cli.tasks(c["endereco"]))


def _fechar_aviso(con, caixa_id: int, agora: dt.datetime) -> None:
    con.execute("update aviso set entregue_em=? where tipo='caixa_reconectar' and entregue_em is null and json_extract(payload,'$.chave')=?",
                (agora.astimezone(dt.timezone.utc).isoformat(), str(caixa_id)))


def _processar(con, caixa: dict, cliente_de) -> tuple[int, int, int]:
    cli = cliente_de(caixa)
    if cli is None:
        raise PermissionError("sem credencial configurada")
    email, eventos, tarefas = _fontes(cli, caixa["provedor"])
    msgs = ingerir_email(con, caixa["id"], email).novos
    evs = ingerir_eventos(con, caixa["id"], eventos)
    ts = ingerir_tarefas(con, f"{caixa['provedor']}:{caixa['endereco']}", tarefas(caixa))
    _concluir_pedidas(con, caixa, cli)
    return msgs, evs, ts


def _concluir_pedidas(con, caixa: dict, cli) -> None:
    """Conclui NA ORIGEM as tarefas que o Ricardo mandou concluir pelo painel (a API não tem rede); só então marca aqui."""
    origem = f"{caixa['provedor']}:{caixa['endereco']}"
    for t in con.execute("select id, externo_id from tarefa where origem=? and estado='aberta' and pedido_concluir_em is not null", (origem,)).fetchall():
        if caixa["provedor"] == "graph":
            cli.concluir_tarefa(caixa["endereco"], t["externo_id"])
        else:
            cli.concluir_tarefa(t["externo_id"])
        con.execute("update tarefa set estado='concluida' where id=?", (t["id"],))


def rodar(con, cliente_de: Callable[[dict], object | None], agora: dt.datetime) -> ResumoTrabalho:
    caixas = msgs = evs = ts = falhas = 0
    with registrar_rodada(con, "trabalho") as r:
        for c in [dict(x) for x in con.execute("select * from caixa_email where estado='sim' and le=1 order by id")]:
            caixas += 1
            try:
                m, e, t = _processar(con, c, cliente_de)
            except (ErroGraph, ErroGoogle, PermissionError) as ex:
                falhas += 1
                if isinstance(ex, PermissionError) or CREDENCIAL.search(str(ex)):
                    _novo(con, agora, "caixa_reconectar", c["id"], {"endereco": c["endereco"], "provedor": c["provedor"]})
                continue
            msgs, evs, ts = msgs + m, evs + e, ts + t
            _fechar_aviso(con, c["id"], agora)
        r.lidos, r.novos = caixas, msgs
        if falhas:
            r.aviso = f"{falhas} caixa(s) com falha"
    return ResumoTrabalho(caixas, msgs, evs, ts, falhas)
