"""Avisos para o Ricardo (/api/v1/avisos): o que o produtor (gabi/avisos.py) gravou e ainda não foi lido. Só o boss.
Título e texto saem do servidor em pt-BR, para o painel e o canal (Hermes) mostrarem a mesma coisa. Consome: aviso, decisao."""
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


def _hhmm(iso) -> str | None:
    return str(iso)[11:16] if isinstance(iso, str) and len(iso) >= 16 else None


def _curto(texto: str, limite: int = 120) -> str:
    """Linha do resumo cabe no limite do Telegram (4096 caracteres por mensagem): 15 linhas de até 500 caracteres estourariam."""
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


def _descrever_atividade(tipo: str, p: dict) -> tuple[str, str]:
    """O texto da atividade é do Ricardo (vai só para os canais dele); nunca para log."""
    if tipo == "atividade_hora":
        return f"Atividade agora: {p.get('texto', '?')}", f"marcada para {_hhmm(p.get('vence_em')) or 'agora'}"
    if tipo == "atividade_hoje":
        hora = _hhmm(p.get("vence_em"))
        return f"Atividade para hoje: {p.get('texto', '?')}", f"vence hoje às {hora}" if hora else "vence hoje"
    c = p.get("contagens") or {k: len(p.get(k) or []) for k in ("vencidas", "hoje", "sem_data")}
    partes = [f"{c['vencidas']} {'vencida' if c['vencidas'] == 1 else 'vencidas'}" if c.get("vencidas") else "", f"{c['hoje']} para hoje" if c.get("hoje") else "",
              f"{c['sem_data']} sem data" if c.get("sem_data") else ""]
    linhas = [f"{rot}: {_curto(i.get('texto', '?'))}" + (f" ({_ddmm(i['vence_em'])})" if i.get("vence_em") else "")
              for rot, chave in (("vencida", "vencidas"), ("hoje", "hoje"), ("sem data", "sem_data")) for i in p.get(chave) or []]
    mostradas = len(linhas)
    mais = f"; e mais {p['total'] - mostradas}" if isinstance(p.get("total"), int) and p["total"] > mostradas else ""
    return "Atividades: " + ", ".join(x for x in partes if x), "; ".join(linhas) + mais


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
    if tipo == "documento_vence":
        dias = p.get("dias")
        quando = f"venceu em {_ddmm(p.get('data'))} (há {-dias} dias)" if isinstance(dias, int) and dias < 0 else f"em {_ddmm(p.get('data'))} ({dias} dias)"
        return f"Documento vence: {p.get('tipo', '?')} de {p.get('titular_nome', '?')}", quando
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
    if tipo == "teams_sem_resposta":
        quem = p.get("de_nome") or "Alguém"
        verbo = "te mencionou" if p.get("tipo_chat") == "grupo" else "te chamou"
        try:
            d = dt.datetime.fromisoformat(p["desde"])
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
            desde = f" desde {d.astimezone(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m %H:%M')}"
        except (KeyError, TypeError, ValueError):
            desde = ""
        return f"Teams: {quem} {verbo}", f"sem resposta{desde} ({p.get('conta', '?')})"
    if tipo == "hermes_parado":
        return "O Hermes (Telegram e WhatsApp) está parado", f"a unidade {p.get('unidade') or 'hermes-gateway'} está {p.get('estado') or 'fora do ar'}; reinicie com: sudo systemctl restart hermes-gateway"
    if tipo == "google_parado":
        return ("Google parado: correio, agenda e contatos sem ler",
                f"todas as fontes Google falham ({', '.join(p.get('contas') or [])}); provável token expirado: refaça com sudo /opt/gabi-brain/venv/bin/python -m tools.obter_token_google <conta> --env /etc/gabi/google.env --gravar")
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
    if tipo.startswith("atividade_"):
        return _descrever_atividade(tipo, p)
    if tipo == "projeto_parado":
        n = p.get("parado_ha_dias") or 0
        return f"Projeto parado: {p.get('nome', '?')}", f"sem movimento há {n} {'dia' if n == 1 else 'dias'}"
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
            con.execute("begin immediate")
            con.execute("update aviso set entregue_em=? where id=?", (agora, aviso_id))
            con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'api')", (agora, ident.login, f"aviso {aviso_id} lido"))
            con.execute("commit")
        return envelope(con, {"id": aviso_id, "lido": True}, agora=_agora(request))
    finally:
        con.close()
