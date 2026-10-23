"""Gera tests/golden/<modulo>.json: entradas SINTÉTICAS -> saídas do gabi-fin atual (/opt/gabi-fin, só leitura).

Rede de segurança do porte: o código portado em gabi/dinheiro/ só entra se reproduzir estas saídas.
Nunca usa dado real da família. Uso: python tools/golden.py [--todos]
"""
import datetime as dt
import importlib
import json
import re
import sqlite3
import sys
from pathlib import Path

FIN_DIR = "/opt/gabi-fin"
SAIDA = Path(__file__).resolve().parent.parent / "tests" / "golden"
sys.dont_write_bytecode = True  # nunca grava __pycache__ dentro de /opt/gabi-fin


def _mod(nome):
    if FIN_DIR not in sys.path:
        sys.path.insert(0, FIN_DIR)
    m = importlib.import_module(nome)
    if nome == "finlib":
        m.REGRAS = "/inexistente/regras.txt"  # nunca ler as regras reais do OpenClaw: a referência é sintética
    return m


def _ser(x):
    """Torna a saída comparável e serializável em JSON (conjuntos ordenados, datas ISO, tuplas como listas)."""
    if isinstance(x, dict):
        return {str(k): _ser(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_ser(v) for v in x]
    if isinstance(x, (set, frozenset)):
        return sorted((_ser(v) for v in x), key=lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False))
    if isinstance(x, (dt.date, dt.datetime)):
        return x.isoformat()
    if isinstance(x, float) and x != x:
        return "NaN"
    return x


def _data(s):
    return dt.date.fromisoformat(s)


# ---------------- bancos sintéticos (mesmo esquema do fin.db) ----------------
def _banco(finlib, tx=(), contas=(), faturas=()):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(finlib.SCHEMA)
    for t in tx:
        c.execute("insert into tx(id,account_id,tipo_conta,data,descricao,valor,categoria,operacao,metodo,parcela,parcelas,"
                  "data_compra,fatura_id,natureza,raw) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", t)
    for k in contas:
        c.execute("insert into contas(ts,account_id,tipo,nome,banco,saldo,limite,disponivel,vencimento) values (?,?,?,?,?,?,?,?,?)", k)
    for f in faturas:
        c.execute("insert into faturas(id,account_id,vencimento,total,minimo,raw) values (?,?,?,?,?,?)", f)
    return c


def _tx(i, data, desc, valor, conta="a1234", tipo="BANK", natureza="caixa+custo", cat="", parcela=None, parcelas=None):
    return (f"t{i}", conta, tipo, data, desc, valor, cat, "", "", parcela, parcelas, data, None, natureza, "{}")


def _historico():
    """6 meses de movimento: assinatura fixa, aluguel, salário, conta variável, pensão com 2 pagamentos no mês."""
    rows, i = [], 0
    for ano, mes in [(2026, 4), (2026, 5), (2026, 6), (2026, 7), (2026, 8), (2026, 9), (2026, 10)]:
        base = f"{ano}-{mes:02d}"
        for dia, desc, v in [(10, "NETFLIX.COM", -55.90), (5, "ALUGUEL IMOBILIARIA SUL", -2000.0), (1, "SALARIO EMPRESA XYZ", 8000.0),
                             (15, "ENERGIA ENEL", -(180.0 + mes * 7)), (20, "PENSAO FULANO DE TAL", -1500.0)]:
            if base == "2026-10" and dia > 8:
                continue
            i += 1
            rows.append(_tx(i, f"{base}-{dia:02d}", desc, v))
        if base in ("2026-09", "2026-10"):
            i += 1
            rows.append(_tx(i, f"{base}-03", "PENSAO FULANO DE TAL", -500.0))
    return rows


def _w_recorrentes(visao, hoje):
    f = _mod("finlib")
    return f.recorrentes(_banco(f, tx=_historico()), visao, _data(hoje))


def dados_gastos():
    return [_tx(1, "2026-09-02", "PADARIA BOM PAO", -35.0, cat="Food"), _tx(2, "2026-09-03", "UBER TRIP", -22.5, cat="Transport"),
            _tx(3, "2026-09-10", "UBER TRIP", -31.0, cat="Transport"), _tx(4, "2026-09-12", "MERCADO", -310.0, tipo="CREDIT", natureza="custo", cat="Groceries"),
            _tx(5, "2026-09-15", "SALARIO", 5000.0, natureza="caixa")]


def _w_gastos(de, ate, por):
    f = _mod("finlib")
    return f.gastos(_banco(f, tx=dados_gastos()), de, ate, por)


def dados_previsao():
    contas = [("2026-10-08T07:00", "a1234", "BANK", "Conta", "C6", 5000.0, None, None, None),
              ("2026-10-08T07:00", "c9999", "CREDIT", "Cartao", "Itau", -800.0, 5000.0, 4200.0, "2026-10-20")]
    faturas = [("f1", "c9999", "2026-10-20", 800.0, 80.0, "{}")]
    tx = _historico() + [_tx(900, "2026-09-02", "COMPRA PARCELADA", -120.0, conta="c9999", tipo="CREDIT", natureza="custo", parcela=2, parcelas=5)]
    return tx, contas, faturas


def _w_previsao(dias, extra, hoje):
    f = _mod("finlib")
    tx, contas, faturas = dados_previsao()
    return f.previsao(_banco(f, tx=tx, contas=contas, faturas=faturas), dias, extra, _data(hoje))


def dados_vazamentos():
    return _historico() + [_tx(901, "2026-09-05", "TARIFA MANUTENCAO CONTA", -29.9), _tx(902, "2026-09-06", "IOF", -12.0),
                           _tx(903, "2026-09-09", "LANCHE X", -40.0), _tx(904, "2026-09-09", "LANCHE X", -40.0, conta="b5555")]


def _w_vazamentos(meses, hoje):
    f = _mod("finlib")
    return f.vazamentos(_banco(f, tx=dados_vazamentos()), meses, _data(hoje))


def _w_natureza(tipo, desc, cat, valor, donos):
    f = _mod("finlib")
    return f.natureza(tipo, desc, cat, valor, f.dono_tokens(donos))


def _w_aplica(r, regras):
    import re as _re
    f = _mod("finlib")
    return f.aplica_regras(r, [(_re.compile(p, _re.I), c, pes) for p, c, pes in regras])


def _w_boleto(banco, valor, venc, livre, hoje, quebrar=False):
    f = _mod("finlib")
    linha = f.gera_linha(banco, valor, _data(venc), livre)
    if quebrar:
        linha = linha[:-1] + str((int(linha[-1]) + 1) % 10)
    return {"linha": linha, "resultado": f.conferir_boleto(linha, _data(hoje))}


def _w_conferir(linha, hoje):
    return _mod("finlib").conferir_boleto(linha, _data(hoje))


def _cnpj_valido(base12):
    e = _mod("extrator")
    for n in (12, 13):
        pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] if n == 12 else [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        r = sum(int(a) * b for a, b in zip(base12[:n], pesos)) % 11
        base12 += str(0 if r < 2 else 11 - r)
    return base12


def _tlv(tag, valor):
    return f"{tag}{len(valor):02d}{valor}"


def _pix(valor="123.45"):
    """Copia-e-cola Pix bem formado (campos TLV com tamanho exato) com o CRC16 correto."""
    e = _mod("extrator")
    conta = _tlv("00", "BR.GOV.BCB.PIX") + _tlv("01", "123e4567-e89b-12d3-a456-426614174000")
    base = (_tlv("00", "01") + _tlv("26", conta) + _tlv("52", "0000") + _tlv("53", "986") + _tlv("54", valor)
            + _tlv("58", "BR") + _tlv("59", "FULANO DE TAL") + _tlv("60", "SAO PAULO") + _tlv("62", _tlv("05", "***")) + "6304")
    return base + e._crc16(base)


def _w_pix_valor(codigo):
    return _mod("extrator").pix_valor(codigo)


def _comprovante():
    return ("Comprovante de transferência Pix\nValor: R$ 1.250,00\nData/Hora: 07/10/2026 10:15\n"
            "Dados de quem pagou\nNome: Ricardo Teste\nCPF: ***.123.456-**\nBanco: C6\n"
            "Dados de quem recebeu\nNome: Padaria Bom Pao Ltda\nCNPJ: 11.222.333/0001-81\nChave Pix: padaria@exemplo.com\n"
            "Instituicao: Itau\nAgencia: 1234\nConta: 56789-0\n")


def _bruto_planilha():
    cab = ["id", "nome", "extrato", "apelidos", "vencimento", "ajuste_dia_util", "valor_tipo", "valor_padrao", "forma", "conta", "cartao",
           "documento", "pix", "ativo", "valido_de", "valido_ate", "obs"]

    def linha(id_, nome="Nome", extrato="EXTRATO", venc="dia:5", ajuste="", tipo="", padrao="", forma="", ativo="", de="", ate="", apelidos=""):
        return [id_, nome, extrato, apelidos, venc, ajuste, tipo, padrao, forma, "", "", "", "", ativo, de, ate, ""]

    return {
        "Compromissos": [cab,
            linha("aluguel", "Aluguel", "IMOBILIARIA SUL", "dia:5", tipo="fixo", padrao="2.000,00", forma="pix", apelidos="IMOB SUL; ALUGUEL"),
            linha("energia", "Energia", "ENEL", "dia:15", tipo="variavel", forma="boleto"),
            linha("escola", "Escola", "COLEGIO", "5du", ajuste="antecipa", tipo="fixo", padrao=3000, forma="boleto"),
            linha("velho", "Antigo", "ANTIGO", "dia:1", ativo="nao"),
            linha("ruim-venc", "Ruim", "X", "45"),
            linha("ruim-forma", "Ruim", "X", "dia:5", forma="cheque"),
            linha("com espaco", "Ruim", "X", "dia:5"),
            linha("aluguel", "Duplicado", "Y", "dia:6"),
            linha("sem-nome", "", "X", "dia:5"),
            linha("datas", "Datas", "X", "dia:5", de="2026-12", ate="2026-01"),
            linha("serie", "Serie", "S", "dia:7", tipo="fixo", padrao="100", de="2026-01", ate="2026-12"),
            linha("serie-202611", "Serie nova", "S", "dia:7", tipo="fixo", padrao="110", de="2026-11"),
            linha("valor-ruim", "Valor", "V", "dia:9", padrao="abc"),
        ],
        "Parâmetros": [["chave", "valor"], ["janela_antes_dias", 7], ["tolerancia_fixo", "2%"], ["tolerancia_valor", "1,50"],
                       ["horas_conta_parada", "abc"], ["bancos_pj", "C6 PJ; Inter PJ"], ["chave_desconhecida", 1]],
        "Valores do mês": [["mes", "compromisso", "tipo", "valor", "vencimento", "data_pagamento", "origem", "registrado_em"],
                           ["2026-10", "energia", "valor", "230,50", "2026-10-15", "", "boleto", ""],
                           ["2026-10", "aluguel", "pago", "", "", "2026-10-03", "manual", ""],
                           ["2026-13", "energia", "valor", "10", "", "", "", ""],
                           ["2026-10", "fantasma", "valor", "10", "", "", "", ""]],
    }


def _w_validar(variante):
    p = _mod("planilha")
    b = _bruto_planilha()
    if variante == "sem_colunas":
        b["Compromissos"] = [["id", "nome"], ["x", "Y"]]
    elif variante == "vazia":
        b = {}
    r = p.validar(b, _data("2026-10-08"))
    return {"bruto": b, "leitura": r}


def casos():
    hoje = "2026-10-08"
    cnpj = _cnpj_valido("112223330001")
    linha = _w_boleto("341", 1234.56, "2026-10-20", "1" * 25, hoje)["linha"]
    linha_fmt = f"{linha[:5]}.{linha[5:10]} {linha[10:15]}.{linha[15:21]} {linha[21:26]}.{linha[26:32]} {linha[32]} {linha[33:]}"
    return {
        "finlib": [
            *[{"fn": "norm", "args": [s]} for s in ["PIX ENVIADO PADARIA BOM PAO 123", "COMPRA CARTAO MERCADO SÃO JOÃO", "", None,
                                                     "TED PARA FULANO DE TAL LTDA ME", "DEB AUT ENEL 0123456789 PARC 2/5"]],
            *[{"fn": "num", "args": [v]} for v in ["12,5", "12.5", "abc", None, "1.234,56", "", 7]],
            *[{"fn": "dono_tokens", "args": [o]} for o in [["Ricardo Esper"], ["João da Silva Neto", "Ricardo Esper"], [], ["Ana"], ["Maria Açaí de Souza"]]],
            *[{"fn": "_w_natureza", "args": a} for a in [
                ["CREDIT", "COMPRA MERCADO", "Groceries", -50.0, []], ["CREDIT", "PAGAMENTO RECEBIDO", "", 100.0, []],
                ["CREDIT", "ESTORNO LOJA", "", 20.0, []], ["BANK", "PAGAMENTO FATURA CARTAO", "", -300.0, []],
                ["BANK", "DEB AUT CART ITAU", "", -100.0, []], ["BANK", "PIX ENVIADO RICARDO ESPER", "", -100.0, ["Ricardo Esper"]],
                ["BANK", "PIX ENVIADO JOAO", "", -100.0, ["Ricardo Esper"]], ["BANK", "SALARIO", "", 5000.0, []],
                ["BANK", "MERCADO", "Same person transfer", -10.0, []], ["BANK", "X", "Credit card payment", -10.0, []],
                ["BANK", "TARIFA", "", -9.9, []]]],
            *[{"fn": "_w_aplica", "args": a} for a in [
                [{"descricao": "UBER TRIP", "categoria": "Transport"}, [["UBER", "Transporte", "Ricardo"]]],
                [{"descricao": "PADARIA", "categoria": "Food"}, [["UBER", "Transporte", "Ricardo"]]],
                [{"descricao": "UBER", "categoria": "Transport"}, [["UBER", "", "Bia"]]],
                [{"descricao": "X", "categoria": ""}, []]]],
            *[{"fn": "meses_atras", "args": [n, h], "data": [1]} for n, h in [(0, hoje), (1, hoje), (10, "2026-03-31"), (13, "2026-01-15")]],
            {"fn": "_w_boleto", "args": ["341", 1234.56, "2026-10-20", "1" * 25, hoje]},
            {"fn": "_w_boleto", "args": ["237", 99.9, "2026-11-05", "2" * 25, hoje]},
            {"fn": "_w_boleto", "args": ["341", 1234.56, "2026-10-20", "1" * 25, hoje, True]},
            {"fn": "_w_conferir", "args": ["123", hoje]},
            {"fn": "_w_conferir", "args": ["8" + "1" * 47, hoje]},
            {"fn": "_w_recorrentes", "args": ["caixa", hoje]},
            {"fn": "_w_recorrentes", "args": ["custo", hoje]},
            {"fn": "_w_gastos", "args": ["2026-09-01", "2026-09-30", "categoria"]},
            {"fn": "_w_gastos", "args": ["2026-09-01", "2026-09-30", "descricao"]},
            {"fn": "_w_previsao", "args": [30, None, hoje]},
            {"fn": "_w_previsao", "args": [30, {"data": "2026-10-15", "valor": 500.0, "descricao": "compra"}, hoje]},
            {"fn": "_w_vazamentos", "args": [3, hoje]},
        ],
        "previstas": [
            *[{"fn": "feriados", "args": [a]} for a in (2024, 2025, 2026, 2027)],
            *[{"fn": "dia_util", "args": a} for a in [[2026, 10, 1], [2026, 11, 5], [2026, 12, 22], [2026, 1, 1], [2026, 4, 3]]],
            *[{"fn": "forma", "args": [s]} for s in ["PIX ENVIADO X", "DEBITO AUTOMATICO LUZ", "BOLETO PAGO", "DEB AUT ENEL", "COMPRA", "TRANSFERENCIA DOC", None]],
        ],
        "compromissos": [
            *[{"fn": "vencimento_do_mes", "args": a} for a in [["5du", 2026, 10], ["dia:31", 2026, 2], ["dia:15", 2026, 10], ["1du", 2026, 1],
                                                                ["40du", 2026, 10], ["xyz", 2026, 10], [" 5DU ", 2026, 11]]],
            *[{"fn": "vencimento_util", "args": [d, aj], "data": [0]} for d in ("2026-10-10", "2026-10-12", "2026-12-25", "2026-10-09")
              for aj in ("adia", "antecipa")],
        ],
        "extrator": [
            {"fn": "pix_valido", "args": [_pix()]}, {"fn": "pix_valido", "args": [_pix()[:-1] + "0"]}, {"fn": "pix_valido", "args": ["abc"]},
            {"fn": "pix_valor", "args": [_pix()]}, {"fn": "pix_valor", "args": [_pix("0.00")]}, {"fn": "pix_valor", "args": ["zz"]},
            {"fn": "achar_codigo", "args": [f"pague aqui {_pix()} obrigado", hoje], "data": [1]},
            {"fn": "achar_codigo", "args": [f"boleto {linha_fmt} vence 20/10", hoje], "data": [1]},
            {"fn": "achar_codigo", "args": ["nada de codigo aqui", hoje], "data": [1]},
            {"fn": "achar_cnpj", "args": [f"CNPJ {cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]} Padaria"]},
            {"fn": "achar_cnpj", "args": ["CNPJ 11.222.333/0001-00"]}, {"fn": "achar_cnpj", "args": ["00000000000000"]},
            *[{"fn": "tipo_documento", "args": [t]} for t in ["Documento de Arrecadação do eSocial", "DAE eSocial competência 09/2026",
                                                              "Comprovante de pagamento Pix", "texto qualquer", None]],
            {"fn": "ler_comprovante_pix", "args": [_comprovante()]},
            {"fn": "ler_comprovante_pix", "args": ["Nome: A\nNome: B\nCPF: 1\nCPF: 2"]},
            {"fn": "ler_comprovante_pix", "args": [""]},
        ],
        "planilha": [{"fn": "_w_validar", "args": [v]} for v in ("completa", "sem_colunas", "vazia")],
        "emissores": [
            *[{"fn": "chave_extrato", "args": [s]} for s in ["Padaria São João Ltda", None, "", "ENEL DISTRIBUIÇÃO", "PIX ENVIADO JOAO"]],
            *[{"fn": "generica", "args": [s]} for s in ["BOLETO", "FATURA 2026", "11222333000181", "CONTA DE LUZ", None, "ENEL DISTRIBUICAO SP"]],
            *[{"fn": "chave_forte", "args": [s]} for s in ["ENEL DISTRIBUICAO SP", "ENEL", "11222333000181", None]],
            *[{"fn": "chave", "args": a} for a in [["11.222.333/0001-81", "x"], [None, "Boleto 123456"], [None, "Enel Distribuição SP"], [None, "Luz"]]],
        ],
    }


def _executar(modulo, caso):
    nome = caso["fn"]
    alvo = globals()[nome] if nome.startswith("_w_") else getattr(_mod(modulo), nome)
    args = list(caso["args"])
    for i in caso.get("data", []):
        args[i] = _data(args[i])
    try:
        return {"saida": _ser(alvo(*args))}
    except Exception as e:  # noqa: BLE001 - a exceção faz parte do comportamento a preservar
        return {"erro": type(e).__name__, "mensagem": str(e)}


def gerar() -> dict[str, int]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    total = {}
    for modulo, lista in casos().items():
        saida = []
        for caso in lista:
            saida.append({"fn": caso["fn"], "args": _ser(caso["args"]), "data": caso.get("data", []), **_executar(modulo, caso)})
        (SAIDA / f"{modulo}.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        total[modulo] = len(saida)
    return total


if __name__ == "__main__":
    t = gerar()
    print(f"{len(t)} módulos, {sum(t.values())} casos: " + ", ".join(f"{k}={v}" for k, v in t.items()))
