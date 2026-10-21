"""Leitura por visão de PDF sem texto (exames): gate `saude.visao_pdf`, teto, custo por tarefa, falha fechada. Modelo e Paperless FALSOS (sem rede)."""
import json

from gabi.dinheiro.modelo import Orcamento
from gabi.correio.modelo import ModeloComCusto
from gabi.escuta.classificar import recusa_sem_envio
from gabi.fontes.openrouter import ErroOpenRouter
from tests.familia.test_rodada_exames import LAUDO, _doc, _rodar, _sistema, con  # noqa: F401

VALIDO = {"laboratorio": "Lab X", "data": "2026-07-10", "marcadores": [
    {"marcador": "TSH", "valor": 2.5, "unidade": "mUI/L", "em": None, "ref_min": 0.4, "ref_max": 4.0, "qualitativo": False, "observacao": None}]}


class ModeloPDF:
    def __init__(self, resposta=VALIDO, erro=None):
        self.resposta, self.erro, self.pdfs, self.prompts = resposta, erro, [], []

    def completar(self, prompt, *, forte):
        return "{}", 0.001

    def completar_pdf(self, pdf, prompt, *, forte=False):
        self.pdfs.append(pdf)
        self.prompts.append(prompt)
        if self.erro:
            raise self.erro
        return (self.resposta if isinstance(self.resposta, str) else json.dumps(self.resposta)), 0.004


def _ligar(con, valor="true", **extra):
    con.execute("insert into parametro(chave, valor) values ('saude.visao_pdf', ?)", (valor,))
    for k, v in extra.items():
        con.execute("insert into parametro(chave, valor) values (?, ?)", (k, json.dumps(v)))


def _doc_estado(con, pid):
    d = con.execute("select estado, motivo from exame_doc where paperless_id=?", (pid,)).fetchone()
    return d["estado"], d["motivo"]


def _baixou(srv):
    return any(c[1].endswith("/download/") for c in srv.chamadas)


def test_gate_desligado_nao_baixa_nem_chama(con, tmp_path):
    p, srv = _sistema([_doc(10, "")], tmp_path)
    m = ModeloPDF()
    r = _rodar(con, tmp_path, p, m)
    assert r["falhos"] == 1 and m.pdfs == [] and not _baixou(srv)
    assert _doc_estado(con, 10) == ("falhou", "sem texto legível (leitura por imagem desligada)")


def test_gate_com_valor_diferente_de_true_continua_desligado(con, tmp_path):
    _ligar(con, '"true"')
    p, _ = _sistema([_doc(10, "")], tmp_path)
    m = ModeloPDF()
    _rodar(con, tmp_path, p, m)
    assert m.pdfs == []


def test_gate_ligado_chama_uma_vez_e_extrai(con, tmp_path):
    _ligar(con)
    p, _ = _sistema([_doc(10, "")], tmp_path)
    m = ModeloPDF()
    r = _rodar(con, tmp_path, p, m)
    assert (r["extraidos"], r["falhos"]) == (1, 0) and len(m.pdfs) == 1 and m.pdfs[0].startswith(b"%PDF")
    assert _doc_estado(con, 10) == ("extraido", None)
    assert "DADO de terceiros" in m.prompts[0]


def test_sem_completar_pdf_comportamento_antigo(con, tmp_path):
    _ligar(con)
    p, srv = _sistema([_doc(10, "")], tmp_path)
    _rodar(con, tmp_path, p, None)
    assert _doc_estado(con, 10) == ("falhou", "sem texto legível") and not _baixou(srv)


def test_teto_de_custo_estourado_recusa_sem_enviar(con, tmp_path):
    _ligar(con)
    p, _ = _sistema([_doc(10, "")], tmp_path)
    m = ModeloPDF()
    r = _rodar(con, tmp_path, p, m, Orcamento(1, 10, gasto_dia_usd=1.0))
    assert r["falhos"] == 1 and m.pdfs == []
    assert _doc_estado(con, 10)[0] == "falhou"


def test_pdf_acima_do_teto_de_tamanho_e_recusado(con, tmp_path):
    _ligar(con, **{"saude.visao_pdf_max_mb": 0.00001})  # ~10 bytes
    p, _ = _sistema([_doc(10, "")], tmp_path)
    m = ModeloPDF()
    _rodar(con, tmp_path, p, m)
    assert m.pdfs == [] and _doc_estado(con, 10) == ("falhou", "PDF grande demais para leitura por imagem")


def test_json_invalido_descarta_sem_levantar_e_o_lote_segue(con, tmp_path):
    _ligar(con)
    p, _ = _sistema([_doc(10, ""), _doc(11, LAUDO)], tmp_path)
    r = _rodar(con, tmp_path, p, ModeloPDF("isto não é json"))
    assert (r["extraidos"], r["falhos"]) == (1, 1)
    assert _doc_estado(con, 10) == ("falhou", "leitura por imagem sem resultado") and _doc_estado(con, 11)[0] == "extraido"


def test_custo_na_tarefa_exames_visao(con, tmp_path):
    _ligar(con)
    p, _ = _sistema([_doc(10, "")], tmp_path)
    w = ModeloComCusto(ModeloPDF(), tmp_path / "g.db", tarefa="exames")
    _rodar(con, tmp_path, p, w)
    w.fechar()
    assert [tuple(r) for r in con.execute("select tarefa, custo_usd from custo_modelo")] == [("exames-visao", 0.004)]


def test_falha_do_modelo_grava_reserva_e_o_lote_segue(con, tmp_path):
    _ligar(con)
    p, _ = _sistema([_doc(10, ""), _doc(11, LAUDO)], tmp_path)
    w = ModeloComCusto(ModeloPDF(erro=ErroOpenRouter("OpenRouter -> 502")), tmp_path / "g.db", tarefa="exames")
    r = _rodar(con, tmp_path, p, w)
    w.fechar()
    assert (r["extraidos"], r["falhos"]) == (1, 1) and _doc_estado(con, 10)[0] == "falhou"
    assert [r[0] for r in con.execute("select tarefa from custo_modelo")] == ["exames-visao-falha"]


def test_recusa_antes_do_envio_nao_grava_custo(con, tmp_path):
    _ligar(con)
    p, _ = _sistema([_doc(10, "")], tmp_path)
    w = ModeloComCusto(ModeloPDF(erro=ErroOpenRouter("pdf grande demais")), tmp_path / "g.db", tarefa="exames")
    _rodar(con, tmp_path, p, w)
    w.fechar()
    assert con.execute("select count(*) from custo_modelo").fetchone()[0] == 0 and recusa_sem_envio(ErroOpenRouter("pdf inválido"))


def test_modelo_com_custo_sem_completar_pdf_no_cliente_nao_expoe_o_metodo(tmp_path):
    class So:
        def completar(self, prompt, *, forte):
            return "x", 0.1
    w = ModeloComCusto(So(), tmp_path / "g.db")
    assert getattr(w, "completar_pdf", None) is None
    w.fechar()
