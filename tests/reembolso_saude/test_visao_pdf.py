"""Reembolso de saúde: PDF sem texto lido por visão só com `saude.visao_pdf` ligado; teto, custo por tarefa e falha fechada. Tudo FALSO (sem rede)."""
import json

from gabi.correio.modelo import ModeloComCusto
from gabi.dinheiro.modelo import Orcamento
from gabi.fontes.openrouter import ErroOpenRouter
from tests.reembolso_saude.conftest import Modelo, con, arq, doc, pista, rodar, sistema, cofre_docs  # noqa: F401


class ModeloPDF(Modelo):
    def __init__(self, resposta=None, erro=None):
        super().__init__({}, None)
        self.resposta, self.erro_pdf, self.pdfs = pista("nf") if resposta is None else resposta, erro, []

    def completar_pdf(self, pdf, prompt, *, forte=False):
        self.pdfs.append(pdf)
        if self.erro_pdf:
            raise self.erro_pdf
        return (self.resposta if isinstance(self.resposta, str) else json.dumps(self.resposta)), 0.004


def _sem_texto(i):
    d = doc(i, "x")
    d["content"] = ""
    return d


def _ligar(con, **extra):
    con.execute("insert into parametro(chave, valor) values ('saude.visao_pdf', 'true')")
    for k, v in extra.items():
        con.execute("insert into parametro(chave, valor) values (?, ?)", (k, json.dumps(v)))


def _ref(con, pid):
    d = con.execute("select estado, motivo from reembolso_saude_doc where paperless_id=?", (pid,)).fetchone()
    return d["estado"], d["motivo"]


def _baixou(srv):
    return any(c[1].endswith("/download/") for c in srv.chamadas)


def test_gate_desligado_nao_chama_nada(con, arq):
    p, srv = sistema([_sem_texto(10)])
    m = ModeloPDF()
    r = rodar(con, arq, p, m)
    assert r["falhos"] == 1 and m.pdfs == [] and m.chamadas == 0 and not _baixou(srv)
    assert _ref(con, 10) == ("falhou", "sem texto legível (leitura por imagem desligada)")


def test_gate_ligado_chama_uma_vez_e_classifica(con, arq):
    _ligar(con)
    p, _ = sistema([_sem_texto(10)])
    m = ModeloPDF()
    r = rodar(con, arq, p, m)
    assert r["classificados"] == 1 and len(m.pdfs) == 1 and m.chamadas == 0
    assert _ref(con, 10)[0] == "classificado"


def test_sem_completar_pdf_comportamento_antigo(con, arq):
    _ligar(con)
    p, srv = sistema([_sem_texto(10)])
    rodar(con, arq, p, Modelo({}))
    assert _ref(con, 10) == ("falhou", "sem texto legível") and not _baixou(srv)


def test_teto_de_custo_estourado_espera_sem_baixar_nem_enviar(con, arq):
    _ligar(con)
    p, srv = sistema([_sem_texto(10)])
    m = ModeloPDF()
    r = rodar(con, arq, p, m, orc=Orcamento(1, 10, gasto_dia_usd=1.0))
    assert r["esperando"] == 1 and m.pdfs == [] and not _baixou(srv)
    assert con.execute("select count(*) from reembolso_saude_doc").fetchone()[0] == 0  # continua novo: tenta quando o teto liberar


def test_pdf_acima_do_teto_de_tamanho_e_recusado(con, arq):
    _ligar(con, **{"saude.visao_pdf_max_mb": 0.00001})
    p, _ = sistema([_sem_texto(10)])
    m = ModeloPDF()
    rodar(con, arq, p, m)
    assert m.pdfs == [] and _ref(con, 10) == ("falhou", "PDF grande demais para leitura por imagem")


def test_json_invalido_descarta_sem_levantar_e_o_lote_segue(con, arq):
    _ligar(con)
    p, _ = sistema([_sem_texto(10), doc(11, "nf1")])
    m = ModeloPDF("isto não é json")
    m.respostas = {"nf1": pista("nf")}
    r = rodar(con, arq, p, m)
    assert r["falhos"] == 1 and r["classificados"] == 1
    assert _ref(con, 10) == ("falhou", "resposta inválida")


def test_custo_na_tarefa_reembolso_visao(con, arq, tmp_path):
    _ligar(con)
    p, _ = sistema([_sem_texto(10)])
    w = ModeloComCusto(ModeloPDF(), tmp_path / "g.db", tarefa="reembolso-saude", tarefa_visao="reembolso-visao")
    rodar(con, arq, p, w)
    w.fechar()
    assert [tuple(r) for r in con.execute("select tarefa, custo_usd from custo_modelo")] == [("reembolso-visao", 0.004)]


def test_falha_do_modelo_grava_reserva_e_nao_derruba_o_lote(con, arq, tmp_path):
    _ligar(con)
    p, _ = sistema([_sem_texto(10), doc(11, "nf1")])
    inner = ModeloPDF(erro=ErroOpenRouter("OpenRouter -> 502"))
    inner.respostas = {"nf1": pista("nf")}
    w = ModeloComCusto(inner, tmp_path / "g.db", tarefa="reembolso-saude", tarefa_visao="reembolso-visao")
    r = rodar(con, arq, p, w)
    w.fechar()
    assert r["classificados"] == 1 and _ref(con, 10)[0] == "novo"  # falha temporária: conta tentativa e tenta de novo (como no texto)
    assert [r[0] for r in con.execute("select tarefa from custo_modelo order by id")] == ["reembolso-visao-falha", "reembolso-saude"]
