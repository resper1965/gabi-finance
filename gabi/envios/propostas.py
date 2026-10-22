"""Criação das propostas de envio (evento de agenda, mensagem do Teams) que só saem depois do "Enviar" do dono no painel.
Consome: parametro (envios.escrita, envios.contas_agenda), agenda_fonte, teams_fonte, teams_conversa, contato_google e contato_google_email. Grava: envio_proposta (migração 0076).
Sem rede e sem envio: aqui só se valida, resolve nomes e grava o conteúdo canônico. Título, texto, nome e e-mail nunca vão para log nem para mensagem de erro: as falhas são códigos fixos (ErroEnvio.codigo)."""
import base64
import datetime as dt
import hashlib
import json
import re
import secrets
import unicodedata
from zoneinfo import ZoneInfo

from gabi.db import transacao

FUSO = "America/Sao_Paulo"
_SP = ZoneInfo(FUSO)
_UTC = dt.timezone.utc
_EMAIL = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")
_DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
MAX_TITULO, MIN_DURACAO, MAX_DURACAO, MAX_CONVIDADOS, MAX_TEXTO, MAX_DESCRICAO = 200, 5, 720, 30, 4000, 2000


class ErroEnvio(Exception):
    """Falha de proposta com código fixo (nunca texto de usuário); `candidatos` só nos casos ambíguos."""

    def __init__(self, codigo: str, mensagem: str = "", candidatos: list[dict] | None = None):
        super().__init__(codigo)
        self.codigo, self.mensagem, self.candidatos = codigo, mensagem or codigo, candidatos


def _parametro(con, chave: str, padrao):
    r = con.execute("select valor from parametro where chave=?", (chave,)).fetchone()
    if r is None:
        return padrao
    try:
        return json.loads(r[0])
    except (ValueError, TypeError):
        return padrao


def escrita_ligada(con) -> bool:
    """Só o valor JSON "ligado" liga; ausente ou qualquer outra coisa = desligado."""
    return _parametro(con, "envios.escrita", None) == "ligado"


def contas_agenda(con) -> list[str]:
    v = _parametro(con, "envios.contas_agenda", [])
    if not isinstance(v, list):
        return []
    return list(dict.fromkeys(x.strip().lower() for x in v if isinstance(x, str) and x.strip()))


def provedor_da_conta(con, conta: str) -> str | None:
    r = con.execute("select provedor from agenda_fonte where lower(conta)=? and calendario_id='primary'", (conta.strip().lower(),)).fetchone()
    return r[0] if r else None


def contas_teams(con) -> list[str]:
    return [r[0].lower() for r in con.execute("select conta from teams_fonte where estado='sim' order by conta")]


def normalizar_nome(s: str) -> str:
    """Casefold sem acento, espaços colapsados."""
    sem = "".join(c for c in unicodedata.normalize("NFD", s or "") if not unicodedata.combining(c))
    return " ".join(sem.casefold().split())


def _invalida():
    return ErroEnvio("requisicao_invalida")


def resolver_convidados(con, itens: list[str]) -> list[str]:
    """E-mail vira minúsculo; nome casa por igualdade do nome inteiro (sem caixa e acento) com contato_google, de qualquer conta.
    Nome com 0 ou mais de 1 e-mail: convidado_ambiguo com os candidatos. Sem duplicar, na ordem dada."""
    saida: list[str] = []
    for item in itens:
        if not isinstance(item, str) or not item.strip():
            raise ErroEnvio("convidado_invalido")
        if "@" in item:
            email = item.strip().lower()
            if not _EMAIL.match(email):
                raise ErroEnvio("convidado_invalido")
            achados = [email]
        else:
            alvo = normalizar_nome(item)
            achados, cands = [], {}
            for r in con.execute("select g.nome, e.email from contato_google g join contato_google_email e on e.conta=g.conta and e.telefone=g.telefone where g.nome is not null"):
                if normalizar_nome(r["nome"]) == alvo and r["email"].strip():
                    cands.setdefault(r["email"].strip().lower(), r["nome"])
            achados = list(cands)
            if len(achados) != 1:
                raise ErroEnvio("convidado_ambiguo", candidatos=[{"nome": n, "email": e} for e, n in cands.items()])
        if achados[0] not in saida:
            saida.append(achados[0])
    return saida


def _conta_teams(con, conta: str) -> str:
    c = (conta or "").strip().lower()
    if c not in contas_teams(con):
        raise ErroEnvio("conta_nao_permitida")
    return c


def resolver_chat(con, conta: str, nome: str) -> dict:
    """Chat do Teams da conta pelo `de_nome` (sem caixa e acento); 0 ou mais de 1 dá destino_ambiguo."""
    alvo = normalizar_nome(nome)
    achados = [r for r in con.execute("select chat_id, tipo, de_nome from teams_conversa where lower(conta)=? and de_nome is not null order by chat_id", (conta.strip().lower(),))
               if alvo and normalizar_nome(r["de_nome"]) == alvo]
    if len(achados) != 1:
        raise ErroEnvio("destino_ambiguo", candidatos=[{"nome": r["de_nome"], "tipo": r["tipo"]} for r in achados])
    return {"chat_id": achados[0]["chat_id"], "destino_nome": achados[0]["de_nome"]}


def _utc(t: dt.datetime) -> str:
    return t.astimezone(_UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonico(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _gravar(con, agora: dt.datetime, tipo: str, conta: str, obj: dict, vence: dt.datetime) -> dict:
    conteudo = _canonico(obj)
    chave = base64.b32hexencode(secrets.token_bytes(16)).decode().lower().rstrip("=")
    criada, vence_em = _utc(agora), _utc(vence)
    with transacao(con, imediata=True):
        cur = con.execute("insert into envio_proposta(tipo, conta, conteudo, hash, chave, criada_em, vence_em) values (?,?,?,?,?,?,?)",
                          (tipo, conta, conteudo, hashlib.sha256(conteudo.encode()).hexdigest(), chave, criada, vence_em))
    return {"id": cur.lastrowid, "estado": "pendente", "vence_em": vence_em}


def _texto(texto) -> str:
    if not isinstance(texto, str) or not (1 <= len(texto) <= MAX_TEXTO) or not texto.strip():
        raise _invalida()
    return texto


def _inicio(inicio: str) -> dt.datetime:
    try:
        t = dt.datetime.fromisoformat(inicio.strip())
    except (ValueError, AttributeError):
        raise _invalida()
    return t.replace(tzinfo=_SP) if t.tzinfo is None else t


def criar_evento(con, agora: dt.datetime, *, conta, titulo, inicio, duracao_min, convidados, descricao="", online=True) -> dict:
    if not isinstance(titulo, str) or not (1 <= len(titulo) <= MAX_TITULO) or not titulo.strip():
        raise _invalida()
    if isinstance(duracao_min, bool) or not isinstance(duracao_min, int) or not (MIN_DURACAO <= duracao_min <= MAX_DURACAO):
        raise _invalida()
    if not isinstance(convidados, list) or not (1 <= len(convidados) <= MAX_CONVIDADOS):
        raise _invalida()
    if not isinstance(descricao, str) or len(descricao) > MAX_DESCRICAO or not isinstance(online, bool):
        raise _invalida()
    c = (conta or "").strip().lower()
    prov = provedor_da_conta(con, c) if c in contas_agenda(con) else None
    if prov is None:
        raise ErroEnvio("conta_nao_permitida")
    ini = _inicio(inicio)
    if ini <= agora:
        raise ErroEnvio("inicio_passado")
    emails = resolver_convidados(con, convidados)
    fim = ini + dt.timedelta(minutes=duracao_min)
    obj = {"conta": c, "provedor": prov, "titulo": titulo, "inicio_utc": _utc(ini), "fim_utc": _utc(fim), "fuso": FUSO,
           "convidados": emails, "descricao": descricao, "online": online}
    r = _gravar(con, agora, "evento", c, obj, min(agora + dt.timedelta(hours=24), ini))
    li, lf = ini.astimezone(_SP), fim.astimezone(_SP)
    n = len(emails)
    r["resumo"] = (f"Evento '{titulo}' {_DIAS[li.weekday()]} {li:%d/%m %H:%M}–{lf:%H:%M} ({c.split('@')[-1].split('.')[0]}), "
                   f"{n} convidado{'s' if n != 1 else ''}")
    return r


def criar_teams_chat(con, agora: dt.datetime, *, conta, chat_com, texto) -> dict:
    texto = _texto(texto)
    c = _conta_teams(con, conta)
    alvo = resolver_chat(con, c, chat_com)
    r = _gravar(con, agora, "teams_chat", c, {"conta": c, **alvo, "texto": texto}, agora + dt.timedelta(hours=24))
    r["resumo"] = f"Teams: chat com {alvo['destino_nome']}"
    return r


def criar_teams_canal(con, agora: dt.datetime, *, conta, equipe_id, canal_id, equipe_nome, canal_nome, texto) -> dict:
    texto = _texto(texto)
    c = _conta_teams(con, conta)
    if not all(isinstance(x, str) and x.strip() for x in (equipe_id, canal_id, equipe_nome, canal_nome)):
        raise _invalida()
    obj = {"conta": c, "equipe_id": equipe_id, "canal_id": canal_id, "equipe_nome": equipe_nome, "canal_nome": canal_nome, "texto": texto}
    r = _gravar(con, agora, "teams_canal", c, obj, agora + dt.timedelta(hours=24))
    r["resumo"] = f"Teams: canal {canal_nome} da equipe {equipe_nome}"
    return r
