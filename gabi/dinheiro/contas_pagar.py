"""Compromissos do mês (gerar + conciliar), contas a pagar e caixa único. Consome: dinheiro.{repositorio,compromissos,conciliacao,caixa}."""
import datetime as dt
from collections import Counter
from dataclasses import dataclass, field

from gabi.dinheiro import caixa, compromissos, conciliacao, repositorio


@dataclass
class ResumoCompromissos:
    gerados: int
    estados: dict
    invalidas: list = field(default_factory=list)


def atualizar_compromissos(con, hoje: dt.date, agora: dt.datetime, docs=()) -> ResumoCompromissos:
    """Gera os compromissos do mês corrente e do seguinte, concilia com o extrato e grava. Idempotente."""
    leitura = repositorio.ler_leitura(con)
    invalidas: list = []
    comps = compromissos.gerar(repositorio.FontesBanco(con), leitura, list(docs), hoje, invalidas)
    donos = caixa.dono_tokens(repositorio.titulares(con)) or None
    res, novos = conciliacao.conciliar(comps, repositorio.txs_para_conciliar(con, hoje), repositorio.vinculos(con),
                                       repositorio.estado_contas(con), leitura["valores"], leitura["params"], hoje, agora, donos)
    repositorio.gravar_resultado(con, comps, res, novos, agora)
    return ResumoCompromissos(len(comps), dict(Counter(r["estado"] for r in res.values())), invalidas)
