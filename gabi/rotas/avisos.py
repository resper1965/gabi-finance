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


def _reais(v) -> str:
    """"3522.64" -> "R$ 3.522,64" (os avisos novos; os antigos seguem com o formato decimal)."""
    try:
        return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "sem valor"


def _ddmm(iso) -> str:
    return f"{str(iso)[8:10]}/{str(iso)[5:7]}" if isinstance(iso, str) and len(iso) >= 10 else "?"


def _quem(p: dict) -> str:
    return p.get("nome") or p.get("numero") or "número desconhecido"


def _descrever_escuta(tipo: str, p: dict) -> tuple[str, str]:
    """Só número e nome: o texto da mensagem nunca vem para o aviso."""
    if tipo == "escuta_novo_remetente":
        return f"Novo remetente no WhatsApp: {_quem(p)}", "aprove, ignore ou bloqueie na fila da escuta"
    if tipo == "escuta_atencao":
        return f"Possível crise: {_quem(p)}. Abra a conversa.", ""
    if tipo == "escuta_saude":
        return f"Mensagem de saúde de {_quem(p)}: abra a conversa", ""
    if tipo == "escuta_pedido_incompleto":
        return f"Pedido incompleto de {_quem(p)}", "faltou valor ou vencimento; abra a conversa e peça o que falta"
    if tipo == "escuta_sem_permissao":
        return f"Pedido de {_quem(p)} sem permissão: libere em Cadastros", "a mensagem fica retida até a pessoa poder pedir (pode_pedir)"
    if tipo == "escuta_parada":
        return "Escuta do WhatsApp parada", p.get("motivo", "")
    if tipo == "escuta_sem_modelo":
        return "Escuta sem modelo de leitura", f"a escuta está sem modelo disponível agora: {p.get('motivo') or 'motivo desconhecido'}"
    if tipo == "escuta_anexo_grande":
        return f"Anexo grande demais de {_quem(p)}", "acima do teto da escuta (escuta.anexo_max_mb): não foi guardado; abra a conversa"
    if tipo == "escuta_falhou":
        return f"Mensagem de {_quem(p)} não foi processada", "falhou 8 vezes seguidas (Paperless, ponte ou modelo fora do ar); abra a conversa"
    return tipo, ""


def _descrever_email(tipo: str, p: dict) -> tuple[str, str]:
    """Remetente e assunto são dado do dono (vão só para os canais dele); nunca para log."""
    if tipo == "email_emergencial":
        return f"E-mail emergencial de {p.get('remetente') or '?'}: {p.get('assunto') or '(sem assunto)'}", p.get("motivo", "")
    if tipo == "email_lixeira_resumo":
        itens = p.get("itens") or []
        lista = "; ".join(f"{i.get('remetente') or '?'} — {i.get('assunto') or '(sem assunto)'}" for i in itens if isinstance(i, dict))
        total = p.get("total", len(itens))
        mais = f" (e mais {total - len(itens)})" if isinstance(total, int) and total > len(itens) else ""
        return f"{total} e-mail(s) foram para a lixeira hoje", f"{lista}{mais}. Se faltou algo, restaure no painel (Mensagens › Prioridades): a lixeira esvazia sozinha em 30 dias."
    if tipo == "email_sem_modelo":
        return "Correio sem modelo de leitura", f"o e-mail está sem modelo disponível agora (nada vai para a lixeira): {p.get('motivo') or 'motivo desconhecido'}"
    if tipo == "email_falhou":
        return f"{p.get('total', '?')} e-mail(s) não puderam ser lidos pela Gabi", "esgotaram as tentativas (modelo ou serviço fora do ar); não foram para a lixeira e não geram alerta"
    if tipo == "email_reconectar":
        return f"Reconectar o e-mail {p.get('conta', '?')}", "a credencial foi recusada ou não está configurada; o e-mail não está sendo lido"
    return tipo, json.dumps(p, ensure_ascii=False)


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
    if tipo == "caixa_reconectar" and p.get("provedor") == "linear":
        return "Reconectar a Linear", "a chave foi recusada ou não está configurada; as entregas não estão sendo lidas"
    if tipo == "caixa_reconectar":
        return f"Reconectar a caixa {p.get('endereco', '?')}", "a credencial foi recusada ou não está configurada; a caixa não está sendo lida"
    if tipo == "agenda_reconectar":
        return f"Reconectar a agenda {p.get('conta', '?')}", "a credencial foi recusada ou não está configurada; a agenda não está sendo lida"
    if tipo.startswith("email_"):
        return _descrever_email(tipo, p)
    if tipo.startswith("escuta_"):
        return _descrever_escuta(tipo, p)
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
