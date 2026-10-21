"""Banco SINTÉTICO + API local para ver o painel e tirar capturas (nunca usa dado real).
Uso: .venv/bin/python -m tools.demo [porta]   (padrão 8099; relógio fixo em 08/10/2026 15:00 BRT)"""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

from gabi.acesso import adicionar
from gabi.api import criar_app
from gabi.db import conectar, migrar

RAIZ = Path(__file__).resolve().parent.parent
AGORA = dt.datetime(2026, 10, 8, 15, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


def _l(c, conta, ext, data, desc, v, nat, cat=None, empresa=None, parcela=None, parcelas=None, fatura=None, origem="voce"):
    c.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, estabelecimento, natureza, categoria_id, categoria_origem, "
              "empresa_id, empresa_origem, parcela, parcelas, fatura_id, status) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'posted')",
              (conta, ext, data, v, desc, desc.split()[0], nat, cat, origem if cat else None, empresa, "voce" if empresa else None, parcela, parcelas, fatura))


def _semear_agenda(c) -> None:
    """Agenda sintética (dois compromissos que se sobrepõem) só para a demonstração e as amostras do painel."""
    c.execute("insert into agenda_fonte(id, conta, provedor, estado, nome) values (1,'ricardo@ness.exemplo','google','sim','Ricardo')")
    c.execute("insert into agenda_evento(fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local, titulo, link_reuniao, participantes_qtd) values "
              "(1,'ev1','2026-10-08T19:00:00+00:00','2026-10-08T20:00:00+00:00','2026-10-08','2026-10-08','Revisão Atlas','https://meet.exemplo/a',1)")
    c.execute("insert into agenda_evento(fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local, titulo) values "
              "(1,'ev2','2026-10-08T19:30:00+00:00','2026-10-08T20:30:00+00:00','2026-10-08','2026-10-08','Dentista')")


def semear(caminho: Path) -> None:
    c = conectar(caminho)
    migrar(c, RAIZ / "migrations")
    adicionar(c, "boss@x.com", "p1", "boss", por="demo")
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b1','C6','BANK','C6 PJ','sim')")
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado, limite_centavos, vencimento_fatura) values ('c1','Itau','CREDIT','Itaú Visa','sim',500000,'2026-10-20')")
    for n in ("Mercado", "Transporte", "Receita", "Assinaturas", "Casa"):
        c.execute("insert into categoria(nome) values (?)", (n,))
    c.execute("insert into empresa(id, nome) values ('e1','Ness')")
    c.execute("insert into fatura(id, account_id, vencimento, total_centavos, pagamento_status, conta_id) values ('f0','c1','2026-09-20',35590,'PAID',2)")
    c.execute("insert into fatura(id, account_id, vencimento, total_centavos, pagamento_status, conta_id) values ('f1','c1','2026-10-20',47590,'OPEN',2)")
    _l(c, 1, "b-1", "2026-10-07", "PADARIA BOM PAO", -3550, "caixa+custo", 1)
    _l(c, 1, "b-2", "2026-10-06", "UBER TRIP", -2250, "caixa+custo", 2, empresa="e1", origem="regra")
    _l(c, 1, "b-3", "2026-10-05", "SALARIO EMPRESA", 800000, "caixa", 3, origem="banco")
    _l(c, 1, "b-4", "2026-09-28", "MERCADO CENTRAL", -10000, "caixa+custo", 1)
    _l(c, 1, "b-5", "2026-10-08", "FARMACIA SAO JOAO", -8790, "caixa+custo")
    for ext, d in (("n1", "2026-10-03"), ("n2", "2026-09-03"), ("n3", "2026-08-03"), ("n4", "2026-07-03")):
        _l(c, 2, ext, d, "NETFLIX", -5590, "custo", 4, fatura="f1" if ext == "n1" else None)
    for ext, d, par, fat in (("tv3", "2026-10-02", 3, "f1"), ("tv2", "2026-09-02", 2, None), ("tv1", "2026-08-02", 1, None)):
        _l(c, 2, ext, d, "TV PARCELADA", -30000, "custo", 5, parcela=par, parcelas=10, fatura=fat)
    _l(c, 2, "lj", "2026-10-04", "LOJA X", -12000, "custo", 1, fatura="f1")
    for em, v in (("2026-10-01T23:00:00", 1000000), ("2026-10-07T23:00:00", 1100000), ("2026-10-08T14:00:00", 1234560)):
        c.execute("insert into saldo(conta_id, em, saldo_centavos) values (1,?,?)", (em, v))
    c.execute("insert into saldo(conta_id, em, saldo_centavos) values (2,'2026-10-08T14:00:00', -47590)")
    c.execute("insert into rodada(fonte, inicio, fim, status, conferida) values ('open-finance','2026-10-08T17:00:00+00:00','2026-10-08T17:00:30+00:00','ok',1)")
    for f in ('notas-nibo', 'comprovantes-paperless', 'trabalho', 'agenda', 'correio'):  # fontes que o envelope espera (trabalho: há caixa liberada; agenda e correio: há fonte liberada)
        c.execute("insert into rodada(fonte, inicio, fim, status) values (?,'2026-10-08T17:00:00+00:00','2026-10-08T17:00:30+00:00','ok')", (f,))
    c.execute("insert into regra(padrao, acao, ativa, criado_em, criada_por) values ('UBER','{\"categoria_id\": 2}',1,'2026-10-01T10:00:00','boss@x.com')")
    c.execute("insert into regra(padrao, acao, ativa, criado_em, criada_por) values ('PADARIA','{\"categoria_id\": 1}',0,'2026-10-02T10:00:00','boss@x.com')")
    c.execute("insert into sugestao(tipo, lancamento_id, payload, estado, motivo, criado_em) values ('categoria', 5, ?, 'pendente', 'estabelecimento parecido com Mercado', '2026-10-08T12:00:00')",
              (json.dumps({"categoria_id": 1}),))
    for ext, ident, tit, proj, resp, prazo, est in (("l1", "ION-12", "Entregar laudo do cliente", "nCommand", "Ricardo", "2026-10-20", "In Progress"),
                                                    ("l2", "ION-13", "Revisar proposta", "IARA", None, None, "Todo")):
        c.execute("insert into entrega(externo_id, identificador, titulo, projeto, responsavel, prazo, estado) values (?,?,?,?,?,?,?)", (ext, ident, tit, proj, resp, prazo, est))
    for pid, nome in (("p-ric", "Ricardo"), ("p-hel", "Helena"), ("p-lia", "Lia"), ("p-bia", "Bia"), ("p-casa", "Casa")):
        c.execute("insert into pessoa(id, nome, origem) values (?,?, 'demo')", (pid, nome))
    for cid, nome, venc, valor, estado, dados in (
            ("aluguel:2026-10", "Aluguel", "2026-10-05", 350000, "atrasado", {}),
            ("internet:2026-10", "Internet", "2026-10-08", 12990, "aberto", {}),
            ("escola:2026-10", "Escola", "2026-10-10", 210000, "aberto", {}),
            ("seguro:2026-10", "Seguro do carro", "2026-10-25", 45000, "aberto", {}),
            ("luz:2026-10", "Luz", "2026-10-03", 28750, "pago", {"pago_em": "2026-10-03", "metodo": "extrato", "diferenca": 0.0})):
        c.execute("insert into compromisso(id, origem, linha_id, nome, vencimento, vencimento_util, valor_centavos, valor_fonte, forma, estado, dados, atualizado_em) "
                  "values (?, 'planilha', ?, ?, ?, ?, ?, 'planilha', 'pix', ?, ?, '2026-10-08T12:00:00')",
                  (cid, cid.split(":")[0], nome, venc, venc, valor, estado, json.dumps(dados)))
    _semear_agenda(c)
    c.close()


def main(porta: int) -> None:
    import uvicorn
    pasta = Path(tempfile.mkdtemp(prefix="gabi-demo-"))
    semear(pasta / "demo.db")
    app = criar_app(pasta / "demo.db", permite_tcp_local=True, relogio=lambda: AGORA)
    print(f"demo em http://127.0.0.1:{porta}  (cabeçalho Tailscale-User-Login: boss@x.com)")
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8099)
