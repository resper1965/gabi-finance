"""Avisos para o Ricardo (/api/v1/avisos): o que o produtor (gabi/avisos.py) gravou e ainda não foi lido. Só o boss.
Título e texto saem do servidor em pt-BR, para o painel e o canal (Hermes) mostrarem a mesma coisa. Consome: aviso, decisao."""
import datetime as dt
import json

from fastapi import APIRouter, Depends, Request

from gabi.envelope import envelope
from gabi.identidade import Identidade, exigir
from gabi.rotas.dinheiro import _agora, _con, erro

router = APIRouter(prefix="/api/v1/avisos", dependencies=[Depends(exigir("boss"))])


def _brl(v) -> str:
    return f"R$ {v}" if v is not None else "valor a confirmar"


def descrever(tipo: str, p: dict) -> tuple[str, str]:
    if tipo == "rodada_parada":
        return "Dados do banco parados", p.get("motivo", "")
    if tipo == "conta_atrasada":
        return f"Conta atrasada: {p.get('nome', '?')}", f"venceu em {p.get('vencimento', '?')}, {_brl(p.get('valor'))}"
    if tipo == "cobrada_apos_cancelar":
        return f"Cobrada depois de cancelar: {p.get('nome', '?')}", f"último débito em {p.get('ultimo_debito', '?')}, {_brl(p.get('valor'))}"
    if tipo == "vence_hoje":
        itens = p.get("itens") or []
        return "Vence hoje", "; ".join(f"{i['nome']} {_brl(i.get('valor'))}" for i in itens) or "nada"
    if tipo == "servico_falhou":
        return "Serviço falhou", f"{p.get('unidade', '?')} terminou com erro"
    if tipo == "exportacao_parada":
        return "Backup fora da VPS parado", p.get("motivo", "")
    if tipo == "caixa_reconectar" and p.get("provedor") == "linear":
        return "Reconectar a Linear", "a chave foi recusada ou não está configurada; as entregas não estão sendo lidas"
    if tipo == "caixa_reconectar":
        return f"Reconectar a caixa {p.get('endereco', '?')}", "a credencial foi recusada ou não está configurada; a caixa não está sendo lida"
    return tipo, json.dumps(p, ensure_ascii=False)


@router.get("")
def listar(request: Request):
    """Avisos abertos (não lidos) do gabi.brain, os mais novos primeiro, com título e texto em pt-BR."""
    con = _con(request)
    try:
        itens = []
        for r in con.execute("select id, tipo, payload, criado_em from aviso where entregue_em is null order by criado_em desc, id desc limit 50"):
            p = json.loads(r["payload"])
            titulo, texto = descrever(r["tipo"], p)
            itens.append({"id": r["id"], "tipo": r["tipo"], "titulo": titulo, "texto": texto, "criado_em": r["criado_em"]})
        return envelope(con, {"itens": itens}, agora=_agora(request))
    finally:
        con.close()


@router.post("/{aviso_id}/lido")
async def lido(aviso_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Marca um aviso como lido (idempotente) e registra quem leu."""
    con = _con(request)
    try:
        a = con.execute("select id, entregue_em from aviso where id=?", (aviso_id,)).fetchone()
        if a is None:
            raise erro(404, "nao_encontrado", f"aviso {aviso_id} não existe")
        if a["entregue_em"] is None:
            agora = dt.datetime.now(dt.timezone.utc).isoformat()
            con.execute("begin")
            con.execute("update aviso set entregue_em=? where id=?", (agora, aviso_id))
            con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'api')", (agora, ident.login, f"aviso {aviso_id} lido"))
            con.execute("commit")
        return envelope(con, {"id": aviso_id, "lido": True}, agora=_agora(request))
    finally:
        con.close()
