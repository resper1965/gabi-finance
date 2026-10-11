"""Rodada da escuta: mensagens com palavra de risco primeiro (sem modelo), depois as demais por recebida_em; uma transação por mensagem;
orçamento de tempo por rodada (escuta.tempo_max_s).
Ordem de decisão: grupo não aprovado, bloqueado/ignorado, palavra de risco (sem modelo, para todo não-bloqueado),
fora da lista (retida, sem modelo), aprovado (modelo). Texto de mensagem nunca vai a log, exceção ou aviso."""
import datetime as dt
import json
import logging
import sqlite3
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from gabi.cobrar.cadastro import dados
from gabi.db import transacao
from gabi.dinheiro.modelo import ModeloCliente, Orcamento
from gabi.cobrar.pedidos import SemEscopo
from gabi.escuta.classificar import Classificacao, Falha, classificar
from gabi.fontes.paperless import ErroPaperless
from gabi.escuta.crise import palavras_risco, tem_risco
from gabi.escuta.destinos import Destinos
from gabi.escuta import spool_seguro
from gabi.escuta.remetentes import avisar_novo, estado_remetente

log = logging.getLogger(__name__)
BRT = ZoneInfo("America/Sao_Paulo")


class _PedidoIncompleto(Exception):
    pass


def _aviso(con, tipo: str, payload: dict, agora: str) -> None:
    con.execute("insert into aviso(tipo, payload, criado_em) values (?,?,?)", (tipo, json.dumps(payload, ensure_ascii=False), agora))


def _aviso_sem_modelo(con, agora: str, motivo: str) -> None:
    """Um por dia. `motivo` é curto e fixo (vem de classificar.Falha), nunca texto de mensagem."""
    if con.execute("select 1 from aviso where tipo='escuta_sem_modelo' and substr(criado_em,1,10)=?", (agora[:10],)).fetchone():
        return
    _aviso(con, "escuta_sem_modelo", {"motivo": motivo}, agora)


MAX_TENTATIVAS = 8
_ESPERA_BASE = dt.timedelta(minutes=5)
_ESPERA_MAX = dt.timedelta(hours=6)
# Falha temporária de destino: Paperless/ponte fora do ar, rede. Tenta de novo com espera; nunca apaga texto/anexo por isso.
TEMPORARIAS = (ErroPaperless, ConnectionError, TimeoutError)


def _quando(s: str) -> dt.datetime:
    d = dt.datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=BRT)


def _esperando(proxima_em, agora: str) -> bool:
    if not proxima_em:
        return False
    try:
        return _quando(proxima_em) > _quando(agora)
    except (TypeError, ValueError):
        return False


def _adiar(con, id_: int, agora: str, c: dict, apagar_texto_se_desistir: bool = False) -> None:
    """Falha temporária: tentativas+1 e espera min(6 h, 5 min * 2^tentativas); a mensagem continua `nova`. Na 8ª, `falhou` + aviso
    `escuta_falhou` (só número e nome). Roda dentro de uma transação do chamador."""
    m = con.execute("select de, grupo, tentativas from escuta_msg where id=?", (id_,)).fetchone()
    n = (m["tentativas"] or 0) + 1
    if n >= MAX_TENTATIVAS:
        con.execute("update escuta_msg set estado='falhou', tentativas=?, proxima_em=null, processada_em=?"
                    + (", texto=null" if apagar_texto_se_desistir else "") + " where id=?", (n, agora, id_))
        numero = m["de"]
        _aviso(con, "escuta_falhou", {"numero": numero, "nome": None if m["grupo"] else _nome(con, numero, estado_remetente(con, numero)[1])}, agora)
        c["falhas"] += 1
        return
    espera = min(_ESPERA_MAX, _ESPERA_BASE * (2 ** n))
    d = dt.datetime.fromisoformat(agora)
    con.execute("update escuta_msg set tentativas=?, proxima_em=? where id=?", (n, (d + espera).isoformat(), id_))
    c["adiadas"] += 1


def _nome(con, numero: str, pessoa_id: str | None) -> str | None:
    if pessoa_id:
        r = con.execute("select nome from pessoa where id=?", (pessoa_id,)).fetchone()
        if r and r["nome"]:
            return r["nome"]
    r = con.execute("select nome from escuta_remetente where numero=?", (numero,)).fetchone()
    return r["nome"] if r else None


def _fechar(con, id_: int, agora: str, tipo=None, confianca=None, campos=None, apagar_texto=False, apagar_anexo=False) -> None:
    con.execute(
        "update escuta_msg set estado='processada', tipo=?, confianca=?, campos=?, processada_em=?"
        + (", texto=null" if apagar_texto else "") + (", anexo_caminho=null" if apagar_anexo else "") + " where id=?",
        (tipo, confianca, json.dumps(campos, ensure_ascii=False) if campos else None, agora, id_))


def _falhou(con, id_: int, agora: str, aviso: tuple[str, dict] | None = None, apagar_texto: bool = False) -> None:
    with transacao(con):
        con.execute("update escuta_msg set estado='falhou', processada_em=?" + (", texto=null" if apagar_texto else "") + " where id=?",
                    (agora, id_))
        if aviso:
            _aviso(con, aviso[0], aviso[1], agora)


_SEM = object()  # fase 1 não chamou o modelo


def _precisa_modelo(con, m, palavras) -> bool:
    """Fase 1 (sem transação): só aprovado (pessoa ou grupo aprovado), com texto e sem palavra de risco chega ao modelo."""
    if not (m["texto"] or "").strip() or tem_risco(m["texto"] or "", palavras):
        return False
    if m["grupo"]:
        g = con.execute("select aprovado from escuta_grupo where id_grupo=?", (m["id_grupo"],)).fetchone()
        return bool(g and g["aprovado"] == 1)
    return estado_remetente(con, m["de"])[0] == "aprovado"


def _uma(con, destinos, orcamento, agora, modo, m, palavras, c, apagar: list, spool, sinais: dict, r=_SEM) -> None:
    """Fase 2: roda dentro da transação da mensagem (begin immediate, relendo linha e remetente). `r` = classificação feita na fase 1. Contadores em c; arquivos a apagar vão em `apagar` (só após o commit).
    Palavra de risco vence tudo: mesmo de remetente aprovado, a classificação é pulada (um pedido na mesma mensagem não é processado)."""
    id_, texto, ativo, anexo = m["id"], m["texto"], modo == "ativo", m["anexo_caminho"]
    if m["grupo"]:
        g = con.execute("select aprovado from escuta_grupo where id_grupo=?", (m["id_grupo"],)).fetchone()
        if not (g and g["aprovado"] == 1):  # grupo fora da lista: não guarda nada
            _fechar(con, id_, agora, apagar_texto=True, apagar_anexo=True)
            apagar.append(anexo)
            return
        numero, estado, pid = m["de"], "aprovado", None
    else:
        numero = m["de"]
        estado, pid = estado_remetente(con, numero)
        if estado in ("ignorado", "bloqueado"):
            if estado == "ignorado" and tem_risco(texto or "", palavras):
                if ativo:
                    destinos.crise(con, numero, _nome(con, numero, None), agora)
                _fechar(con, id_, agora, tipo="crise", apagar_texto=True, apagar_anexo=True)
            else:
                _fechar(con, id_, agora, apagar_texto=True, apagar_anexo=True)
            apagar.append(anexo)
            return
    nome = _nome(con, numero, pid)
    aprovado = estado == "aprovado"
    if tem_risco(texto or "", palavras):  # independe do modelo e do remetente estar aprovado; crise nunca é apagada daqui
        if ativo:
            destinos.crise(con, numero, nome, agora)
        if not aprovado:
            avisar_novo(con, numero, agora)
        _fechar(con, id_, agora, tipo="crise")
        c["classificadas"] += 1
        return
    if not aprovado:
        avisar_novo(con, numero, agora)
        if m["estado"] == "nova":
            c["retidas"] += 1
        con.execute("update escuta_msg set estado='retida' where id=?", (id_,))
        return
    if not (texto or "").strip():
        _nada(con, destinos, m, agora, ativo, c, apagar, None, spool)
        return
    if r is _SEM:  # ficou aprovado durante a fase 1 sem modelo: espera a próxima rodada
        return
    if isinstance(r, Falha):
        if r.temporaria:  # exceção/timeout/resposta vazia: tenta de novo com espera (I6)
            _adiar(con, id_, agora, c)
        else:  # sem modelo, teto ou limite: fica nova, sem contar tentativa; o aviso diz o motivo
            _aviso_sem_modelo(con, agora, r.motivo)
        return
    tipo, campos = r.tipo, r.campos
    if tipo == "pedido" and not (pid and dados(con.execute("select dados from pessoa where id=?", (pid,)).fetchone()).get("pode_pedir") is True):
        _reter_pedido(con, m, numero, nome, r, agora, c)  # I3: nunca 'nada'; espera o dono liberar pode_pedir
        return
    if tipo == "nada":
        _nada(con, destinos, m, agora, ativo, c, apagar, r.confianca, spool)
        if r.invalida:  # spec §3.3: resposta inválida vira 'nada' + contagem de falha (I13)
            c["falhas"] += 1
        else:
            c["classificadas"] += 1
        return
    if tipo == "saude":  # o texto e os campos de saúde não ficam no banco da escuta
        sinais["saude"] = True  # se falhar daqui em diante, o texto de saúde é apagado (ADR-014)
        if ativo:
            _exigir_dentro(m, spool)
            destinos.saude(con, dict(m), campos)
        _fechar(con, id_, agora, tipo="saude", confianca=r.confianca, apagar_texto=True)
        c["classificadas"] += 1
        return
    if ativo:
        if tipo == "pedido":
            _exigir_dentro(m, spool)  # RuntimeError: vira falhou (não "pedido incompleto"), destino não é chamado
            try:
                destinos.pedido(con, pid, numero, dict(m), campos)
            except SemEscopo:  # I2: cadastro não casou (não é falha de serviço): retida, como o I3
                _reter_pedido(con, m, numero, nome, r, agora, c)
                return
            except ValueError as e:
                raise _PedidoIncompleto() from e
        elif tipo == "crise":
            destinos.crise(con, numero, nome, agora)
    _fechar(con, id_, agora, tipo=tipo, confianca=r.confianca, campos=campos)
    c["classificadas"] += 1


def _reter_pedido(con, m, numero: str, nome: str | None, r, agora: str, c) -> None:
    """Pedido de quem não pode pedir: fica `retida` com o texto (é pedido, não saúde) e a classificação guardada (a próxima rodada não
    paga o modelo de novo); aviso `escuta_sem_permissao` 1 vez por dia por remetente. Quando o dono marcar pode_pedir, a rodada processa."""
    con.execute("update escuta_msg set estado='retida', tipo='pedido', confianca=?, campos=? where id=?",
                (r.confianca, json.dumps(r.campos or {}, ensure_ascii=False), m["id"]))
    if m["estado"] == "nova":
        c["retidas"] += 1
    if not con.execute("select 1 from aviso where tipo='escuta_sem_permissao' and json_extract(payload,'$.numero')=? and substr(criado_em,1,10)=?",
                       (numero, agora[:10])).fetchone():
        _aviso(con, "escuta_sem_permissao", {"numero": numero, "nome": nome}, agora)


def _classificacao_guardada(m):
    """Pedido retido por falta de permissão (I3) já tem a classificação: não chama o modelo de novo."""
    if m["estado"] != "retida" or m["tipo"] != "pedido" or m["campos"] is None:
        return None
    try:
        campos = json.loads(m["campos"])
    except (TypeError, ValueError):
        return None
    return Classificacao("pedido", m["confianca"] or 0.0, campos) if isinstance(campos, dict) else None


def _exigir_dentro(m, spool) -> None:
    """Caminho de anexo vem do banco (não confiável): só vai a um destino se estiver dentro do spool. Senão a mensagem falha e nada é tocado."""
    if m["anexo_caminho"] and not spool_seguro.caminho_valido(spool, m["anexo_caminho"]):
        raise RuntimeError("anexo fora do spool")


def _nada(con, destinos, m, agora, ativo: bool, c, apagar: list, confianca, spool) -> None:
    """Aprovado sem texto ou 'nada'. Com anexo: no ativo entrega (documento) antes de apagar; no registro guarda o anexo."""
    if not m["anexo_caminho"]:
        _fechar(con, m["id"], agora, tipo="nada", confianca=confianca, apagar_texto=True)
        return
    if ativo:
        _exigir_dentro(m, spool)
        destinos.documento(con, dict(m))  # se levantar, nada foi apagado (transação desfeita)
        apagar.append(m["anexo_caminho"])
    c["documentos"] += 1
    _fechar(con, m["id"], agora, tipo="nada", confianca=confianca, apagar_texto=True, apagar_anexo=ativo)


def processar(con, destinos: Destinos, cliente: ModeloCliente | None, orcamento: Orcamento, agora: str,
              modo: str = "registro", spool: Path | None = None, *, tempo_max_s: float | None = None,
              monotonico=time.monotonic) -> dict:
    """`tempo_max_s`: orçamento de tempo da rodada (I1b). Estourado, a rodada para limpa (`tempo=1`) e as demais ficam como estão.
    As mensagens com palavra de risco são fechadas PRIMEIRO, sem modelo, antes de qualquer chamada ao modelo (backlog não atrasa crise)."""
    if modo not in ("registro", "ativo"):
        raise ValueError(f"modo inválido: {modo!r}")
    c = {"novas": 0, "classificadas": 0, "retidas": 0, "falhas": 0, "adiadas": 0, "documentos": 0, "ocupado": 0, "tempo": 0}
    erro_geral = False
    palavras = palavras_risco(con)
    inicio = monotonico()
    linhas = [(r["id"], r["estado"], tem_risco(r["texto"] or "", palavras)) for r in con.execute(
        "select id, estado, texto, proxima_em from escuta_msg where estado in ('nova','retida') order by recebida_em, id")
        if not _esperando(r["proxima_em"], agora)]  # em espera depois de falha temporária: só quando chegar proxima_em
    linhas.sort(key=lambda x: not x[2])  # estável: passada de risco (sem modelo) primeiro, depois a ordem de chegada
    for id_, estado_ini, risco in linhas:
        if not risco and tempo_max_s is not None and monotonico() - inicio > tempo_max_s:
            c["tempo"] = 1  # orçamento de tempo da rodada: o resto fica para o próximo disparo
            break
        if estado_ini == "nova":
            c["novas"] += 1
        apagar: list = []
        sinais: dict = {}
        try:
            m = con.execute("select * from escuta_msg where id=? and estado in ('nova','retida')", (id_,)).fetchone()
            if m is None:
                continue
            # Fase 1, SEM transação: o modelo (lento, pago, o custo é commitado em outra conexão) nunca roda com lock ou snapshot aberto.
            if not _precisa_modelo(con, m, palavras):
                r = _SEM
            else:
                r = _classificacao_guardada(m) or classificar(m["texto"], cliente, orcamento)
            # Fase 2: escrita imediata; relê a linha e o remetente (pode ter mudado enquanto o modelo rodava).
            # O lock de escrita fica preso durante as chamadas dos destinos (upload no Paperless): aceitável neste volume.
            try:
                con.execute("begin immediate")
            except sqlite3.OperationalError:
                # lock de escrita ocupado além do busy_timeout: a linha fica como está (sem falha, sem aviso) e a rodada para;
                # as demais esperariam 5 s cada. O próximo disparo do timer tenta de novo.
                c["ocupado"] = 1
                break
            with transacao(con, aberta=True):
                m = con.execute("select * from escuta_msg where id=? and estado in ('nova','retida')", (id_,)).fetchone()
                if m is None:
                    continue
                _uma(con, destinos, orcamento, agora, modo, m, palavras, c, apagar, spool, sinais, r)
        except _PedidoIncompleto as e:
            # pedido incompleto vem de Destinos.pedido; a mensagem fica falhou, sem texto no aviso
            log.warning("escuta: mensagem %s falhou (pedido incompleto)", id_)
            c["falhas"] += 1
            m = con.execute("select de from escuta_msg where id=?", (id_,)).fetchone()
            numero = m["de"]
            _falhou(con, id_, agora, ("escuta_pedido_incompleto", {"numero": numero, "nome": _nome(con, numero, estado_remetente(con, numero)[1])}))
            continue
        except TEMPORARIAS as e:
            # Paperless/ponte/rede fora: a transação foi desfeita (nada apagado, nada enviado ao banco); tenta de novo com espera.
            log.warning("escuta: mensagem %s adiada (%s)", id_, type(e).__name__)
            with transacao(con):
                _adiar(con, id_, agora, c, apagar_texto_se_desistir=bool(sinais.get("saude")))
            continue
        except Exception as e:
            log.warning("escuta: mensagem %s falhou (%s)", id_, type(e).__name__)
            c["falhas"] += 1
            erro_geral = True
            _falhou(con, id_, agora, apagar_texto=bool(sinais.get("saude")))
            continue
        if spool is not None:
            for a in apagar:
                if a:
                    spool_seguro.apagar_anexo(spool, a)  # só <spool>/anexos/<nome>, via descritor de diretório
    if erro_geral and not con.execute("select 1 from aviso where tipo='servico_falhou' and payload like ? and substr(criado_em,1,10)=?",
                                      ('%gabi-brain-escuta%', agora[:10])).fetchone():
        _aviso(con, "servico_falhou", {"unidade": "gabi-brain-escuta"}, agora)
    return c
