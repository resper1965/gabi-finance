"""Destinos da escuta: o que acontece com uma mensagem já classificada. Protocol + DestinosReais."""
import base64
import datetime as dt
import json
from pathlib import Path
from typing import Protocol

from gabi.cobrar import pedidos
from gabi.fontes.paperless import Paperless


class Destinos(Protocol):
    def pedido(self, con, remetente_pessoa_id: str, numero: str, msg: dict, campos: dict) -> None:
        """ValueError = pedido incompleto (a rodada marca a mensagem como falhou e avisa)."""

    def saude(self, con, msg: dict, campos: dict) -> None: ...

    def crise(self, con, numero: str, nome: str | None) -> None:
        """Nunca recebe o texto da mensagem."""

    def documento(self, con, msg: dict) -> None:
        """Entrega o anexo da mensagem (Paperless). Se levantar, o anexo NÃO é apagado e a mensagem fica falhou."""


TAG_ENTRADA = "gabi:entrada-whatsapp"
TAG_SAUDE = "gabi:saude-exame"
_JANELA_CRISE = dt.timedelta(minutes=60)


def _agora() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _quando(s: str) -> dt.datetime | None:
    try:
        d = dt.datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def _chave_ou_linha(v) -> tuple[str | None, str | None]:
    """(pix_chave, linha_digitavel): linha digitável é quase só dígitos com 44 ou mais; o resto é chave Pix."""
    s = str(v or "").strip()
    if not s:
        return None, None
    compacto = "".join(ch for ch in s if ch not in " .-")
    dig = sum(ch.isdigit() for ch in compacto)
    if dig >= 44 and dig >= 0.9 * len(compacto):
        return None, s
    return s, None


def _nome(con, numero: str) -> str | None:
    r = con.execute("select nome from escuta_remetente where numero=?", (numero,)).fetchone()
    if r and r["nome"]:
        return r["nome"]
    for p in con.execute("select nome, dados from pessoa where excluido_em is null"):
        try:
            canais = (json.loads(p["dados"] or "{}") or {}).get("canais") or []
        except (TypeError, ValueError):
            continue
        if f"whatsapp:{numero}" in canais and p["nome"]:
            return p["nome"]
    return None


def _ler(msg: dict) -> tuple[bytes, str]:
    """Lê o anexo (só leitura, no caminho dado; o processar já garantiu que está no spool)."""
    caminho = Path(msg["anexo_caminho"])
    with open(caminho, "rb") as f:
        return f.read(), caminho.name


class DestinosReais:
    def __init__(self, paperless: Paperless, cobrar_registrar=pedidos.registrar):
        self.paperless, self._registrar = paperless, cobrar_registrar

    def _enviar_anexo(self, msg: dict, tag: str):
        conteudo, nome = _ler(msg)
        return self.paperless.enviar(conteudo, nome, [tag])

    def pedido(self, con, remetente_pessoa_id: str, numero: str, msg: dict, campos: dict) -> None:
        pix, linha = _chave_ou_linha(campos.get("chave_ou_linha"))
        descricao = " - ".join(str(campos[k]) for k in ("favorecido", "motivo") if campos.get(k)) or "pedido via WhatsApp"
        valor = campos.get("valor")
        enviar = None
        b64 = None
        if msg.get("anexo_caminho"):
            conteudo, nome = _ler(msg)
            b64 = base64.b64encode(conteudo).decode()

            def enviar(c: bytes, _nome_padrao: str):
                r = self.paperless.enviar(c, nome, [TAG_ENTRADA])
                return r if isinstance(r, int) else None  # o Paperless devolve a tarefa de consumo; o id do documento só existe depois
        self._registrar(
            con, solicitante=f"whatsapp:{numero}", canal="whatsapp", mensagem_original=msg.get("texto") or "", descricao=descricao,
            valor=None if valor is None else str(valor), vencimento=campos.get("vence") or None, anexo_base64=b64, anexo_paperless_id=None,
            pix_chave=pix, linha_digitavel=linha, para_quem=None, enviar_ao_paperless=enviar)

    def saude(self, con, msg: dict, campos: dict) -> None:
        """Nunca grava texto nem campos no gabi.db. Com anexo: Paperless. Sem anexo: só um aviso para abrir a conversa."""
        if msg.get("anexo_caminho"):
            self._enviar_anexo(msg, TAG_SAUDE)
            return
        numero = msg["de"]
        con.execute("insert into aviso(tipo, payload, criado_em) values ('escuta_saude', ?, ?)",
                    (json.dumps({"numero": numero, "nome": _nome(con, numero)}, ensure_ascii=False), _agora().isoformat()))

    def crise(self, con, numero: str, nome: str | None) -> None:
        """Um aviso por número por hora; payload só com número e nome."""
        corte = _agora() - _JANELA_CRISE
        for r in con.execute("select payload, criado_em from aviso where tipo='escuta_atencao'"):
            q = _quando(r["criado_em"])
            try:
                n = json.loads(r["payload"]).get("numero")
            except (TypeError, ValueError, AttributeError):
                continue
            if n == numero and q is not None and q > corte:
                return
        con.execute("insert into aviso(tipo, payload, criado_em) values ('escuta_atencao', ?, ?)",
                    (json.dumps({"numero": numero, "nome": nome}, ensure_ascii=False), _agora().isoformat()))

    def documento(self, con, msg: dict) -> None:
        self._enviar_anexo(msg, TAG_ENTRADA)
