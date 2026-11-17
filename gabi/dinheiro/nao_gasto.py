"""O que não é gasto: ajusta a natureza do lançamento depois do caixa.natureza (que fica intocado, provado pelo golden).

Saem de Gastos (natureza 'caixa+custo' -> 'caixa'), só em conta corrente e saída:
- boleto que paga fatura de cartão: bate com uma fatura conhecida (valor ±R$ 1, até 15 dias do vencimento) ou foi pago ao emissor de um
  cartão do Ricardo (as compras já estão em Gastos; contar a fatura seria contar duas vezes). Boleto de escola, condomínio etc. segue gasto;
- Pix/transferência para empresa do próprio Ricardo (cadastro de empresas, relação "pj_titular"), pelo nome ou pelo CNPJ;
- investimento: categoria do banco "Investments", aplicação, transferência para conta investimento, chamada de margem.
A marcação manual (natureza_manual 'gasto' | 'nao_gasto') vence tudo. Idempotente: recalcula a partir do caixa.natureza.
Consome: db (lancamento, conta, fatura, empresa, natureza_manual/natureza_regra).
"""
import json
import re

from gabi.dinheiro import caixa, repositorio

TOLERANCIA_CENTAVOS = 100
JANELA_DIAS = 15
BOLETO_RE = re.compile(r'PAGAMENTO\s+DE\s+BOLETO|PAG\s+BOLETO', re.I)
INVESTIMENTO_RE = re.compile(r'CONTA\s+INVESTIMENTO|APLICA[CÇ][AÃ]O|CHAMADA\s+DE\s+MARGEM', re.I)
# como cada emissor de cartão aparece no extrato quando o boleto da fatura é pago (chave: instituição da conta de cartão, sem acento)
EMISSORES = {"ITAU": r'\bITAU\b|\bINT\s+PERS', "XP": r'\bXP\b', "BRADESCO": r'\bBRADESCO\b', "SANTANDER": r'\bSANTANDER\b',
             "C6": r'\bC6\b', "NUBANK": r'\bNU\s*PAGAMENTOS|\bNUBANK\b'}
_SEM_CUSTO = {"caixa+custo": "caixa", "custo": "neutro"}
_COM_CUSTO = {"caixa": "caixa+custo", "neutro": "custo"}


def _emissores(con) -> re.Pattern | None:
    padroes = set()
    for (inst,) in con.execute("select distinct instituicao from conta where tipo='CREDIT' and excluido_em is null and instituicao is not null"):
        nome = caixa._sem_acento(inst)
        padroes |= {p for chave, p in EMISSORES.items() if chave in nome.split() or nome.startswith(chave)}
    return re.compile("|".join(sorted(padroes)), re.I) if padroes else None


def _proprias(con) -> list[tuple[str, str]]:
    """(nome sem sufixo societário, CNPJ só dígitos) de cada empresa com relação pj_titular."""
    saida = []
    for r in con.execute("select nome, cnpj, dados from empresa"):
        try:
            dados = json.loads(r["dados"] or "{}")
        except ValueError:
            dados = {}
        if dados.get("relacao") == "pj_titular":
            nome = re.sub(r'\b(LTDA|S\.?A\.?|EIRELI|ME|EPP|UNIPESSOAL|LDA)\b\.?', ' ', caixa._sem_acento(r["nome"]))
            saida.append((re.sub(r'\s+', ' ', nome).strip(), re.sub(r'\D', '', r["cnpj"] or "")))
    return saida


def _paga_fatura(con, r) -> bool:
    return con.execute("select 1 from fatura f join conta k on k.id=f.conta_id where k.tipo='CREDIT' and abs(f.total_centavos + ?) <= ? "
                       "and abs(julianday(f.vencimento) - julianday(?)) <= ? limit 1",
                       (r["valor_centavos"], TOLERANCIA_CENTAVOS, r["data"], JANELA_DIAS)).fetchone() is not None


def regra(con, r, emissores, proprias) -> str | None:
    """Por que este lançamento de conta corrente não é gasto (None = é gasto)."""
    desc, cat = r["descricao_original"] or "", r["categoria_banco"] or ""
    if BOLETO_RE.search(desc) or re.search(r'bank\s*slip', cat, re.I):
        if _paga_fatura(con, r):
            return "fatura"
        if emissores and emissores.search(caixa._sem_acento(desc)):
            return "emissor"
    texto = caixa._sem_acento(desc)
    digitos = re.sub(r'\D', '', desc)
    for nome, cnpj in proprias:
        if (nome and nome in texto) or (cnpj and cnpj in digitos):
            return "propria"
    if re.fullmatch(r'investments?', cat.strip(), re.I) or INVESTIMENTO_RE.search(desc):
        return "investimento"
    return None


def reaplicar(con, ids=None) -> dict:
    """Recalcula natureza/natureza_regra de todos os lançamentos (ou só de `ids`). Devolve {regra: quantos lançamentos mudaram}.
    Não abre transação: quem chama decide (a captura e as rotas já estão numa)."""
    donos = caixa.dono_tokens(repositorio.titulares(con))
    emissores, proprias = _emissores(con), _proprias(con)
    sql = ("select l.id, l.data, l.valor_centavos, l.descricao_original, l.categoria_banco, l.natureza, l.natureza_regra, l.natureza_manual, "
           "c.tipo from lancamento l join conta c on c.id=l.conta_id")
    args: list = []
    if ids is not None:
        ids = list(ids)
        if not ids:
            return {}
        sql += f" where l.id in ({','.join('?' * len(ids))})"
        args = ids
    contagem: dict[str, int] = {}
    for r in con.execute(sql, args).fetchall():
        nat = caixa.natureza(r["tipo"], r["descricao_original"], r["categoria_banco"], r["valor_centavos"] / 100, donos)
        motivo = None
        if r["natureza_manual"] == "nao_gasto":
            nat, motivo = _SEM_CUSTO.get(nat, nat), "manual"
        elif r["natureza_manual"] == "gasto":
            nat, motivo = _COM_CUSTO.get(nat, nat), "manual"
        elif nat == "caixa+custo" and r["tipo"] == "BANK" and r["valor_centavos"] < 0:
            motivo = regra(con, r, emissores, proprias)
            if motivo:
                nat = "caixa"
        if (nat, motivo) != (r["natureza"], r["natureza_regra"]):
            con.execute("update lancamento set natureza=?, natureza_regra=? where id=?", (nat, motivo, r["id"]))
            chave = motivo or "sem_regra"  # sem_regra: voltou ao que o caixa.natureza diz (ex.: marcação manual tirada)
            contagem[chave] = contagem.get(chave, 0) + 1
    return contagem


if __name__ == "__main__":  # reaplica no histórico todo: python -m gabi.dinheiro.nao_gasto --banco /var/lib/gabi-finance/gabi.db
    import argparse
    from pathlib import Path

    from gabi.db import conectar, transacao

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--banco", type=Path, required=True)
    con = conectar(ap.parse_args().banco)
    soma = "select coalesce(sum(-valor_centavos), 0) from lancamento where natureza like '%custo%' and valor_centavos<0"
    antes = con.execute(soma).fetchone()[0]
    with transacao(con):
        mudou = reaplicar(con)
    print(f"mudaram: {mudou}; gastos (saídas) antes {antes / 100:.2f}, depois {con.execute(soma).fetchone()[0] / 100:.2f}")
