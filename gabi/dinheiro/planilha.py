"""Validação das abas de compromissos (Compromissos, Parâmetros, Valores do mês). Portado do gabi-fin/planilha.py SEM alterar a lógica.

Só a parte pura: a leitura do Google Sheets (gog) e a semeadura ficaram para trás; o snapshot do staging e os Cadastros do painel
entram por aqui. Provado contra tests/golden/planilha.json. Consome: dinheiro.compromissos (_serie).
"""
import re
import unicodedata
from datetime import date, timedelta

from gabi.dinheiro.compromissos import _serie


ABAS = ("Compromissos", "Parâmetros", "Valores do mês")

COLUNAS_COMPROMISSOS = ("id", "nome", "extrato", "apelidos", "vencimento", "ajuste_dia_util", "valor_tipo",
                        "valor_padrao", "forma", "conta", "cartao", "documento", "pix", "ativo",
                        "valido_de", "valido_ate", "obs")

COLUNAS_VALORES = ("mes", "compromisso", "tipo", "valor", "vencimento", "data_pagamento", "origem", "registrado_em")

PADROES = {
    "horas_envio": {7, 15}, "horas_silenciosas": {23}, "janela_antes_dias": 10,
    "tolerancia_fixo": 0.01, "tolerancia_juros": 0.10, "tolerancia_valor": 1.00,
    "horas_conta_parada": 24, "dias_agenda": 7, "bancos_pj": set(),
    "telegram_destino": None, "prefixo_mensagem": "",
}

FORMAS = {"pix", "boleto", "debito_automatico", "fatura"}

_VENC = re.compile(r"^(\d+du|dia:\d{1,2})$")

_MES = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")

_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_SIM = {"sim", "s", "true", "1", ""}

_NAO = {"nao", "n", "false", "0"}

def _sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c))

def _norm(s):
    return " ".join(_sem_acento(s).upper().split())

def _txt(v):
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v).strip()

def numero_br(s):
    if isinstance(s, bool):
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s or "").replace("R$", "").replace(" ", "").replace(" ", "")
    if not t:
        return None
    if "," in t:
        if "." in t and t.rfind(".") > t.rfind(","):
            return None
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1:
        t = t.replace(".", "")
    elif re.fullmatch(r"-?\d+\.\d{3}", t):
        return None  # "2.500": milhar ou decimal? ambiguo
    if not re.fullmatch(r"-?\d+(\.\d+)?", t):
        return None
    return float(t)

def _data(v):
    """Data ISO a partir de texto AAAA-MM-DD ou serial do Sheets. None se vazio; ValueError se ilegivel."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (date(1899, 12, 30) + timedelta(days=int(v))).isoformat()
    t = _txt(v)
    if not t:
        return None
    if not _DATA.match(t):
        raise ValueError(t)
    date.fromisoformat(t)
    return t

def _mes(v):
    """AAAA-MM a partir de texto ou serial de data do Sheets. "" se vazio; ValueError se ilegivel."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (date(1899, 12, 30) + timedelta(days=int(v))).strftime("%Y-%m")
    t = _txt(v)
    if t and not _MES.match(t):
        raise ValueError(t)
    return t

def _tabela(linhas):
    """(indice por nome, [(numero_da_linha, celulas)]) ignorando linhas vazias."""
    if not linhas:
        return {}, []
    idx = {_sem_acento(_txt(c)).lower(): i for i, c in enumerate(linhas[0]) if _txt(c)}
    return idx, [(n, r) for n, r in enumerate(linhas[1:], start=2) if any(_txt(c) for c in r)]

def _cel(idx, r, nome):
    i = idx.get(nome)
    return r[i] if i is not None and i < len(r) else ""

def _meses_sobrepoe(a, b):
    de = max(a["valido_de"] or "", b["valido_de"] or "")
    ate = min(a["valido_ate"] or "9999-99", b["valido_ate"] or "9999-99")
    return de <= ate

def _linha(idx, n, r):
    """Devolve (Linha | None, motivo | None). None sem motivo = linha inativa, ignorada."""
    g = lambda c: _cel(idx, r, c)
    ativo = _sem_acento(_txt(g("ativo"))).lower()
    if ativo in _NAO:
        return None, None
    if ativo not in _SIM:
        return None, f"ativo '{_txt(g('ativo'))}' não reconhecido"
    id_ = _txt(g("id"))
    if not id_ or re.search(r"\s", id_):
        return None, f"id '{id_}' inválido"
    nome, extrato = _txt(g("nome")), _txt(g("extrato"))
    if not nome:
        return None, "nome vazio"
    if not extrato:
        return None, "extrato vazio"
    venc = "".join(_txt(g("vencimento")).lower().split())
    if not _VENC.match(venc) or (venc.endswith("du") and not 1 <= int(venc[:-2]) <= 23) \
            or (venc.startswith("dia:") and not 1 <= int(venc[4:]) <= 31):
        return None, f"vencimento '{_txt(g('vencimento'))}' não reconhecido"
    ajuste = _sem_acento(_txt(g("ajuste_dia_util"))).lower() or "adia"
    if ajuste not in ("adia", "antecipa"):
        return None, f"ajuste_dia_util '{_txt(g('ajuste_dia_util'))}' não reconhecido"
    tipo = _sem_acento(_txt(g("valor_tipo"))).lower() or "fixo"
    if tipo not in ("fixo", "variavel"):
        return None, f"valor_tipo '{_txt(g('valor_tipo'))}' não reconhecido"
    vp = None
    if _txt(g("valor_padrao")):
        vp = numero_br(g("valor_padrao"))
        if vp is None:
            return None, f"valor_padrao '{_txt(g('valor_padrao'))}' não é número"
    forma = _txt(g("forma")).lower()
    if forma and forma not in FORMAS:
        return None, f"forma '{_txt(g('forma'))}' não reconhecida"
    meses = {}
    for c in ("valido_de", "valido_ate"):
        try:
            t = _mes(g(c))
        except (ValueError, OverflowError):
            return None, f"{c} '{_txt(g(c))}' não é AAAA-MM"
        meses[c] = t or None
    if meses["valido_de"] and meses["valido_ate"] and meses["valido_de"] > meses["valido_ate"]:
        return None, "valido_de depois de valido_ate"
    return {
        "id": id_, "nome": nome, "extrato": extrato,
        "apelidos": [a.strip() for a in _txt(g("apelidos")).split(";") if a.strip()],
        "vencimento": venc, "ajuste_dia_util": ajuste, "valor_tipo": tipo, "valor_padrao": vp,
        "forma": forma, "conta": _txt(g("conta")), "cartao": _txt(g("cartao")),
        "documento": _txt(g("documento")), "pix": _txt(g("pix")), "ativo": True,
        "valido_de": meses["valido_de"], "valido_ate": meses["valido_ate"], "linha_planilha": n,
    }, None

def _horas(v):
    t = _txt(v)
    hs = {int(x) for x in re.split(r"[,;]", t) if x.strip()} if t else set()
    if not hs or any(not 0 <= h <= 23 for h in hs):
        raise ValueError(t)
    return hs

def _pct(v):
    t = _txt(v).replace(" ", "")
    if t.endswith("%"):
        n = numero_br(t[:-1])
        return None if n is None else n / 100
    return numero_br(v) if t else None

def _inteiro(v):
    n = numero_br(v)
    if n is None or n != int(n) or n <= 0:
        raise ValueError(_txt(v))
    return int(n)

def _num(v):
    n = numero_br(v)
    if n is None:
        raise ValueError(_txt(v))
    return n

def _porc(v):
    n = _pct(v)
    if n is None:
        raise ValueError(_txt(v))
    return n

_CONV = {
    "horas_envio": _horas, "horas_silenciosas": _horas, "janela_antes_dias": _inteiro,
    "tolerancia_fixo": _porc, "tolerancia_juros": _porc, "tolerancia_valor": _num,
    "horas_conta_parada": _inteiro, "dias_agenda": _inteiro,
    "bancos_pj": lambda v: {x.strip() for x in _txt(v).split(";") if x.strip()},
    "telegram_destino": lambda v: _txt(v) or None,
    "prefixo_mensagem": lambda v: "" if v is None else str(v),
}

def _params(linhas, invalidas):
    p = {k: (set(v) if isinstance(v, set) else v) for k, v in PADROES.items()}
    idx, rows = _tabela(linhas)
    for n, r in rows:
        chave = _txt(_cel(idx, r, "chave"))
        if chave not in _CONV:
            continue
        v = _cel(idx, r, "valor")
        if chave != "prefixo_mensagem" and not _txt(v):
            continue
        try:
            p[chave] = _CONV[chave](v)
        except (ValueError, TypeError):
            invalidas.append({"aba": ABAS[1], "linha": n, "motivo": f"{chave} '{_txt(v)}' não reconhecido"})
    return p

def _valores(linhas, conhecidos, invalidas):
    out = []
    idx, rows = _tabela(linhas)
    aba = ABAS[2]
    for n, r in rows:
        g = lambda c: _cel(idx, r, c)
        try:
            mes = _mes(g("mes"))
        except (ValueError, OverflowError):
            mes = ""
        comp = _txt(g("compromisso"))
        tipo = _sem_acento(_txt(g("tipo"))).lower()
        motivo = None
        valor = venc = pago = None
        if not _MES.match(mes):
            motivo = f"mes '{_txt(g('mes'))}' não é AAAA-MM"
        elif comp not in conhecidos:
            motivo = f"compromisso '{comp}' inexistente"
        elif tipo not in ("valor", "pago"):
            motivo = f"tipo '{_txt(g('tipo'))}' não reconhecido"
        else:
            if _txt(g("valor")):
                valor = numero_br(g("valor"))
                if valor is None:
                    motivo = f"valor '{_txt(g('valor'))}' não é número"
            elif tipo == "valor":
                motivo = "valor vazio"
            for campo in ("vencimento", "data_pagamento"):
                try:
                    d = _data(g(campo))
                except ValueError:
                    motivo = motivo or f"{campo} '{_txt(g(campo))}' não é AAAA-MM-DD"
                    d = None
                if campo == "vencimento":
                    venc = d
                else:
                    pago = d
        if motivo:
            invalidas.append({"aba": aba, "linha": n, "motivo": motivo})
        elif comp in conhecidos and conhecidos[comp]:
            out.append({"mes": mes, "compromisso": comp, "tipo": tipo, "valor": valor, "vencimento": venc,
                        "data_pagamento": pago, "origem": _txt(g("origem")), "linha_planilha": n})
    return out

def validar(bruto, hoje):
    invalidas, linhas, vistos = [], [], {}
    idx, rows = _tabela(bruto.get(ABAS[0], []))
    faltam = [c for c in ("id", "nome", "extrato", "vencimento") if c not in idx]
    if faltam and bruto.get(ABAS[0]):
        invalidas.append({"aba": ABAS[0], "linha": 1, "motivo": "coluna(s) ausente(s): " + ", ".join(faltam)})
        rows = []
    conhecidos = {}  # id -> True se a linha e ativa
    for n, r in rows:
        linha, motivo = _linha(idx, n, r)
        if linha is None and motivo is None:
            i = _txt(_cel(idx, r, "id"))
            conhecidos.setdefault(i, False)
            continue
        if linha is not None and linha["id"] in vistos:
            linha, motivo = None, f"id '{linha['id']}' repetido (linha {vistos[linha['id']]['linha_planilha']})"
        if linha is None:
            invalidas.append({"aba": ABAS[0], "linha": n, "motivo": motivo})
            continue
        vistos[linha["id"]] = linha
        linhas.append(linha)
    ruins = {}
    for i, a in enumerate(linhas):
        for b in linhas[i + 1:]:
            if _serie(a["id"]) == _serie(b["id"]) and _meses_sobrepoe(a, b):
                ruins.setdefault(a["linha_planilha"], b["linha_planilha"])
                ruins.setdefault(b["linha_planilha"], a["linha_planilha"])
    for n in sorted(ruins):
        invalidas.append({"aba": ABAS[0], "linha": n, "motivo": f"sobrepõe linha {ruins[n]}"})
    linhas = [x for x in linhas if x["linha_planilha"] not in ruins]
    invalidas.sort(key=lambda x: x["linha"])
    for x in linhas:
        conhecidos[x["id"]] = True
    pinv, vinv = [], []
    params = _params(bruto.get(ABAS[1], []), pinv)
    valores = _valores(bruto.get(ABAS[2], []), conhecidos, vinv)
    return {"linhas": linhas, "params": params, "valores": valores, "invalidas": invalidas + pinv + vinv,
            "lida_em": "", "da_copia": False, "erro_leitura": None}
