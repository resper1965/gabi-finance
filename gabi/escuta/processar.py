"""Rodada da escuta: uma passada ordenada por recebida_em, uma transação por mensagem.
Ordem de decisão: grupo não aprovado, bloqueado/ignorado, palavra de risco (sem modelo, para todo não-bloqueado),
fora da lista (retida, sem modelo), aprovado (modelo). Texto de mensagem nunca vai a log, exceção ou aviso."""
import json
import logging
from pathlib import Path

from gabi.cobrar.cadastro import dados
from gabi.db import transacao
from gabi.dinheiro.modelo import ModeloCliente, Orcamento
from gabi.escuta.classificar import classificar
from gabi.escuta.crise import palavras_risco, tem_risco
from gabi.escuta.destinos import Destinos
from gabi.escuta.remetentes import _dentro, avisar_novo, estado_remetente

log = logging.getLogger(__name__)


class _PedidoIncompleto(Exception):
    pass


def _aviso(con, tipo: str, payload: dict, agora: str) -> None:
    con.execute("insert into aviso(tipo, payload, criado_em) values (?,?,?)", (tipo, json.dumps(payload, ensure_ascii=False), agora))


def _aviso_sem_modelo(con, agora: str) -> None:
    """Um por dia."""
    if con.execute("select 1 from aviso where tipo='escuta_sem_modelo' and substr(criado_em,1,10)=?", (agora[:10],)).fetchone():
        return
    _aviso(con, "escuta_sem_modelo", {"motivo": "sem modelo ou teto de custo estourado"}, agora)


def _nome(con, numero: str, pessoa_id: str | None) -> str | None:
    if pessoa_id:
        r = con.execute("select nome from pessoa where id=?", (pessoa_id,)).fetchone()
        if r and r["nome"]:
            return r["nome"]
    r = con.execute("select nome from escuta_remetente where numero=?", (numero,)).fetchone()
    return r["nome"] if r else None


def _fechar(con, id_: int, agora: str, tipo=None, confianca=None, campos=None, apagar=False, estado="processada") -> None:
    con.execute(
        "update escuta_msg set estado=?, tipo=?, confianca=?, campos=?, processada_em=?"
        + (", texto=null, anexo_caminho=null" if apagar else "") + " where id=?",
        (estado, tipo, confianca, json.dumps(campos, ensure_ascii=False) if campos else None, agora, id_))


def _falhou(con, id_: int, agora: str, aviso: tuple[str, dict] | None = None) -> None:
    with transacao(con):
        con.execute("update escuta_msg set estado='falhou', processada_em=? where id=?", (agora, id_))
        if aviso:
            _aviso(con, aviso[0], aviso[1], agora)


def _uma(con, destinos, cliente, orcamento, agora, modo, m, palavras, c, spool, apagar: list) -> None:
    """Roda dentro da transação da mensagem. Atualiza contadores em c; arquivos a apagar vão em `apagar` (após o commit)."""
    id_, texto, ativo = m["id"], m["texto"], modo == "ativo"
    if m["grupo"]:
        g = con.execute("select aprovado from escuta_grupo where id_grupo=?", (m["id_grupo"],)).fetchone()
        if not (g and g["aprovado"] == 1):
            _fechar(con, id_, agora)
            return
        numero, estado, pid = m["de"], "aprovado", None
    else:
        numero = m["de"]
        estado, pid = estado_remetente(con, numero)
        if estado in ("ignorado", "bloqueado"):
            if estado == "ignorado" and tem_risco(texto or "", palavras):
                if ativo:
                    destinos.crise(con, numero, _nome(con, numero, None))
                _fechar(con, id_, agora, tipo="crise", apagar=True)
                apagar.append(m["anexo_caminho"])
                return
            _fechar(con, id_, agora, apagar=True)
            apagar.append(m["anexo_caminho"])
            return
    nome = _nome(con, numero, pid)
    aprovado = estado == "aprovado"
    if tem_risco(texto or "", palavras):  # independe do modelo e do remetente estar aprovado
        if ativo:
            destinos.crise(con, numero, nome)
        _fechar(con, id_, agora, tipo="crise", apagar=not aprovado)
        if not aprovado:
            apagar.append(m["anexo_caminho"])
        c["classificadas"] += 1
        return
    if not aprovado:
        avisar_novo(con, numero, agora)
        con.execute("update escuta_msg set estado='retida' where id=?", (id_,))
        c["retidas"] += 1
        return
    if not (texto or "").strip():
        _fechar(con, id_, agora, tipo="nada", apagar=True)
        apagar.append(m["anexo_caminho"])
        return
    r = classificar(texto, cliente, orcamento)
    if r is None:  # fica nova e tenta de novo na próxima rodada
        _aviso_sem_modelo(con, agora)
        return
    tipo, campos = r.tipo, r.campos
    if tipo == "pedido" and not (pid and dados(con.execute("select dados from pessoa where id=?", (pid,)).fetchone()).get("pode_pedir") is True):
        tipo, campos = "nada", {}
        c["falhas"] += 1
    if tipo == "nada":
        _fechar(con, id_, agora, tipo="nada", confianca=r.confianca, apagar=True)
        apagar.append(m["anexo_caminho"])
        c["classificadas"] += 1
        return
    if ativo:
        if tipo == "pedido":
            try:
                destinos.pedido(con, pid, numero, dict(m), campos)
            except ValueError as e:
                raise _PedidoIncompleto() from e
        elif tipo == "saude":
            destinos.saude(con, dict(m), campos)
        elif tipo == "crise":
            destinos.crise(con, numero, nome)
    _fechar(con, id_, agora, tipo=tipo, confianca=r.confianca, campos=campos)
    c["classificadas"] += 1


def processar(con, destinos: Destinos, cliente: ModeloCliente | None, orcamento: Orcamento, agora: str,
              modo: str = "registro", spool: Path | None = None) -> dict:
    if modo not in ("registro", "ativo"):
        raise ValueError(f"modo inválido: {modo!r}")
    c = {"novas": 0, "classificadas": 0, "retidas": 0, "falhas": 0}
    palavras = palavras_risco(con)
    ids = [(r["id"], r["estado"]) for r in con.execute(
        "select id, estado from escuta_msg where estado in ('nova','retida') order by recebida_em, id")]
    for id_, estado_ini in ids:
        if estado_ini == "nova":
            c["novas"] += 1
        apagar: list = []
        try:
            with transacao(con):
                m = con.execute("select * from escuta_msg where id=? and estado in ('nova','retida')", (id_,)).fetchone()
                if m is None:
                    continue
                _uma(con, destinos, cliente, orcamento, agora, modo, m, palavras, c, spool, apagar)
        except _PedidoIncompleto as e:
            # pedido incompleto vem de Destinos.pedido; a mensagem fica falhou, sem texto no aviso
            log.warning("escuta: mensagem %s falhou (pedido incompleto)", id_)
            c["falhas"] += 1
            m = con.execute("select de from escuta_msg where id=?", (id_,)).fetchone()
            numero = m["de"]
            _falhou(con, id_, agora, ("escuta_pedido_incompleto", {"numero": numero, "nome": _nome(con, numero, estado_remetente(con, numero)[1])}))
            continue
        except Exception as e:
            log.warning("escuta: mensagem %s falhou (%s)", id_, type(e).__name__)
            c["falhas"] += 1
            _falhou(con, id_, agora)
            continue
        if spool is not None:
            for a in apagar:
                if a and _dentro(a, Path(spool)):
                    try:
                        Path(a).unlink(missing_ok=True)
                    except OSError:
                        pass
    return c
