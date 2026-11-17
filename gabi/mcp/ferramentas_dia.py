"""Ferramentas MCP do dia: o resumo da manhã financeiro (escopo `trabalho`) e o `olhar_a_frente` financeiro (escopo `fin`). SÓ LEITURA; nenhuma ferramenta envia, apaga ou confirma (R1/R2/R14).
Consome: dinheiro.agenda_financeira, dinheiro.olhar_a_frente, decisoes, envelope; recebe `executar` do servidor. Agenda e e-mail saíram no corte do gabi-finance."""
import datetime as dt
import logging

from gabi import decisoes
from gabi.dinheiro import agenda_financeira, olhar_a_frente as frente
from gabi.envelope import envelope

log = logging.getLogger(__name__)

ESCOPOS = {"resumo_manha": "trabalho", "olhar_a_frente": "fin"}


def _quando(iso: str | None) -> str:
    """ISO UTC -> 'dd/mm HH:MM' em Brasília; sem data: 'nunca'."""
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return "nunca"
    return (t.astimezone(dt.timezone(dt.timedelta(hours=-3)))).strftime("%d/%m %H:%M")


def _inteiro(v, minimo: int, maximo: int, nome: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not minimo <= v <= maximo:
        raise ValueError(f"{nome} deve ser um inteiro de {minimo} a {maximo}")
    return v


def resumo_da_manha(con, agora: dt.datetime) -> dict:
    """Mensagem das 07:05: Financeiro (agenda financeira de 3 dias), o bloco "Olhando à frente" (só quando há alerta) e a contagem de decisões abertas.
    Se os dados estiverem desatualizados, a primeira linha avisa. `linhas` guarda cada linha; `texto` junta com \n."""
    env = envelope(con, {}, agora=agora)
    linhas = []
    if env["desatualizado"]:
        linhas += [f"⚠️ *Dados desatualizados* (conferidos até {_quando(env['dados_ate'])}). Confira antes de agir."]
        if env.get("bancos_antigos"):
            linhas += ["Sem atualizar há mais de 24 h: " + "; ".join(f"{b['banco']} (desde {_quando(b['desde'])})" for b in env["bancos_antigos"]) + "."]
        linhas += [""]
    linhas += agenda_financeira.montar(con, agora, dias=3)
    try:
        a_frente = frente.bloco_resumo(con, agora)
    except Exception:  # o olhar à frente nunca derruba o resumo da manhã (ADR-037)
        log.exception("resumo da manhã: olhar à frente falhou")
        a_frente = []
    if a_frente:
        linhas += [""] + a_frente
    n = len(decisoes.abertas(con))
    if n:  # só a contagem: as perguntas saem quando ele pedir ("o que está pendente?")
        linhas += ["", f"🗳 {n} decisão(ões) esperando você. Quer ver?" if n > 1 else "🗳 1 decisão esperando você. Quer ver?"]
    return {"linhas": linhas, "texto": "\n".join(linhas)}


def registrar(srv, executar) -> None:
    @srv.tool()
    def resumo_manha() -> dict:
        """Resumo da manhã financeiro já formatado para o celular (começa por 'dados desatualizados' se for o caso). Entregar exatamente como vem."""
        return executar("resumo_manha", resumo_da_manha)

    @srv.tool()
    def olhar_a_frente(dias: int = 30) -> dict:
        """O que vai virar problema (só dados locais): `caixa` (primeiro dia em que o saldo projetado fica negativo, saldo mínimo e o dia dele; `null` se nunca fica) e `a_receber_atrasado` (atrasado há 10 dias ou mais). `ha_alerta` diz se vale avisar o Ricardo sem ele perguntar. A previsão só conta entradas de NFS-e previstas. Só leitura."""
        return executar("olhar_a_frente", lambda con, agora: frente.olhar_a_frente(con, agora, _inteiro(dias, 7, 90, "dias")))
