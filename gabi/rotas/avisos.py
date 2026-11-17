"""Avisos para o Ricardo (/api/v1/avisos): o que o produtor (gabi/avisos.py) gravou e ainda não foi lido. Só o boss.
Título e texto saem do servidor em pt-BR, para o painel e o canal mostrarem a mesma coisa. Consome: aviso, decisao."""
import datetime as dt
import json
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request

from gabi.envelope import envelope
from gabi.identidade import Identidade, exigir
from gabi.rotas.dinheiro import _agora, _con, erro

router = APIRouter(prefix="/api/v1/avisos", dependencies=[Depends(exigir("boss"))])


def _brl(v) -> str:
    return f"R$ {v}" if v is not None else "valor a confirmar"


def _reais(v) -> str:
    """"3522.64" -> "R$ 3.522,64" (os avisos novos; os antigos seguem com o formato decimal)."""
    try:
        return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "sem valor"


def _ddmm(iso) -> str:
    return f"{str(iso)[8:10]}/{str(iso)[5:7]}" if isinstance(iso, str) and len(iso) >= 10 else "?"


def descrever(tipo: str, p: dict) -> tuple[str, str]:
    if tipo == "vence_em_breve":
        itens = p.get("itens") or []
        linhas = []
        for i in itens:
            valor = _reais(i.get("valor")) if i.get("valor") is not None else "sem valor"
            marca = f"≈{valor} (estimado)" if i.get("estimado") and i.get("valor") is not None else valor
            linhas.append(f"{_ddmm(i.get('vencimento'))} {i.get('nome', '?')} {marca}" + (" · débito automático" if i.get("debito_automatico") else ""))
        legenda = " ≈ = estimado pelo último valor; corrijo quando o real chegar." if any(i.get("estimado") for i in itens) else ""
        return f"Vence em breve: {len(itens)} conta(s)", "; ".join(linhas) + "." + legenda
    if tipo == "valor_diferente":
        return f"Valor diferente: {p.get('nome', '?')}", f"estimado {_reais(p.get('estimado'))}, veio {_reais(p.get('real'))} (vence {_ddmm(p.get('vencimento'))})"
    if tipo == "rodada_parada":
        return "Dados do banco parados", p.get("motivo", "")
    if tipo == "saldo_divergente":
        d = p.get("diferenca_centavos")
        quanto = _reais(abs(d) / 100) if isinstance(d, int) else "um valor"
        return f"Saldo não bate com os lançamentos: {p.get('conta', '?')}", f"diferença de {quanto} entre o saldo do banco e os lançamentos lidos; só para você conferir (os dados seguem valendo)"
    if tipo == "banco_desatualizado":
        try:
            d = dt.datetime.fromisoformat(str(p["desde"]).replace("Z", "+00:00"))
            desde = d.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m %H:%M")
        except (KeyError, TypeError, ValueError):
            desde = "data desconhecida"
        return f"{p.get('banco', 'Banco')} sem atualizar há mais de 24 h", f"o saldo e os lançamentos vêm da última atualização do banco, em {desde}; confira antes de decidir por eles"
    if tipo == "conta_atrasada":
        return f"Conta atrasada: {p.get('nome', '?')}", f"venceu em {p.get('vencimento', '?')}, {_brl(p.get('valor'))}"
    if tipo == "cobrada_apos_cancelar":
        return f"Cobrada depois de cancelar: {p.get('nome', '?')}", f"último débito em {p.get('ultimo_debito', '?')}, {_brl(p.get('valor'))}"
    if tipo == "vence_hoje":
        itens = p.get("itens") or []
        return "Vence hoje", "; ".join(f"{i['nome']} {_brl(i.get('valor'))}" for i in itens) or "nada"
    if tipo == "servico_falhou":
        return "Serviço falhou", f"{p.get('unidade', '?')} terminou com erro"
    if tipo == "lancamento_sem_conversao":
        n = p.get("quantidade", 0)
        return ("Compra em moeda estrangeira sem valor em reais",
                f"{n} lançamento(s) em moeda estrangeira entraram pelo valor original, sem conversão; o valor em reais não veio do banco")
    if tipo == "exportacao_parada":
        return "Backup fora da VPS parado", p.get("motivo", "")
    return tipo, json.dumps(p, ensure_ascii=False)


@router.get("")
def listar(request: Request):
    """Avisos abertos (não lidos) do gabi-finance, os mais novos primeiro, com título e texto em pt-BR."""
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
            con.execute("begin immediate")
            con.execute("update aviso set entregue_em=? where id=?", (agora, aviso_id))
            con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'api')", (agora, ident.login, f"aviso {aviso_id} lido"))
            con.execute("commit")
        return envelope(con, {"id": aviso_id, "lido": True}, agora=_agora(request))
    finally:
        con.close()
