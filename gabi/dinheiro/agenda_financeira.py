"""Agenda financeira em mensagem: o que vence, o que está atrasado e a previsão do saldo (diária curta e semanal de 30 dias).
Só lê; sem rede nem modelo. A previsão é a do painel (`projecao.projetar`): saídas dos compromissos e entradas só das NFS-e previstas.
Consome: contas_pagar (contas_a_pagar, caixa_unico), projecao, avisos (CONFIRMADO via conciliacao)."""
import datetime as dt
from zoneinfo import ZoneInfo

from gabi.dinheiro import contas_pagar
from gabi.dinheiro.conciliacao import CONFIRMADO
from gabi.dinheiro.projecao import projetar

BRT = ZoneInfo("America/Sao_Paulo")
LIMITE_ITENS = 12
LEITURA_VELHA_HORAS = 6
AVISO_ENTRADAS = "Entradas: só as notas (NFS-e) previstas contam; o resto não entra na previsão."


def _brl(centavos: int) -> str:
    sinal, c = ("-" if centavos < 0 else ""), abs(centavos)
    return f"{sinal}R$ {c // 100:,}".replace(",", ".") + f",{c % 100:02d}"


def _dm(d: dt.date) -> str:
    return d.strftime("%d/%m")


def _valor(i: dict) -> str:
    if i["valor_centavos"] is None:
        return "valor a confirmar"
    estimado = i["valor_fonte"] not in CONFIRMADO
    return ("~" if estimado else "") + _brl(i["valor_centavos"])


def _marca(i: dict) -> str:
    return " (déb. auto)" if i["estado"] == "debito_automatico" else ""


def _linha_saldo(caixa, agora: dt.datetime) -> str:
    if not caixa.contas:
        return "Saldo: sem leitura"
    mais_antiga = min(c["em"] for c in caixa.contas)
    limite = (agora.astimezone(BRT).replace(tzinfo=None) - dt.timedelta(hours=LEITURA_VELHA_HORAS)).isoformat(timespec="seconds")
    aviso = f" ⚠️ leitura de {dt.datetime.fromisoformat(mais_antiga):%d/%m %H:%M}" if mais_antiga < limite else ""
    return f"Saldo: {_brl(caixa.saldo_centavos)}{aviso}"


def _itens(con, hoje: dt.date, fim: dt.date) -> tuple[list[dict], list[dict], list[dict]]:
    """(atrasadas, de hoje, dos próximos dias até `fim`), cada item com a data real do vencimento útil."""
    g = contas_pagar.contas_a_pagar(con, hoje)
    todos = [i for grupo in ("hoje", "proximas", "adiante", "debito_automatico") for i in g[grupo]]
    do_dia, adiante = [], []
    for i in sorted(todos, key=lambda x: (x["vencimento_util"], x["nome"])):
        d = dt.date.fromisoformat(i["vencimento_util"])
        if d == hoje:
            do_dia.append(i)
        elif hoje < d <= fim:
            adiante.append(i)
    return g["atrasadas"], do_dia, adiante


def _previsao_diaria(proj: list[dict]) -> str:
    for d in proj:
        if d["saldo_centavos"] < 0:
            return f"⚠️ Falta {_brl(-d['saldo_centavos'])} em {_dm(dt.date.fromisoformat(d['dia']))}"
    ultimo = proj[-1]
    return f"Previsão: {_brl(ultimo['saldo_centavos'])} em {_dm(dt.date.fromisoformat(ultimo['dia']))}"


def _diaria(con, hoje: dt.date, agora: dt.datetime, dias: int) -> list[str]:
    caixa = contas_pagar.caixa_unico(con, hoje)
    atrasadas, do_dia, adiante = _itens(con, hoje, hoje + dt.timedelta(days=dias))
    soma_atraso = sum(i["valor_centavos"] or 0 for i in atrasadas)
    linhas = ["💰 *Financeiro*", _linha_saldo(caixa, agora),
              f"• ⚠️ Atrasadas: {len(atrasadas)} ({_brl(soma_atraso)})" if atrasadas else "• Atrasadas: 0",
              "• Hoje: " + "; ".join(f"{i['nome']} {_valor(i)}{_marca(i)}" for i in do_dia) if do_dia else "• Hoje: nada"]
    if adiante:
        linhas.append(f"Próximos {dias} dias")
        linhas += [f"• {_dm(dt.date.fromisoformat(i['vencimento_util']))} {i['nome']} {_valor(i)}{_marca(i)}" for i in adiante[:LIMITE_ITENS]]
        if len(adiante) > LIMITE_ITENS:
            linhas.append(f"• +{len(adiante) - LIMITE_ITENS} outros")
    else:
        linhas.append(f"• Nada nos próximos {dias} dias")
    linhas += [_previsao_diaria(projetar(con, hoje, dias + 1)), AVISO_ENTRADAS]
    return linhas


def _semanal(con, hoje: dt.date, agora: dt.datetime, dias: int) -> list[str]:
    caixa = contas_pagar.caixa_unico(con, hoje)
    proj = projetar(con, hoje, dias)
    semanas: dict[dt.date, list[dict]] = {}
    for d in proj:
        dia = dt.date.fromisoformat(d["dia"])
        semanas.setdefault(dia - dt.timedelta(days=dia.weekday()), []).append(d)
    linhas = [f"💰 *Financeiro: próximos {dias} dias*", _linha_saldo(caixa, agora)]
    for dias_da_semana in semanas.values():
        a, b = dt.date.fromisoformat(dias_da_semana[0]["dia"]), dt.date.fromisoformat(dias_da_semana[-1]["dia"])
        sai, entra = sum(d["saidas_centavos"] for d in dias_da_semana), sum(d["entradas_centavos"] for d in dias_da_semana)
        menor = min(d["saldo_centavos"] for d in dias_da_semana)
        linhas.append(f"• {_dm(a)}–{_dm(b)}: sai {_brl(sai)}" + (f", entra {_brl(entra)}" if entra else "") + f", menor saldo {_brl(menor)}")
    aperto = next((d for d in proj if d["saldo_centavos"] < 0), None)
    linhas.append(f"⚠️ Primeiro aperto: {_dm(dt.date.fromisoformat(aperto['dia']))} (falta {_brl(-aperto['saldo_centavos'])})" if aperto
                  else "Sem falta de caixa no período")
    linhas.append(AVISO_ENTRADAS)
    return linhas


def montar(con, agora: dt.datetime, dias: int = 3, semanal: bool = False) -> list[str]:
    """Linhas da mensagem. `agora` com fuso; "hoje" é sempre a data de Brasília. Diária: atrasadas, hoje, próximos `dias`,
    previsão do saldo. Semanal: `dias` à frente agrupados por semana, com o primeiro aperto de caixa."""
    hoje = agora.astimezone(BRT).date()
    return _semanal(con, hoje, agora, dias) if semanal else _diaria(con, hoje, agora, dias)
