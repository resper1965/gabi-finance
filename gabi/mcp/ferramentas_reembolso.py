"""Ferramentas MCP do reembolso de saúde (D8): LEITURA da projeção do `gabi.db` e registro da intenção "pedi/recebi". Nada é enviado (R2).
ADR-014: o MCP não recebe a chave do cofre; paciente, prestador, valor e CPF nunca chegam aqui. Por isso as ferramentas falam em "dossiê N (mês)" e em ids de
documento do Paperless (os PDFs saem por `documentos_baixar`, para o próprio Ricardo). NÃO importa nada de gabi.familia nem de reembolso_saude.cofre
(`tests/test_saude_blindagem.py`). Consome: reembolso_saude.{texto,requisitos}; recebe `executar` do servidor."""
import datetime as dt
import json
import re

from gabi.hoje import BRT
from gabi.mcp.ferramentas_prop import ErroFerramenta
from gabi.reembolso_saude import requisitos, texto

ESCOPOS = {"reembolso_saude_pendentes": "fin", "reembolso_saude_segunda": "fin", "reembolso_saude_dossie": "docs",
           "reembolso_saude_pedi": "propostas", "reembolso_saude_recebi": "propostas"}
ESTADOS = ("a_pedir", "sem_nf", "sem_aprovacao", "a_conferir", "pedido", "recebido")
_PROTOCOLO = re.compile(r"[\w./ -]{1,40}")


def _hoje(agora: dt.datetime) -> dt.date:
    return agora.astimezone(BRT).date()


def _dossie(con, dossie_id):
    r = con.execute("select * from reembolso_saude_dossie where id=?", (dossie_id,)).fetchone() if isinstance(dossie_id, int) and not isinstance(dossie_id, bool) else None
    if r is None:
        raise ErroFerramenta("nao_encontrado", f"o dossiê {dossie_id} não existe")
    return r


def _item(r, req, hoje: dt.date) -> dict:
    parado = max((hoje - dt.date.fromisoformat(r["parado_desde"])).days, 0) if r["parado_desde"] else None
    return {"dossie": r["id"], "mes": r["mes"], "estado": r["estado"], "documentos": r["docs"], "pronto": bool(r["pronto"]),
            "faltam": [requisitos.rotulo(req, i) for i in json.loads(r["faltam"])], "parado_dias": parado}


def pendentes(con, agora: dt.datetime, estado: str | None = None) -> dict:
    """Dossiês de reembolso do plano de saúde, por número (nunca por nome): estado, o que falta e há quantos dias parado. `estado` filtra."""
    if estado is not None and estado not in ESTADOS:
        raise ValueError(f"estado deve ser um de {ESTADOS}")
    req = requisitos.carregar(con)
    linhas = con.execute("select * from reembolso_saude_dossie" + (" where estado=?" if estado else "") + " order by id", (estado,) if estado else ())
    return {"dossies": [_item(r, req, _hoje(agora)) for r in linhas]}


def dossie(con, agora: dt.datetime, dossie_id: int) -> dict:
    """Um dossiê: ids dos documentos do Paperless e o RASCUNHO do pedido (lista do que anexar). Não envia nada: baixe os PDFs com documentos_baixar e envie você."""
    r = _dossie(con, dossie_id)
    req = requisitos.carregar(con)
    item = _item(r, req, _hoje(agora))
    ids = json.loads(r["doc_ids"])
    situacao = "tudo o que o plano exige está nos documentos" if item["pronto"] else ("falta: " + ", ".join(item["faltam"]) if item["faltam"] else f"estado {r['estado']}")
    rascunho = (f"Rascunho do pedido de reembolso ({req['operadora']}), dossiê {r['id']} ({r['mes'][5:7]}/{r['mes'][:4]}).\n"
                f"Anexar os documentos {', '.join(map(str, ids))} do Paperless (baixe cada PDF com documentos_baixar). {situacao[0].upper() + situacao[1:]}.\n"
                "Quem envia à operadora é você; depois me diga \"pedi\" para eu registrar.")
    return {**{k: item[k] for k in ("dossie", "mes", "estado", "pronto", "faltam")}, "documentos": ids, "rascunho": rascunho}


def segunda(con, agora: dt.datetime) -> dict:
    """Lista "reembolsos de saúde a pedir e a conferir" pronta para o celular (a da segunda 08h), por número de dossiê, sem nomes."""
    linhas = texto.montar_segunda(con, _hoje(agora))
    return {"linhas": linhas, "texto": "\n".join(linhas)}


def _registrar(con, agora: dt.datetime, dossie_id: int, acao: str, protocolo: str | None) -> dict:
    r = _dossie(con, dossie_id)
    if protocolo is not None and not _PROTOCOLO.fullmatch(protocolo):
        raise ValueError("protocolo: até 40 letras, números, ponto, barra, hífen e espaço")
    if acao == "pedi" and r["estado"] != "a_pedir":
        raise ValueError(f"o dossiê {dossie_id} não está a pedir (estado {r['estado']})")
    if acao == "recebi" and r["estado"] not in ("pedido", "a_conferir"):
        raise ValueError(f"o dossiê {dossie_id} não tem pedido registrado (estado {r['estado']})")
    aberta = con.execute("select id from reembolso_saude_acao where dossie_id=? and acao=? and aplicado_em is null", (dossie_id, acao)).fetchone()
    if aberta:
        return {"registrado": True, "acao_id": aberta["id"], "ja_registrado": True, "aplica_na_proxima_rodada": True}
    aid = con.execute("insert into reembolso_saude_acao(dossie_id, acao, protocolo, criado_em) values (?,?,?,?)",
                      (dossie_id, acao, protocolo, agora.astimezone(dt.timezone.utc).isoformat())).lastrowid
    return {"registrado": True, "acao_id": aid, "aplica_na_proxima_rodada": True}


def registrar(srv, executar) -> None:
    @srv.tool()
    def reembolso_saude_pendentes(estado: str | None = None) -> dict:
        """Reembolsos do PLANO DE SAÚDE (não os de ness/IONIC) por número de dossiê: estado (a_pedir, sem_nf, sem_aprovacao, a_conferir, pedido, recebido), o que falta e há quantos dias está parado. Nunca traz nome de paciente ou prestador. Só leitura."""
        return executar("reembolso_saude_pendentes", lambda con, agora: pendentes(con, agora, estado))

    @srv.tool()
    def reembolso_saude_segunda() -> dict:
        """Lista "reembolsos de saúde a pedir e a conferir" pronta para o celular, entregar exatamente como vem. Sem nomes: quem é cada dossiê o Ricardo vê no painel. Só leitura."""
        return executar("reembolso_saude_segunda", lambda con, agora: segunda(con, agora))

    @srv.tool()
    def reembolso_saude_dossie(dossie_id: int) -> dict:
        """Documentos de um dossiê de reembolso de saúde (ids do Paperless) e o RASCUNHO do pedido. Não envia nada: os PDFs saem por documentos_baixar, para o Ricardo enviar."""
        return executar("reembolso_saude_dossie", lambda con, agora: dossie(con, agora, dossie_id))

    @srv.tool()
    def reembolso_saude_pedi(dossie_id: int, protocolo: str | None = None) -> dict:
        """REGISTRA que o Ricardo pediu o reembolso do dossiê (protocolo opcional). Só chame depois de ele dizer que pediu. Nada é enviado; o estado muda na próxima rodada."""
        return executar("reembolso_saude_pedi", lambda con, agora: _registrar(con, agora, dossie_id, "pedi", protocolo))

    @srv.tool()
    def reembolso_saude_recebi(dossie_id: int) -> dict:
        """REGISTRA que o Ricardo recebeu o reembolso do dossiê (quando o crédito não foi casado sozinho). Só chame depois de ele dizer. O estado muda na próxima rodada."""
        return executar("reembolso_saude_recebi", lambda con, agora: _registrar(con, agora, dossie_id, "recebi", None))
