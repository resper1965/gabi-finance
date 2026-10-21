"""Piso de interação: só vira contato quem o dono conhece de verdade (resposta dele ou volume de mensagens nos últimos 12 meses).
Devolve só contagens; nada aqui imprime nem registra endereço, nome ou número."""
import re
from datetime import datetime, timedelta, timezone

from gabi.correio.regras import endereco as _endereco

JANELA_DIAS = 365
PISO_MENSAGENS = 5
PISO_RESPOSTAS = 1

# Remetente automático: o endereço diz que ninguém lê a resposta. Fora disso, só `lista` e a classe `lixo` (promoção/notificação) descartam.
_AUTOMATICO = re.compile(r"noreply|no-reply|donotreply|mailer-daemon|notifica|newsletter")


def _fmt(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _digitos(t: str | None) -> str:
    return re.sub(r"\D", "", (t or "").split("@")[0])


def interacao(con, agora: str, endereco: str | None = None, telefone: str | None = None) -> dict:
    """{"mensagens", "respostas"} na janela [agora - JANELA_DIAS, agora]. E-mail: mensagens recebidas do endereço (fora lista, classe lixo e remetente automático)
    e endereços respondidos pelo dono. Telefone: mensagens de escuta_msg; `escuta_msg` não registra o que o dono envia, então respostas é sempre 0 para telefone."""
    fim = datetime.strptime(agora, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    ini, fim = _fmt(fim - timedelta(days=JANELA_DIAS)), _fmt(fim)
    mensagens = respostas = 0
    end = (endereco or "").strip().lower()
    if end and not _AUTOMATICO.search(end):
        for m in con.execute("select remetente from email_msg where lower(remetente) like ? and lista=0 and coalesce(classe,'')<>'lixo' "
                             "and recebida_em>=? and recebida_em<=?", (f"%{end}%", ini, fim)):
            mensagens += _endereco(m["remetente"]) == end
        respostas = con.execute("select count(*) from email_respondido where lower(endereco)=? and em>=? and em<=?", (end, ini, fim)).fetchone()[0]
    if telefone:
        # `escuta_msg.de` guarda o E.164 normalizado (igual a escuta_remetente.numero), mas casa por dígitos para não depender de '+' ou de JID.
        alvo = _digitos(telefone)
        for m in con.execute("select de from escuta_msg where grupo=0 and instr(de, ?)>0 and recebida_em>=? and recebida_em<=?", (alvo[-8:], ini, fim)):
            mensagens += _digitos(m["de"]) == alvo
    return {"mensagens": mensagens, "respostas": respostas}


def passa_piso(r: dict) -> bool:
    return r["respostas"] >= PISO_RESPOSTAS or r["mensagens"] >= PISO_MENSAGENS
