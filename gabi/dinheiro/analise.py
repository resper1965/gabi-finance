"""Análises do caixa (recorrentes, previsão, gastos, vazamentos). Portado do gabi-fin/finlib.py SEM alterar a lógica.

O acesso ao banco virou `fonte` (visao, ultimo_snapshot, faturas, parcelas_cartao) — ver dinheiro/repositorio.FonteAnalise.
Única mudança deliberada: gastos/vazamentos usam a categoria e o "para quem" JÁ classificados no lançamento (r['categoria'],
r['pessoa']) em vez de aplicar o arquivo de regras do OpenClaw. Provado contra tests/golden/finlib.json. Consome: dinheiro.caixa.
"""
import datetime as dt
import statistics as st

from gabi.dinheiro.caixa import TAXA_CAT, TAXA_RE, meses_atras, norm
from gabi.hoje import hoje_brt

D = dt.date


CORTE_SERIE = 0.6  # pagamento < 60% do principal do mes, ao mesmo favorecido, e outra obrigacao (ex.: pensao x reembolso)

def _series(rs, fim_mes):
    """Mesmo favorecido com mais de um pagamento no mes: separa a serie principal (o maior de cada mes
    anterior) dos demais. A referencia vem so dos meses fechados: um pagamento menor deste mes nao vira a principal."""
    por_mes = {}
    for r in rs: por_mes.setdefault(r['data'][:7], []).append(r)
    if all(len(v) == 1 for v in por_mes.values()): return [('', rs, None)]
    maiores = sorted((max(v, key=lambda r: abs(r['valor'])) for m, v in por_mes.items() if m < fim_mes.strftime('%Y-%m')),
                     key=lambda r: r['data'])
    if not maiores: return [('', rs, None)]
    ref = abs(maiores[-1]['valor'])
    princ = [r for r in rs if abs(r['valor']) >= ref * CORTE_SERIE]
    outros = [r for r in rs if abs(r['valor']) < ref * CORTE_SERIE]
    corte = round(ref * CORTE_SERIE, 2)
    return [('', princ, [corte, None])] + ([(' OUTRO', outros, [0, corte])] if outros else [])

def _recorrente(rs, nd, sinal, ult4, fim_mes):
    meses = {r['data'][:7] for r in rs}
    if len(meses & ult4) < 3: return None
    vals = [abs(r['valor']) for r in rs]; med = st.median(vals)
    cv = (st.pstdev(vals) / st.mean(vals)) if len(vals) > 1 and st.mean(vals) else 0
    dia = int(st.median(int(r['data'][8:10]) for r in rs))
    este_mes = any(r['data'] >= fim_mes.isoformat() for r in rs)
    rs = sorted(rs, key=lambda r: r['data'])
    prev = [abs(r['valor']) for r in rs if r['data'][:7] < max(meses)]; ultr = rs[-1]; ult = abs(ultr['valor'])
    return {'descricao': ultr['descricao'], 'chave': nd, 'sentido': 'entrada' if sinal > 0 else 'saida', 'valor_medio': round(med, 2),
            'tipo': 'fixo' if cv < 0.05 else 'variavel', 'dia': dia, 'meses': len(meses), 'ja_ocorreu_este_mes': este_mes,
            'ultimo': round(ult, 2), 'dia_ultimo': int(ultr['data'][8:10]), 'mediana_anterior': round(st.median(prev), 2) if prev else None}

def recorrentes(fonte, visao_nome='caixa', hoje=None):
    hoje = hoje or hoje_brt(); ini = meses_atras(6, hoje).isoformat(); fim_mes = hoje.replace(day=1)
    grupos = {}
    for r in fonte.visao(visao_nome, ini):
        if r['parcelas'] and r['parcelas'] > 1: continue
        k = (norm(r['descricao']), 1 if r['valor'] > 0 else -1)
        if not k[0]: continue
        grupos.setdefault(k, []).append(r)
    out = []
    ult4 = {meses_atras(i, hoje).strftime('%Y-%m') for i in range(1, 5)}
    for (nd, sinal), rs in grupos.items():
        for sufixo, serie, faixa in _series(rs, fim_mes):
            item = _recorrente(serie, nd + sufixo, sinal, ult4, fim_mes)
            if item:
                item['faixa'] = faixa  # [min, max) do valor desta serie quando o favorecido tem duas
                if sufixo: item['descricao'] += ' (outro pagamento)'
                out.append(item)
    return sorted(out, key=lambda x: -x['valor_medio'])

def previsao(fonte, dias=30, extra=None, hoje=None):
    hoje = hoje or hoje_brt(); fim = hoje + dt.timedelta(days=dias)
    ts, contas = fonte.ultimo_snapshot()
    saldo = sum(x['saldo'] or 0 for x in contas if x['tipo'] != 'CREDIT')
    ev = []
    for r in recorrentes(fonte, 'caixa', hoje):
        y, m = hoje.year, hoje.month
        for _ in range(3):
            saida = r['sentido'] != 'entrada'  # pagamento: referencia e o ultimo (valor e dia), nao a mediana
            try: dia = D(y, m, min(r['dia_ultimo'] if saida else r['dia'], 28))
            except ValueError: dia = None
            if dia and hoje <= dia <= fim and not (dia.month == hoje.month and r['ja_ocorreu_este_mes']):
                ev.append((dia, r['descricao'], -r['ultimo'] if saida else r['valor_medio'], 'recorrente ~' if r['tipo'] == 'variavel' else 'recorrente'))
            m += 1
            if m > 12: m = 1; y += 1
    ult_fat = {}
    for f in fonte.faturas(hoje.isoformat(), fim.isoformat()):
        ev.append((D.fromisoformat(f['vencimento'][:10]), 'Fatura cartao ' + f['account_id'][-4:], -abs(f['total'] or 0), 'fatura'))
        ult_fat[f['account_id']] = max(ult_fat.get(f['account_id'], ''), f['vencimento'][:10])
    venc_cartao = {x['account_id']: (x['vencimento'] or '')[:10] for x in contas if x['tipo'] == 'CREDIT'}
    for r in fonte.parcelas_cartao():
        dv = venc_cartao.get(r['account_id']) or ''
        if not dv: continue
        base = D.fromisoformat(dv); limite = ult_fat.get(r['account_id'], '')
        for k in range(1, r['parcelas'] - r['parcela'] + 1):
            mm = base.month + k; yy = base.year + (mm - 1) // 12; mm = (mm - 1) % 12 + 1
            d = D(yy, mm, min(base.day, 28))
            if d.isoformat() > limite and hoje <= d <= fim: ev.append((d, 'Parcela futura: ' + (r['descricao'] or ''), -abs(r['valor']), 'parcela'))
    if extra: ev.append((D.fromisoformat(extra['data']), extra.get('descricao', 'simulado'), -abs(extra['valor']), 'simulado'))
    ev.sort(key=lambda e: e[0]); s = saldo; linhas = []; minimo = (saldo, hoje.isoformat())
    for d, desc, v, tipo in ev:
        s += v; linhas.append({'data': d.isoformat(), 'descricao': desc, 'valor': round(v, 2), 'tipo': tipo, 'saldo': round(s, 2)})
        if s < minimo[0]: minimo = (s, d.isoformat())
    semanas = {}
    for l in linhas:
        w = (D.fromisoformat(l['data']) - hoje).days // 7; semanas[w] = l['saldo']
    return {'dados_de': ts, 'saldo_inicial': round(saldo, 2), 'eventos': linhas, 'saldo_final': round(s, 2),
            'menor_saldo': round(minimo[0], 2), 'dia_menor_saldo': minimo[1],
            'saldo_fim_semana': {f'semana_{k+1}': v for k, v in sorted(semanas.items())},
            'aviso': 'recorrentes ~ sao medias; faturas abertas so entram quando o banco publica'}

def gastos(fonte, de, ate, por='categoria'):
    agg = {}
    for r in fonte.visao('custo', de, ate):
        cat, pessoa = r['categoria'] or 'sem categoria', r.get('pessoa') or ''  # a classificação já vem aplicada (categoria/para quem)
        k = {'categoria': cat, 'pessoa': pessoa or '(sem pessoa)', 'mes': r['data'][:7], 'descricao': norm(r['descricao']), 'conta': r['account_id'][-4:]}.get(por, cat)
        agg[k] = agg.get(k, 0) - r['valor']
    tot = sum(agg.values())
    return {'de': de, 'ate': ate, 'por': por, 'total_custo': round(tot, 2), 'itens': [{'chave': k, 'valor': round(v, 2)} for k, v in sorted(agg.items(), key=lambda x: -x[1])]}

def vazamentos(fonte, meses=3, hoje=None):
    hoje = hoje or hoje_brt(); ini = meses_atras(meses, hoje).isoformat(); fim = (hoje.replace(day=1) - dt.timedelta(days=1)).isoformat()
    custo = fonte.visao('custo', ini, fim); out = {'periodo': [ini, fim]}
    taxas = {}
    for r in custo:
        if r['valor'] < 0 and (TAXA_RE.search(r['descricao'] or '') or TAXA_CAT.search(r['categoria'] or '')):
            k = norm(r['descricao']) or r['categoria']; taxas[k] = taxas.get(k, 0) - r['valor']
    out['tarifas_juros'] = [{'item': k, 'no_periodo': round(v, 2), 'anualizado': round(v * 12 / meses, 2)} for k, v in sorted(taxas.items(), key=lambda x: -x[1])]
    rec = recorrentes(fonte, 'custo', hoje)
    out['assinaturas'] = [{'item': r['descricao'], 'mensal': r['valor_medio'], 'anual': round(r['valor_medio'] * 12, 2), 'meses_vistos': r['meses']}
                          for r in rec if r['sentido'] == 'saida' and r['valor_medio'] < 600]
    out['aumentos'] = [{'item': r['descricao'], 'antes': r['mediana_anterior'], 'agora': r['ultimo'], 'alta_pct': round((r['ultimo'] / r['mediana_anterior'] - 1) * 100, 1)}
                       for r in rec if r['mediana_anterior'] and r['ultimo'] > r['mediana_anterior'] * 1.10]
    dup = []; ss = sorted([r for r in custo if r['valor'] < 0 and not (r['parcelas'] and r['parcelas'] > 1)], key=lambda r: (norm(r['descricao']), r['valor'], r['data']))
    for a, b in zip(ss, ss[1:]):
        if norm(a['descricao']) == norm(b['descricao']) and a['valor'] == b['valor'] and abs((D.fromisoformat(b['data'][:10]) - D.fromisoformat(a['data'][:10])).days) <= 2:
            dup.append({'item': a['descricao'], 'valor': -a['valor'], 'datas': [a['data'][:10], b['data'][:10]], 'contas': [a['account_id'][-4:], b['account_id'][-4:]]})
    out['possiveis_duplicidades'] = dup
    por_mes = {}
    for r in fonte.visao('custo', meses_atras(4, hoje).isoformat(), fim):
        cat = r['categoria'] or 'sem categoria'; por_mes.setdefault(cat, {}).setdefault(r['data'][:7], 0); por_mes[cat][r['data'][:7]] -= r['valor']
    ult = meses_atras(1, hoje).strftime('%Y-%m'); ant = [meses_atras(i, hoje).strftime('%Y-%m') for i in (2, 3, 4)]
    cres = []
    for cat, mm in por_mes.items():
        base = sum(mm.get(m, 0) for m in ant) / 3; v = mm.get(ult, 0)
        if base > 0 and v > base * 1.25 and v - base > 200: cres.append({'categoria': cat, 'mes': ult, 'valor': round(v, 2), 'media_3m': round(base, 2), 'alta_pct': round((v / base - 1) * 100, 1)})
    out['categorias_em_alta'] = sorted(cres, key=lambda x: -(x['valor'] - x['media_3m']))
    return out
