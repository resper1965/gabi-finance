"""Destinos da escuta: o que acontece com uma mensagem já classificada. Protocol + DestinosReais."""
import base64
import datetime as dt
import json
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from gabi.cobrar import pedidos
from gabi.escuta import spool_seguro
from gabi.fontes.paperless import Paperless


class Destinos(Protocol):
    def pedido(self, con, remetente_pessoa_id: str, numero: str, msg: dict, campos: dict) -> None:
        """ValueError = pedido incompleto (a rodada marca a mensagem como falhou e avisa)."""

    def saude(self, con, msg: dict, campos: dict) -> None: ...

    def crise(self, con, numero: str, nome: str | None, agora: str | None = None) -> None:
        """Nunca recebe o texto da mensagem."""

    def documento(self, con, msg: dict) -> None:
        """Entrega o anexo da mensagem (Paperless). Se levantar, o anexo NÃO é apagado e a mensagem fica falhou."""


TAG_ENTRADA = "gabi:entrada-whatsapp"
TAG_SAUDE = "gabi:saude-exame"
_JANELA_CRISE = dt.timedelta(minutes=60)


BRT = ZoneInfo("America/Sao_Paulo")


def _agora() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _quando(s: str) -> dt.datetime | None:
    try:
        d = dt.datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=BRT)  # sem offset vale Brasília, como no spool e nos avisos


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


def _ler(msg: dict, spool: Path | None, maximo: int) -> tuple[bytes, str]:
    """Lê o anexo pelo helper ancorado em descritor (gabi.escuta.spool_seguro): o caminho do banco tem de ser exatamente
    <spool>/anexos/<nome>; arquivo regular, sem symlink, tamanho checado antes de ler. RuntimeError = a mensagem falha, o arquivo fica."""
    try:
        return spool_seguro.abrir_anexo(spool, msg["anexo_caminho"], maximo)
    except (OSError, ValueError) as e:
        raise RuntimeError("anexo ilegível") from e


class DestinosReais:
    def __init__(self, paperless: Paperless, cobrar_registrar=pedidos.registrar, *, spool: Path | None = None,
                 anexo_max_bytes: int = 25 * 1024 * 1024):
        self.paperless, self._registrar, self._spool, self._max = paperless, cobrar_registrar, spool, anexo_max_bytes

    def _enviar_anexo(self, msg: dict, tag: str):
        conteudo, nome = _ler(msg, self._spool, self._max)
        return self.paperless.enviar(conteudo, nome, [tag])

    def pedido(self, con, remetente_pessoa_id: str, numero: str, msg: dict, campos: dict) -> None:
        pix, linha = _chave_ou_linha(campos.get("chave_ou_linha"))
        descricao = " - ".join(str(campos[k]) for k in ("favorecido", "motivo") if campos.get(k)) or "pedido via WhatsApp"
        valor = campos.get("valor")
        enviar = None
        b64 = None
        if msg.get("anexo_caminho"):
            conteudo, nome = _ler(msg, self._spool, self._max)
            b64 = base64.b64encode(conteudo).decode()

            def enviar(c: bytes, _nome_padrao: str):
                r = self.paperless.enviar(c, nome, [TAG_ENTRADA])
                return r if isinstance(r, int) else None  # o Paperless devolve a tarefa de consumo; o id do documento só existe depois
        self._registrar(
            con, solicitante=f"whatsapp:{numero}", canal=pedidos.CANAL_ESCUTA, mensagem_original=msg.get("texto") or "", descricao=descricao,
            valor=valor, vencimento=campos.get("vence") or None, anexo_base64=b64, anexo_paperless_id=None,
            pix_chave=pix, linha_digitavel=linha, para_quem=None, enviar_ao_paperless=enviar)

    def saude(self, con, msg: dict, campos: dict) -> None:
        """Nunca grava texto nem campos no gabi.db. Com anexo: Paperless. Sem anexo: só um aviso para abrir a conversa."""
        if msg.get("anexo_caminho"):
            self._enviar_anexo(msg, TAG_SAUDE)
            return
        numero = msg["de"]
        con.execute("insert into aviso(tipo, payload, criado_em) values ('escuta_saude', ?, ?)",
                    (json.dumps({"numero": numero, "nome": _nome(con, numero)}, ensure_ascii=False), _agora().isoformat()))

    def crise(self, con, numero: str, nome: str | None, agora: str | None = None) -> None:
        """Um aviso por número por hora; payload só com número e nome."""
        agora = agora or _agora().isoformat()
        t = _quando(agora) or _agora()
        corte = (t - _JANELA_CRISE).isoformat()  # mesmo formato de `agora`, então a comparação de texto no SQL vale
        if con.execute("select 1 from aviso where tipo='escuta_atencao' and json_extract(payload,'$.numero')=? and criado_em>? limit 1",
                       (numero, corte)).fetchone():
            return
        con.execute("insert into aviso(tipo, payload, criado_em) values ('escuta_atencao', ?, ?)",
                    (json.dumps({"numero": numero, "nome": nome}, ensure_ascii=False), agora))

    def documento(self, con, msg: dict) -> None:
        self._enviar_anexo(msg, TAG_ENTRADA)
