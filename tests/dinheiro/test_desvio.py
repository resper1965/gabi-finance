import datetime as dt

from gabi.dinheiro.desvio import fora_do_normal

HOJE = dt.date(2026, 10, 16)


class Fonte:
    def __init__(self, linhas):
        self.linhas = linhas

    def visao(self, tipo, de=None, ate=None):
        return [r for r in self.linhas if (not de or r["data"] >= de) and (not ate or r["data"] <= ate)]


def _l(data, descricao, valor):
    return {"data": data, "descricao": descricao, "valor": valor, "parcelas": None, "categoria": None, "pessoa": "", "account_id": "c1"}


def _mensal(descricao, valores, dia=5):
    """Um lançamento por mês, terminando em 2026-10 (o último valor é o do mês corrente)."""
    meses = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"][-len(valores):]
    return [_l(f"{m}-{dia:02d}", descricao, v) for m, v in zip(meses, valores)]


def test_valor_do_mes_muito_acima_do_normal_vira_aviso():
    fonte = Fonte(_mensal("ENERGIA ELETRICA", [-300, -310, -290, -305, -295, -900]))
    avisos = fora_do_normal(fonte, HOJE)
    assert [(a["descricao"], a["valor"], a["normal"], a["motivo"]) for a in avisos] == [("ENERGIA ELETRICA", 900.0, 300.0, "valor_acima")]


def test_valor_muito_abaixo_do_normal_tambem_avisa():
    fonte = Fonte(_mensal("CONDOMINIO", [-1000, -1010, -990, -1005, -995, -400]))
    assert [a["motivo"] for a in fora_do_normal(fonte, HOJE)] == ["valor_abaixo"]


def test_variacao_dentro_do_normal_nao_avisa():
    fonte = Fonte(_mensal("ENERGIA ELETRICA", [-300, -340, -270, -320, -280, -330]))
    assert fora_do_normal(fonte, HOJE) == []


def test_serie_fixa_que_reajusta_avisa_mesmo_com_desvio_zero():
    fonte = Fonte(_mensal("ACADEMIA", [-200, -200, -200, -200, -200, -240]))
    assert [(a["valor"], a["normal"]) for a in fora_do_normal(fonte, HOJE)] == [(240.0, 200.0)]


def test_serie_fixa_com_diferenca_de_centavos_nao_avisa():
    fonte = Fonte(_mensal("ACADEMIA", [-200, -200, -200, -200, -200, -200.5]))
    assert fora_do_normal(fonte, HOJE) == []


def test_mes_corrente_sem_lancamento_nao_avisa():
    fonte = Fonte(_mensal("ENERGIA ELETRICA", [-300, -310, -290, -305, -295]) )
    fonte.linhas = [r for r in fonte.linhas if r["data"] < "2026-10-01"]
    assert fora_do_normal(fonte, HOJE) == []


def test_tres_meses_fechados_ja_formam_o_normal():
    fonte = Fonte(_mensal("CONTRATO NOVO", [-300, -310, -290, -900]))
    assert [a["motivo"] for a in fora_do_normal(fonte, HOJE)] == ["valor_acima"]


def test_dois_meses_fechados_nao_formam_normal():
    fonte = Fonte(_mensal("CONTRATO NOVO", [-300, -310, -900]))
    assert fora_do_normal(fonte, HOJE) == []


def test_entrada_fora_do_normal_marca_o_sentido():
    fonte = Fonte(_mensal("X2 INTERMEDIACOES", [5000, 5100, 4900, 5050, 4950, 2000]))
    assert [(a["sentido"], a["motivo"]) for a in fora_do_normal(fonte, HOJE)] == [("entrada", "valor_abaixo")]
