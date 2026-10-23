"""Leituras do banco como eram antes da reescrita (float/reais) e `rodar_antigo`, que concilia sem gravar."""
import datetime as dt

from gabi.dinheiro import caixa, repositorio
from gabi.dinheiro.valor import para_centavos
from tools._conciliacao_antiga import compromissos, conciliacao

JANELA_TX_DIAS = 120


def _real(centavos):
    return None if centavos is None else centavos / 100.0


def _cent(reais):
    return None if reais is None else para_centavos(round(reais, 2))


class FontesBanco:
    def __init__(self, con):
        self.con = con

    def debitos(self, hoje: dt.date):
        """Débitos de conta BANK não-PJ até hoje (inclui pendentes, como o gabi-fin), mais recentes primeiro: (descricao, valor, data, account_id, id)."""
        rows = self.con.execute(
            "select l.descricao_original, l.valor_centavos, l.data, c.externo_id, l.externo_id from lancamento l join conta c on c.id=l.conta_id "
            "where c.tipo='BANK' and l.valor_centavos<0 and substr(l.data,1,10)<=? and c.pj=0 "
            "order by l.data desc, l.externo_id", (hoje.isoformat(),)).fetchall()
        return [(r[0], _real(r[1]), r[2], r[3], r[4]) for r in rows]

    def faturas(self):
        return [{"account_id": r["account_id"], "nome": r["nome"] or "", "vencimento": r["vencimento"][:10],
                 "total": _real(r["total_centavos"]), "status": r["pagamento_status"]}
                for r in self.con.execute("select f.account_id, c.apelido as nome, f.vencimento, f.total_centavos, f.pagamento_status "
                                          "from fatura f left join conta c on c.id=f.conta_id where f.vencimento is not null and f.vencimento<>''")]

    def anterior(self):
        return {r["id"]: (_real(r["valor_centavos"]), r["valor_fonte"]) for r in self.con.execute("select id, valor_centavos, valor_fonte from compromisso")}


def txs_para_conciliar(con, hoje: dt.date) -> list[dict]:
    desde = (hoje - dt.timedelta(days=JANELA_TX_DIAS)).isoformat()
    ligados = {r[0] for r in con.execute("select tx_id from conciliacao")}
    saida = []
    for r in con.execute("select l.externo_id, c.externo_id as conta, c.tipo, l.data, l.descricao_original, l.valor_centavos, l.categoria_banco, l.natureza "
                         "from lancamento l join conta c on c.id=l.conta_id order by l.data, l.externo_id"):
        if r["data"] >= desde or r["externo_id"] in ligados:
            saida.append({"id": r["externo_id"], "account_id": r["conta"], "tipo_conta": r["tipo"], "data": r["data"],
                          "descricao": r["descricao_original"], "valor": _real(r["valor_centavos"]), "categoria": r["categoria_banco"],
                          "natureza": r["natureza"]})
    return saida


def rodar_antigo(con, hoje: dt.date, agora: dt.datetime, docs=()) -> dict:
    """O mesmo que `contas_pagar.atualizar_compromissos`, sem gravar: {comp_id: (nome, vencimento, estado, motivo, tx_id)}."""
    leitura = repositorio.ler_leitura(con)
    comps = compromissos.gerar(FontesBanco(con), leitura, list(docs), hoje, [])
    donos = caixa.dono_tokens(repositorio.titulares(con)) or None
    res, _ = conciliacao.conciliar(comps, txs_para_conciliar(con, hoje), repositorio.vinculos(con),
                                   repositorio.estado_contas(con), leitura["valores"], leitura["params"], hoje, agora, donos)
    return {c["id"]: (c["nome"], c["vencimento"], res[c["id"]]["estado"], res[c["id"]].get("motivo"), res[c["id"]].get("tx_id"))
            for c in comps if c["id"] in res}
