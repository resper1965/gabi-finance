"""Executor do envio: depois do "Enviar" do dono, reserva a proposta, faz UMA chamada ao provedor e fecha em enviada, falhou ou incerto.
Consome: envio_proposta (via propostas.reservar/concluir, que já auditam em `decisao`), Google (evento_criar) e Graph da ness (evento_criar, convite_responder,
teams_chat_enviar, teams_canal_enviar) pela ponte. Grava: o estado final da proposta; trava em <pasta do banco>/locks/envios.lock.
Nunca repete: 5xx e erro sem status HTTP nem código conhecido viram incerto (o provedor pode ter recebido); 4xx e recusas certas viram falhou. Motivos são códigos fixos; a mensagem do provedor
não vai para log, stderr nem `decisao`."""
import contextlib
import datetime as dt
import fcntl
import json
import re
from pathlib import Path

from gabi.envios.propostas import ErroEnvio, concluir, reservar

_STATUS = re.compile(r"-> (\d{3})$")
_TIPO = re.compile(r"^[A-Za-z_]\w*: ")  # prefixo "<Tipo>: " que a ponte põe quando o tipo do erro remoto é outro
# Recusas certas antes do envio (nada saiu): falhou com código fixo. Casam por igualdade ou como prefixo "<código>: ..." (sem guardar o resto).
_FIXOS = {"login_teams_expirado": "login_teams_expirado", "teams_sem_login": "teams_sem_login",
          "login_teams_conta_diferente": "login_teams_conta_diferente", "conta não autorizada": "conta_nao_permitida",
          "token recusado": "login_google_expirado", "chave inválida": "requisicao_invalida", "evento inválido": "requisicao_invalida",
          "chat inválido": "requisicao_invalida", "texto inválido": "requisicao_invalida", "equipe inválida": "requisicao_invalida",
          "canal inválido": "requisicao_invalida", "conta inválida": "requisicao_invalida", "link inválido": "requisicao_invalida"}


def _banco(con) -> Path:
    """Arquivo do banco principal da conexão (a trava fica ao lado dele)."""
    for r in con.execute("pragma database_list"):
        if r[1] == "main" and r[2]:
            return Path(r[2])
    raise ErroEnvio("requisicao_invalida")  # banco em memória: sem pasta para a trava


@contextlib.contextmanager
def trava(banco: Path):
    """Um envio por vez (flock não bloqueante em <pasta do banco>/locks/envios.lock). Rende True com a trava, False se outro envio a tem."""
    pasta = Path(banco).parent / "locks"
    pasta.mkdir(parents=True, exist_ok=True)
    f = open(pasta / "envios.lock", "w")
    try:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        f.close()  # fechar libera a trava, mesmo em erro


def _motivo(erro: Exception, tipo: str | None = None) -> tuple[str, str]:
    """(estado, motivo) a partir só da mensagem (a ponte preserva a mensagem, não o atributo .status). 4xx = falhou; 5xx = incerto.
    Num convite_resposta, 404/409 = o convite mudou ou sumiu: falhou com convite_obsoleto (pode-se propor de novo)."""
    msg = str(erro)
    m = _STATUS.search(msg)
    if m:
        if tipo == "convite_resposta" and m.group(1) in ("404", "409"):
            return "falhou", "convite_obsoleto"
        # 5xx num POST pode ter sido aceito (Graph/Teams sem idempotência): incerto, nunca repetido
        return ("incerto" if m.group(1).startswith("5") else "falhou"), f"provedor_{m.group(1)}"
    for texto in (msg, _TIPO.sub("", msg, count=1)):
        for k, motivo in _FIXOS.items():
            if texto == k or texto.startswith(k + ":"):
                return "falhou", motivo
    return "incerto", "sem_confirmacao"


def _chamar(l: dict, conteudo: dict, google, graph) -> dict | None:
    if l["tipo"] == "evento":
        prov = google if conteudo.get("provedor") == "google" else graph if conteudo.get("provedor") == "graph" else None
        if prov is None:
            return None
        return prov.evento_criar(l["conta"], l["chave"], conteudo)
    if l["tipo"] == "convite_resposta":
        if conteudo.get("provedor") != "graph" or graph is None:
            return None
        return graph.convite_responder(l["conta"], l["chave"], conteudo["externo_id"], conteudo["resposta"], conteudo["serie_id"])
    if graph is None:
        return None
    if l["tipo"] == "teams_chat":
        return graph.teams_chat_enviar(l["conta"], conteudo["chat_id"], conteudo["texto"])
    return graph.teams_canal_enviar(l["conta"], conteudo["equipe_id"], conteudo["canal_id"], conteudo["texto"])


def enviar(con, proposta_id: int, hash: str, quem: str, agora: dt.datetime, google, graph) -> dict:
    """Envia uma proposta pendente uma única vez. Propaga o ErroEnvio de `reservar` (menos convite_obsoleto, que vira falhou sem chamar o provedor);
    trava ocupada = ErroEnvio("conflito") sem reservar.
    Devolve {"id", "estado"} e, se não enviada, "motivo"."""
    with trava(_banco(con)) as tenho:
        if not tenho:
            raise ErroEnvio("conflito")
        try:
            l = reservar(con, proposta_id, hash, quem, agora)
        except ErroEnvio as e:
            if e.codigo != "convite_obsoleto":
                raise
            return {"id": proposta_id, "estado": "falhou", "motivo": "convite_obsoleto"}  # `reservar` já gravou falhou; o Graph não foi chamado
        conteudo = json.loads(l["conteudo"])
        try:
            r = _chamar(l, conteudo, google, graph)
        except Exception as e:  # noqa: BLE001 - uma tentativa só; o erro vira código fixo
            estado, motivo = _motivo(e, l["tipo"])
        else:
            if r is None:
                estado, motivo = "falhou", "fonte_indisponivel"
            else:
                concluir(con, proposta_id, "enviada", externo_id=r["externo_id"], agora=agora)
                return {"id": proposta_id, "estado": "enviada"}
        concluir(con, proposta_id, estado, motivo=motivo, agora=agora)
        return {"id": proposta_id, "estado": estado, "motivo": motivo}
