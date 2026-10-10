"""Assistente de configuração (T4.5): 7 passos, cada um salva o progresso e pode ficar para depois. Toda conexão é TESTADA na hora.
R5: o app nunca grava nem devolve segredo; a credencial vai ao arquivo de ambiente, por onde o Ricardo escolher, e aqui só se diz ONDE. Só o boss.
Consome: fontes (Paperless/Nibo pela ponte), rodada, caixa_email, aviso, setup_passo."""
import datetime as dt
import os
import re

from fastapi import APIRouter, Depends, Request

from gabi.envelope import envelope
from gabi.identidade import exigir
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, erro

router = APIRouter(prefix="/api/v1/setup", dependencies=[Depends(exigir("boss"))])
HORAS_RODADA = 72

PASSOS = [
    ("microsoft", "Microsoft 365", "Lê e-mail, agenda e tarefas da IONIC (e da ness depois da migração). O administrador do tenant precisa aprovar o app (link em docs/fontes/graph.md). "
                                   "Só leitura e rascunho: nada é enviado nem apagado. Credenciais em /etc/gabi/trabalho.env (GRAPH_*)."),
    ("bancos", "Bancos", "Saldos e extratos pelo Open Finance (mcp.ai), só leitura. A chave fica em /etc/gabi/brain.env (MCPAI_KEY); reconectar C6 e XP no mcp.ai quando pedir."),
    ("paperless", "Paperless", "Onde ficam notas, boletos e comprovantes. O app lê e só acrescenta etiquetas gabi:*; nunca apaga. Token em /etc/gabi/cobrar.env."),
    ("nibo", "Nibo", "Contabilidade da PJ. Lê notas e agendamentos; a única escrita é o lote 'Lançar na PJ', com a sua confirmação. Token em /etc/gabi/cobrar.env (NIBO_TOKEN)."),
    ("extras", "Extras", "Saúde da família (chave em /etc/gabi/saude.key) e entregas da Linear (LINEAR_API_KEY em /etc/gabi/trabalho.env). Opcionais."),
    ("canal", "Canal (Hermes)", "Telegram e WhatsApp. Só entra depois que o gabi.brain terminar: deixe para depois."),
    ("pronto", "Pronto", "Confere se todos os passos acima estão feitos ou combinados para depois."),
]
TITULOS = {p: (t, e) for p, t, e in PASSOS}


def _limpar(texto: str) -> str:
    """Defesa extra: nenhum valor de variável de segredo do ambiente sai numa resposta."""
    for nome, valor in os.environ.items():
        if valor and len(valor) >= 6 and re.search(r"TOKEN|KEY|SECRET|PASS|SENHA", nome, re.I):
            texto = texto.replace(valor, "***")
    return texto


def _fonte(request: Request, nome: str):
    fabrica = request.app.state.fontes.get(nome)
    return fabrica() if fabrica else None


def _testar_paperless(request, con, agora):
    p = _fonte(request, "paperless")
    if p is None:
        return False, "O Paperless não está configurado: coloque PAPERLESS_URL e PAPERLESS_TOKEN em /etc/gabi/cobrar.env e reinicie o gabi-brain-fontes."
    p.docs(limite=1)
    return True, "Conectado: o Paperless respondeu."


def _testar_nibo(request, con, agora):
    n = _fonte(request, "nibo")
    if n is None:
        return False, "O Nibo não está configurado: coloque NIBO_TOKEN em /etc/gabi/cobrar.env e reinicie o gabi-brain-fontes."
    n.organizations()
    return True, "Conectado: o Nibo respondeu."


def _testar_bancos(request, con, agora):
    fim = con.execute("select max(fim) from rodada where fonte='open-finance' and conferida=1").fetchone()[0]
    if not fim:
        return False, "Nenhuma rodada conferida ainda: confira MCPAI_KEY em /etc/gabi/brain.env e reconecte as contas no mcp.ai."
    idade = agora.astimezone(dt.timezone.utc) - dt.datetime.fromisoformat(fim.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    if idade > dt.timedelta(hours=HORAS_RODADA):
        return False, f"A última rodada conferida foi em {fim[:10]}: reconecte as contas no mcp.ai."
    return True, f"Última rodada conferida em {fim[:10]}."


def _testar_microsoft(request, con, agora):
    if not con.execute("select 1 from caixa_email where provedor='graph' and estado='sim'").fetchone():
        return False, "Nenhuma caixa Microsoft liberada: cadastre e libere em Cadastros › Caixas de e-mail e ponha as credenciais GRAPH_* em /etc/gabi/trabalho.env."
    if con.execute("select 1 from aviso where tipo='caixa_reconectar' and entregue_em is null and json_extract(payload,'$.provedor')='graph'").fetchone():
        return False, "Uma caixa Microsoft pede reconexão (veja o sino)."
    ult = con.execute("select max(fim) from rodada where fonte='trabalho' and status='ok'").fetchone()[0]
    return (True, f"Caixa lida; última rodada em {ult[:16].replace('T', ' ')} UTC.") if ult else (False, "As caixas estão liberadas mas o job do Trabalho ainda não rodou.")


def _testar_extras(request, con, agora):
    saude = getattr(request.app.state, "saude", None) is not None
    linear = con.execute("select count(*) from entrega").fetchone()[0]
    partes = [f"saúde: {'chave configurada' if saude else 'sem chave (/etc/gabi/saude.key)'}", f"Linear: {linear} entrega(s) lida(s)" if linear else "Linear: nenhuma entrega lida (opcional)"]
    return saude, "; ".join(partes)


def _testar_canal(request, con, agora):
    return False, "O canal (Hermes) só é instalado depois que o gabi.brain terminar: deixe para depois."


def _testar_pronto(request, con, agora):
    estados = {r["passo"]: r["estado"] for r in con.execute("select passo, estado from setup_passo")}
    faltam = [TITULOS[p][0] for p, _, _ in PASSOS if p != "pronto" and p not in estados]
    return (False, "Faltam: " + ", ".join(faltam) + ".") if faltam else (True, "Tudo feito ou combinado para depois.")


TESTES = {"microsoft": _testar_microsoft, "bancos": _testar_bancos, "paperless": _testar_paperless, "nibo": _testar_nibo,
          "extras": _testar_extras, "canal": _testar_canal, "pronto": _testar_pronto}


def _passo(con, passo: str) -> dict:
    r = con.execute("select estado, detalhe from setup_passo where passo=?", (passo,)).fetchone()
    return {"passo": passo, "titulo": TITULOS[passo][0], "explicacao": TITULOS[passo][1], "estado": r["estado"] if r else "pendente", "detalhe": r["detalhe"] if r else None}


@router.get("")
def passos(request: Request):
    """Os 7 passos do assistente de configuração, com o estado salvo de cada um (pendente, feito ou depois)."""
    con = _con(request)
    try:
        return envelope(con, {"passos": [_passo(con, p) for p, _, _ in PASSOS]}, agora=_agora(request))
    finally:
        con.close()


@router.get("/{passo}")
def um_passo(passo: str, request: Request):
    """Um passo do assistente: explicação em português (o que o app lê, o que nunca faz e onde vai a credencial) e o estado salvo."""
    if passo not in TITULOS:
        raise erro(404, "nao_encontrado", "passo desconhecido")
    con = _con(request)
    try:
        return envelope(con, _passo(con, passo), agora=_agora(request))
    finally:
        con.close()


@router.post("/{passo}")
async def agir(passo: str, request: Request):
    """Testa a conexão do passo na hora (acao=testar; feito só se der certo) ou deixa para depois (acao=depois). Devolve {ok, detalhe, estado}."""
    if passo not in TITULOS:
        raise erro(404, "nao_encontrado", "passo desconhecido")
    acao = _corpo(await _json(request)).get("acao")
    if acao not in ("testar", "depois"):
        raise erro(400, "requisicao_invalida", "acao deve ser testar ou depois")
    con = _con(request)
    try:
        agora = _agora(request)
        if acao == "depois":
            ok, detalhe, estado = True, "Combinado: fica para depois.", "depois"
        else:
            try:
                ok, detalhe = TESTES[passo](request, con, agora)
            except Exception as e:  # ErroPaperless/ErroNibo/ConnectionError: só o que o cliente já filtrou (sem cabeçalho nem token)
                ok, detalhe = False, f"A conexão falhou: {type(e).__name__}: {e}"
            estado = "feito" if ok else "pendente"
        detalhe = _limpar(detalhe)
        if estado == "pendente":
            con.execute("delete from setup_passo where passo=? and estado='feito'", (passo,))  # deixou de funcionar: volta a pendente
        else:
            con.execute("insert into setup_passo(passo, estado, detalhe, atualizado_em) values (?,?,?,?) on conflict(passo) do update set "
                        "estado=excluded.estado, detalhe=excluded.detalhe, atualizado_em=excluded.atualizado_em", (passo, estado, detalhe, agora.astimezone(dt.timezone.utc).isoformat()))
        return envelope(con, {"passo": passo, "ok": ok, "detalhe": detalhe, "estado": estado}, agora=agora)
    finally:
        con.close()
