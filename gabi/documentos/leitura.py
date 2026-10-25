"""Rodada diária de leitura: lista o Paperless, pula o que já foi lido (mesmo `modified`), manda só o OCR ao modelo, confere local e
registra PROPOSTA para o Ricardo aprovar (nada cria documento nem bem). Motivos e logs levam só contagens e códigos curtos fixos,
nunca número nem texto do documento. Consome: extracao, repositorio, gabi.correio.modelo.Falha, avisos._parametro."""
import datetime as dt
import logging
from dataclasses import dataclass

from gabi.correio.modelo import Falha
from gabi.documentos import extracao, repositorio
from gabi.documentos.repositorio import ErroDocumentos

log = logging.getLogger(__name__)
MAX_TENTATIVAS = 3
MIN_UTEIS = 40
MAX_FORA_DO_AR = 3  # falhas temporárias seguidas do modelo que param a rodada sem contar tentativa
FORA_DO_AR = "falha temporária do modelo"  # a do `_chamar` quando o cliente lança exceção (queda, timeout)


@dataclass
class ResumoLeitura:
    lidos: int = 0
    propostas: int = 0
    sem_texto: int = 0
    sem_documento: int = 0
    falhas: int = 0
    parada: str | None = None  # modelo ausente, teto ou limite: o resto fica para a próxima rodada


def _uteis(ocr: str) -> int:
    return sum(c.isalnum() for c in ocr)


def _pendentes(con, docs: list[dict], limite: int) -> list[tuple[dict, int]]:
    """(documento, tentativas já feitas para este `modified`) dos que ainda precisam de leitura, em ordem de id, até `limite`."""
    feitos = {r["paperless_id"]: r for r in con.execute("select paperless_id, modificado, estado, tentativas from documento_leitura")}
    saida = []
    for d in sorted((d for d in docs if isinstance(d.get("id"), int)), key=lambda d: d["id"]):
        r = feitos.get(d["id"])
        mesmo = r is not None and r["modificado"] == d.get("modified")
        if mesmo and (r["estado"] != "falhou" or r["tentativas"] >= MAX_TENTATIVAS):
            continue
        saida.append((d, r["tentativas"] if mesmo else 0))
        if len(saida) >= limite:
            break
    return saida


def _gravar(con, pid: int, modificado, estado: str, motivo: str | None, tentativas: int, agora: dt.datetime) -> None:
    con.execute("insert into documento_leitura(paperless_id, modificado, estado, motivo, custo, tentativas, lido_em) values (?,?,?,?,0,?,?) "
                "on conflict(paperless_id) do update set modificado=excluded.modificado, estado=excluded.estado, motivo=excluded.motivo, "
                "tentativas=excluded.tentativas, lido_em=excluded.lido_em",
                (pid, modificado, estado, motivo, tentativas, repositorio.ts(agora)))


def ler(con, paperless, cliente, orcamento, agora: dt.datetime, *, max_por_rodada: int, max_caracteres: int) -> ResumoLeitura:
    """Sem cliente de modelo, para antes de tudo (`parada`, nada marcado). Falha temporária do modelo conta tentativa, mas
    MAX_FORA_DO_AR seguidas param a rodada sem contar nenhuma das três (modelo fora do ar não esgota as tentativas)."""
    r = ResumoLeitura()
    if cliente is None:
        r.parada = "modelo não configurado"
        log.info("documentos: parada (modelo não configurado)")
        return r
    seguidas: list[tuple] = []  # falhas temporárias seguidas ainda não gravadas

    def gravar_seguidas():
        for pid_, mod_, motivo_, tent_ in seguidas:
            _gravar(con, pid_, mod_, "falhou", motivo_, tent_ + 1, agora)
            r.falhas += 1
        seguidas.clear()

    for d, tentativas in _pendentes(con, paperless.docs(), max_por_rodada):
        pid, mod = d["id"], d.get("modified")
        try:
            ocr = d["content"] if "content" in d else paperless.documento(pid).get("content")
        except Exception:  # noqa: BLE001 - um documento fora do ar não derruba a rodada
            ocr = False
        if ocr is False:
            _gravar(con, pid, mod, "falhou", "paperless_indisponivel", tentativas + 1, agora)
            r.falhas += 1
            continue
        ocr = ocr if isinstance(ocr, str) else ""
        if _uteis(ocr) < MIN_UTEIS:
            _gravar(con, pid, mod, "sem_texto", "ocr_curto", 0, agora)
            r.sem_texto += 1
            continue
        extraido = extracao.extrair(cliente, orcamento, d.get("title") or "", ocr, max_caracteres, data=d.get("created"))
        if isinstance(extraido, Falha):
            if not extraido.temporaria:  # sem modelo, teto ou limite: não marca, volta na próxima rodada
                seguidas.clear()
                r.parada = extraido.motivo
                break
            if extraido.motivo == FORA_DO_AR:
                seguidas.append((pid, mod, extraido.motivo[:80], tentativas))
                if len(seguidas) >= MAX_FORA_DO_AR:
                    seguidas.clear()
                    r.parada = "modelo indisponível"
                    break
                continue
            gravar_seguidas()
            _gravar(con, pid, mod, "falhou", extraido.motivo[:80], tentativas + 1, agora)
            r.falhas += 1
            continue
        gravar_seguidas()
        doc, bem, motivos = extracao.conferir(con, extraido, ocr)
        if doc is None:
            if motivos:
                _gravar(con, pid, mod, "falhou", "documento_invalido", tentativas + 1, agora)
                r.falhas += 1
            else:
                _gravar(con, pid, mod, "sem_documento", None, 0, agora)
                r.sem_documento += 1
            continue
        try:
            prop = repositorio.propor(con, doc, origem="leitura", paperless_id=pid, conferir=bool(motivos), motivos=motivos,
                                      agora=agora, bem_novo=bem)
        except ErroDocumentos:
            _gravar(con, pid, mod, "falhou", "proposta_invalida", tentativas + 1, agora)
            r.falhas += 1
            continue
        _gravar(con, pid, mod, "lido", None, 0, agora)
        r.lidos += 1
        r.propostas += prop is not None
    gravar_seguidas()
    log.info("documentos: lidos=%d propostas=%d sem_texto=%d sem_documento=%d falhas=%d", r.lidos, r.propostas, r.sem_texto, r.sem_documento, r.falhas)
    return r
