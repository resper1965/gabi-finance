"""Funções puras de análise financeira, portadas do gabi-fin/finlib.py SEM alterar a lógica (R: Ponytail).

Aqui só entra o que não toca em banco nem em arquivo; o SQL vive em gabi/dinheiro/repositorio.py.
Provado contra tests/golden/finlib.json (tests/dinheiro/test_golden_caixa.py). Consome: nada.
"""
import datetime as dt
import re
import unicodedata

D = dt.date

FATURA_RE = re.compile(r'PAG(AMENTO|TO|T)?\.?\s*(DE\s+)?FATURA|FATURA\s+(DO\s+)?CART|PGTO\.?\s*CART|PAGAMENTO\s+CART|DEB(ITO)?\s+AUT\.?\s+CART', re.I)
CARTAO_QUITA_RE = re.compile(r'PAGAMENTO\s+(RECEBIDO|EFETUADO)|PAGTO\s+RECEB|CREDITO\s+DE\s+PAGAMENTO', re.I)
TAXA_RE = re.compile(r'\b(TARIFA|TAR\.?\s|ANUIDADE|JUROS|IOF|ENCARGO|MULTA|MORA|CESTA|MANUT|ROTATIVO|CHEQUE\s+ESPECIAL|LIMITE\s+UTILIZ)', re.I)
TAXA_CAT = re.compile(r'tax|interest|fee|tarif|juros|iof|encargo', re.I)

def num(v):
    try: return float(str(v).replace(',', '.'))
    except Exception: return None

def norm(desc):
    s = re.sub(r'[^A-Z ]', ' ', (desc or '').upper())
    s = re.sub(r'\b(PIX|TED|DOC|TRANSF|ENVIADO|RECEBIDO|COMPRA|PAG|PAGTO|PARC|DEB|CRED|PARA)\b', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()[:40]

def _sem_acento(s):
    return ''.join(ch for ch in unicodedata.normalize('NFD', s or '') if unicodedata.category(ch) != 'Mn').upper()

def dono_tokens(owners):
    """Nome de cada titular -> conjunto de tokens (primeiro e ultimo nome, sem acento, so > 2 letras)."""
    out = []
    for o in owners:
        toks = [t for t in _sem_acento(o).split() if len(t) > 2]
        if toks and set(toks[:1] + toks[-1:]) not in out: out.append(set(toks[:1] + toks[-1:]))
    return out

def natureza(tipo_conta, descricao, categoria, valor, donos):
    """caixa: entra no fluxo de caixa. custo: entra na apuracao de custo. Retorna 'caixa+custo','caixa','custo','neutro'."""
    d, c = descricao or '', categoria or ''
    if tipo_conta == 'CREDIT':
        if valor > 0 and CARTAO_QUITA_RE.search(d): return 'neutro'      # quitacao da fatura vista no cartao
        return 'custo'                                                    # compra (ou estorno, valor positivo) no cartao
    if FATURA_RE.search(d) or re.search(r'credit card payment', c, re.I): return 'caixa'   # paga fatura: so caixa
    if re.search(r'same.?person|mesma titular|transfer.*own', c, re.I): return 'neutro'
    if valor < 0 and tipo_conta == 'BANK' and donos:                   # transferencia propria: o nome de um titular, com ou sem PIX
        palavras = set(_sem_acento(d).split())
        if any(t <= palavras for t in donos): return 'neutro'
    if valor > 0: return 'caixa'                                          # entrada: caixa (receita nao e custo)
    return 'caixa+custo'

def aplica_regras(r, rg):
    for pat, cat, pessoa in rg:
        if pat.search(r['descricao'] or ''): return cat or r['categoria'], pessoa
    return r['categoria'] or 'sem categoria', ''

def meses_atras(n, hoje=None):
    h = hoje or D.today(); y, m = h.year, h.month - n
    while m <= 0: m += 12; y -= 1
    return D(y, m, 1)

# ---------- boleto ----------
def _m10(s):
    t = 0
    for i, ch in enumerate(reversed(s)):
        p = int(ch) * (2 if i % 2 == 0 else 1); t += p // 10 + p % 10
    return (10 - t % 10) % 10
def _m11(s, base=False):
    t = 0
    for i, ch in enumerate(reversed(s)): t += int(ch) * (2 + i % 8)
    r = t % 11
    if base: dv = 11 - r; return 1 if dv in (0, 10, 11) else dv
    return 0 if r in (0, 1) else 11 - r
BANCOS = {'001': 'Banco do Brasil', '033': 'Santander', '104': 'Caixa', '237': 'Bradesco', '341': 'Itau', '260': 'Nubank', '077': 'Inter', '336': 'C6', '208': 'BTG', '102': 'XP', '422': 'Safra', '748': 'Sicredi', '756': 'Sicoob', '212': 'Original', '623': 'Pan', '655': 'Votorantim', '041': 'Banrisul', '070': 'BRB', '389': 'Mercantil', '745': 'Citibank'}
def conferir_boleto(linha, hoje=None):
    d = re.sub(r'\D', '', linha or ''); hoje = hoje or D.today()
    if len(d) == 47:
        c1, c2, c3 = d[0:9], d[10:20], d[21:31]
        dvs = [_m10(c1) == int(d[9]), _m10(c2) == int(d[20]), _m10(c3) == int(d[31])]
        barra = d[0:4] + d[32] + d[33:37] + d[37:47] + d[4:9] + d[10:20] + d[21:31]
        geral = _m11(barra[:4] + barra[5:], base=True) == int(barra[4])
        fator = int(d[33:37]); valor = int(d[37:47]) / 100
        venc = None
        if fator:
            cands = [D(1997, 10, 7) + dt.timedelta(days=fator)] + ([D(2025, 2, 22) + dt.timedelta(days=fator - 1000)] if fator >= 1000 else [])
            venc = min(cands, key=lambda x: abs((x - hoje).days)).isoformat()
        return {'tipo': 'bancario', 'banco': d[:3] + ' ' + BANCOS.get(d[:3], '?'), 'valor': valor, 'vencimento': venc,
                'digitos_ok': all(dvs) and geral, 'detalhe_dv': {'campo1': dvs[0], 'campo2': dvs[1], 'campo3': dvs[2], 'geral': geral}}
    if len(d) == 48 and d[0] == '8':
        blocos = [d[i:i+11] for i in (0, 12, 24, 36)]; dv = [int(d[i]) for i in (11, 23, 35, 47)]
        f = _m10 if d[2] in '67' else _m11
        ok = [f(b) == v for b, v in zip(blocos, dv)]; barra = ''.join(blocos)
        return {'tipo': 'conta de consumo/tributo', 'valor': int(barra[4:15]) / 100 if d[2] in '68' else None, 'digitos_ok': all(ok)}
    return {'erro': 'linha digitavel deve ter 47 (boleto) ou 48 (consumo) digitos', 'recebidos': len(d)}

def gera_linha(banco, valor, venc, livre):
    """So para teste: monta uma linha digitavel valida."""
    fator = (venc - D(2025, 2, 22)).days + 1000; vv = f'{int(round(valor*100)):010d}'
    sem = banco + '9' + f'{fator:04d}' + vv + livre; dvg = _m11(sem, base=True)
    barra = sem[:4] + str(dvg) + sem[4:]
    c1 = barra[0:4] + barra[19:24]; c2 = barra[24:34]; c3 = barra[34:44]
    return c1 + str(_m10(c1)) + c2 + str(_m10(c2)) + c3 + str(_m10(c3)) + str(dvg) + barra[5:9] + barra[9:19]
