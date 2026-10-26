"""Despesas (fixas e avulsas): regras de criar, listar, mudar, dispensar, encerrar e excluir sobre `compromisso_linha`. Chamado pela API, pelo painel e pelo MCP.

`ValueError` = dado inválido; `LookupError` = série não encontrada. Toda escrita grava `decisao` e recalcula A Pagar.
Consome: dinheiro.{planilha,compromissos,contas_pagar,repositorio,valor}.
"""
import datetime as dt
import json
import re
import sqlite3
import unicodedata
from typing import Callable

from gabi.dinheiro import contas_pagar as cp, planilha, repositorio
from gabi.dinheiro.compromissos import _serie
from gabi.dinheiro.valor import formatar, para_centavos
from gabi.hoje import BRT

CAMPOS = {"nome", "extrato", "apelidos", "vencimento", "ajuste_dia_util", "valor_tipo", "valor_padrao", "forma", "conta", "cartao", "pix"}


def _slug(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "item"


def _id_unico(con, tabela: str, base: str) -> str:
    cand, n = base, 2
    while con.execute(f"select 1 from {tabela} where id=?", (cand,)).fetchone():
        cand, n = f"{base}-{n}", n + 1
    return cand


def _id_de_serie_nova(con, base: str, sufixo: str = "") -> str:
    """Primeiro `base`, `base-2`, `base-3`... cuja SÉRIE (`_serie`) não tem nenhuma linha no cadastro (nem excluída): cada despesa nova é série própria."""
    usadas = {_serie(r[0]) for r in con.execute("select id from compromisso_linha")}
    cand, n = base, 2
    while _serie(f"{cand}{sufixo}") in usadas:
        cand, n = f"{base}-{n}", n + 1
    return f"{cand}{sufixo}"


def validar_linha(con, d: dict, proprio: str | None) -> dict:
    """Passa pela MESMA validação da planilha; devolve a linha normalizada ou levanta ValueError com o motivo."""
    cols = planilha.COLUNAS_COMPROMISSOS
    apelidos = d.get("apelidos") or []
    if not isinstance(apelidos, list) or not all(isinstance(a, str) for a in apelidos):
        raise ValueError("apelidos deve ser uma lista de textos")
    v = {**d, "apelidos": "; ".join(apelidos), "ativo": "sim"}  # a validação das regras vale mesmo para linha desativada
    celulas = ["" if v.get(c) is None else v.get(c) for c in cols]
    idx = {c: i for i, c in enumerate(cols)}
    linha, motivo = planilha._linha(idx, 2, celulas)
    if linha is None:
        raise ValueError(motivo or "linha inválida")
    for o in con.execute("select id, valido_de, valido_ate from compromisso_linha where excluido_em is null and id<>?", (proprio or "",)):
        if _serie(o["id"]) == _serie(linha["id"]) and planilha._meses_sobrepoe(linha, {"valido_de": o["valido_de"], "valido_ate": o["valido_ate"]}):
            raise ValueError(f"os meses de validade se sobrepõem aos de {o['id']}")
    return linha


def gravar_linha(con, linha: dict, ativo: bool, obs, inserir: bool, tipo: str = "fixa") -> None:
    args = (linha["nome"], linha["extrato"], json.dumps(linha["apelidos"], ensure_ascii=False), linha["vencimento"], linha["ajuste_dia_util"],
            linha["valor_tipo"], None if linha["valor_padrao"] is None else para_centavos(round(linha["valor_padrao"], 2)), linha["forma"],
            linha["conta"], linha["cartao"], linha["documento"], linha["pix"], int(ativo), linha["valido_de"], linha["valido_ate"], obs)
    if inserir:
        con.execute("insert into compromisso_linha(id, nome, extrato, apelidos, vencimento, ajuste_dia_util, valor_tipo, valor_padrao_centavos, forma, conta, cartao, "
                    "documento, pix, ativo, valido_de, valido_ate, obs, tipo) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (linha["id"], *args, tipo))
    else:
        con.execute("update compromisso_linha set nome=?, extrato=?, apelidos=?, vencimento=?, ajuste_dia_util=?, valor_tipo=?, valor_padrao_centavos=?, forma=?, "
                    "conta=?, cartao=?, documento=?, pix=?, ativo=?, valido_de=?, valido_ate=?, obs=? where id=?", (*args, linha["id"]))


def _auditar(con, agora: dt.datetime, quem: str, origem: str, o_que: str) -> None:
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?,?)", (agora.astimezone(dt.timezone.utc).isoformat(), quem, o_que, origem))


def _campos_validos(campos: dict) -> dict:
    extra = set(campos) - CAMPOS
    if extra:
        raise ValueError(f"campos desconhecidos: {sorted(extra)}")
    nome = campos.get("nome")
    if not isinstance(nome, str) or not nome.strip():
        raise ValueError("nome é obrigatório")
    return {**campos, "nome": nome.strip()}


def _gravar_nova(con, agora, quem, origem, dado: dict, tipo: str, hoje: dt.date) -> dict:
    linha = validar_linha(con, dado, None)
    con.execute("begin")
    try:
        gravar_linha(con, linha, True, None, True, tipo)
        _auditar(con, agora, quem, origem, f"despesa {_serie(linha['id'])} criada ({tipo})")
        con.execute("commit")
    except Exception:
        con.execute("rollback")
        raise
    cp.atualizar_compromissos(con, hoje, agora)
    return _item(con, hoje, _serie(linha["id"]))


def criar_fixa(con, agora: dt.datetime, quem: str, origem: str, campos: dict) -> dict:
    hoje = agora.astimezone(BRT).date()
    c = _campos_validos(campos)
    dado = {**c, "id": _id_de_serie_nova(con, _slug(c["nome"])), "extrato": c.get("extrato") or c["nome"], "valido_de": hoje.strftime("%Y-%m")}
    return _gravar_nova(con, agora, quem, origem, dado, "fixa", hoje)


def criar_avulsa(con, agora: dt.datetime, quem: str, origem: str, campos: dict, data: str) -> dict:
    hoje = agora.astimezone(BRT).date()
    try:
        d = dt.date.fromisoformat(data)
    except (TypeError, ValueError):
        raise ValueError(f"data '{data}' não é AAAA-MM-DD")
    c = _campos_validos(campos)
    mes = data[:7]
    dado = {**c, "id": _id_de_serie_nova(con, _slug(c["nome"]), "-" + mes.replace("-", "")), "extrato": c.get("extrato") or c["nome"], "vencimento": f"dia:{d.day}",
            "valido_de": mes, "valido_ate": mes}
    return _gravar_nova(con, agora, quem, origem, dado, "avulsa", hoje)


def serie_de(con, id_: str) -> list[sqlite3.Row]:
    """Versões não excluídas da série, da mais antiga à mais nova (`valido_de` vazio = desde sempre)."""
    linhas = [r for r in con.execute("select * from compromisso_linha where excluido_em is null") if _serie(r["id"]) == _serie(id_)]
    if not linhas:
        raise LookupError(f"despesa {id_} não existe")
    return sorted(linhas, key=lambda r: (r["valido_de"] or "", r["id"]))


def _item(con, hoje: dt.date, serie: str) -> dict:
    vs = serie_de(con, serie)
    u = vs[-1]
    mes_hoje = hoje.strftime("%Y-%m")
    encerrada = bool(u["valido_ate"]) and u["valido_ate"] < mes_hoje
    ids = [v["id"] for v in vs]
    prox = con.execute(f"select min(vencimento_util) from compromisso where origem='planilha' and estado<>'pago' and vencimento_util>=? "
                       f"and linha_id in ({','.join('?' * len(ids))})", (hoje.isoformat(), *ids)).fetchone()[0]
    return {"id": _serie(serie), "versao_id": u["id"], "nome": u["nome"], "tipo": u["tipo"],
            "valor": None if u["valor_padrao_centavos"] is None else formatar(u["valor_padrao_centavos"]),
            "vencimento": u["vencimento"], "forma": u["forma"], "valido_de": u["valido_de"], "valido_ate": u["valido_ate"],
            "situacao": "encerrada" if encerrada else "ativa", "proximo_vencimento": None if encerrada else prox,
            "versoes": [{"id": v["id"], "valido_de": v["valido_de"], "valido_ate": v["valido_ate"],
                         "valor": None if v["valor_padrao_centavos"] is None else formatar(v["valor_padrao_centavos"]), "vencimento": v["vencimento"]} for v in vs]}


def listar(con, hoje: dt.date, tipo: str | None = None, situacao: str | None = None) -> list[dict]:
    series = {}
    for r in con.execute("select id from compromisso_linha where excluido_em is null order by coalesce(linha_planilha, 1000000 + rowid), id"):
        series.setdefault(_serie(r["id"]), None)
    itens = [_item(con, hoje, s) for s in series]
    return [i for i in itens if (tipo is None or i["tipo"] == tipo) and (situacao is None or i["situacao"] == situacao)]


# ---------------- Task 3: mudar, mês, dispensar, encerrar, excluir ----------------
_MES = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


def _mes_valido(m: str, campo: str = "mês") -> str:
    if not isinstance(m, str) or not _MES.fullmatch(m):
        raise ValueError(f"{campo} '{m}' não é AAAA-MM")
    return m


def _somar_mes(ym: str, n: int) -> str:
    a, m = divmod(int(ym[:4]) * 12 + int(ym[5:7]) - 1 + n, 12)
    return f"{a}-{m + 1:02d}"


def _todas_as_versoes(con, serie: str) -> list[str]:
    """Ids de todas as versões da série, inclusive as excluídas (para achar pagamento e ocorrências)."""
    return [r[0] for r in con.execute("select id from compromisso_linha") if _serie(r[0]) == _serie(serie)]


def mes_pago(con, serie: str, ym: str) -> bool:
    return any(repositorio.ocorrencia_paga(con, v, ym) for v in _todas_as_versoes(con, serie))


def mes_inicial(con, serie: str, hoje: dt.date) -> str:
    """Primeiro mês que uma mudança alcança: o de hoje se ainda não foi pago; senão o seguinte."""
    m = hoje.strftime("%Y-%m")
    return _somar_mes(m, 1) if mes_pago(con, serie, m) else m


def _cobre(v, m: str) -> bool:
    return (v["valido_de"] or "") <= m <= (v["valido_ate"] or "9999-99")


def _vigente(con, id_: str, m: str):
    """Versão não excluída da série que vale em `m`, ou None."""
    return next((v for v in serie_de(con, id_) if _cobre(v, m)), None)


def _meses_pagos(con, ids: list[str]) -> set[str]:
    """Meses em que alguma dessas versões teve ocorrência paga ou conciliada."""
    marca = ",".join("?" * len(ids))
    cand = {tuple(r) for r in con.execute(f"select linha_id, substr(id, -7) from compromisso where origem='planilha' and linha_id in ({marca})", ids)}
    cand |= {tuple(r) for r in con.execute(f"select compromisso, mes from valor_do_mes where tipo='pago' and compromisso in ({marca})", ids)}
    for (cid,) in con.execute("select compromisso_id from conciliacao where tx_id not like 'manual:%'"):
        linha, _, ym = str(cid).rpartition(":")
        if linha in ids:
            cand.add((linha, ym))
    return {ym for linha, ym in cand if repositorio.ocorrencia_paga(con, linha, ym)}


def _teve_pagamento(con, ids: list[str]) -> bool:
    return bool(_meses_pagos(con, ids))


def limpar_nao_pagas(con, serie: str, meses: Callable[[str], bool]) -> int:
    """Apaga de A Pagar as ocorrências da série (`origem='planilha'`, qualquer versão) cujo mês satisfaz `meses` e que não
    foram pagas nem conciliadas (`repositorio.ocorrencia_paga`), em qualquer mês (não só a janela), e o vínculo `manual:`
    órfão delas. Não abre transação: roda dentro da de quem chama. Devolve quantas apagou."""
    ids = _todas_as_versoes(con, serie)
    n = 0
    for cid, linha in con.execute(f"select id, linha_id from compromisso where origem='planilha' and linha_id in ({','.join('?' * len(ids))})", ids).fetchall():
        ym = cid[-7:]
        if meses(ym) and not repositorio.ocorrencia_paga(con, linha, ym):
            con.execute("delete from compromisso where id=?", (cid,))
            con.execute("delete from conciliacao where tx_id=?", (f"manual:{cid}",))
            n += 1
    return n


def _escrever(con, agora: dt.datetime, quem: str, origem: str, o_que: str, faz: Callable[[], None]) -> None:
    """`faz` + decisão numa transação só; depois recalcula A Pagar."""
    con.execute("begin")
    try:
        faz()
        _auditar(con, agora, quem, origem, o_que)
        con.execute("commit")
    except Exception:
        con.execute("rollback")
        raise
    cp.atualizar_compromissos(con, agora.astimezone(BRT).date(), agora)


def _como_dado(v) -> dict:
    """Linha do cadastro no formato de entrada de `validar_linha`."""
    return {"id": v["id"], "nome": v["nome"], "extrato": v["extrato"], "apelidos": json.loads(v["apelidos"] or "[]"), "vencimento": v["vencimento"],
            "ajuste_dia_util": v["ajuste_dia_util"], "valor_tipo": v["valor_tipo"],
            "valor_padrao": None if v["valor_padrao_centavos"] is None else formatar(v["valor_padrao_centavos"]),
            "forma": v["forma"], "conta": v["conta"], "cartao": v["cartao"], "documento": v["documento"], "pix": v["pix"],
            "valido_de": v["valido_de"], "valido_ate": v["valido_ate"]}


def mudar(con, agora: dt.datetime, quem: str, origem: str, id_: str, campos: dict, a_partir: str | None = None) -> dict:
    """Muda a despesa daqui em diante. `m` = `a_partir` (nunca mês passado) ou `mes_inicial`. A versão que vale em `m` é
    editada se começa em `m`; senão termina no mês anterior e nasce `serie-AAAAMM` com os campos novos. Série que só
    começa depois de `m` (futura, sem pagamento) é editada na própria linha."""
    hoje = agora.astimezone(BRT).date()
    extra = set(campos) - CAMPOS
    if extra:
        raise ValueError(f"campos desconhecidos: {sorted(extra)}")
    if "nome" in campos and (not isinstance(campos["nome"], str) or not campos["nome"].strip()):
        raise ValueError("nome é obrigatório")
    serie = _serie(id_)
    vs = serie_de(con, serie)
    if a_partir is not None:
        m = _mes_valido(a_partir, "a_partir")
        if m < hoje.strftime("%Y-%m"):
            raise ValueError(f"meses passados não mudam (a_partir {m})")
    else:
        m = mes_inicial(con, serie, hoje)
    v = _vigente(con, serie, m)
    futura = None if v else next((x for x in vs if (x["valido_de"] or "") > m), None)
    if v is None and futura is None:
        raise ValueError(f"despesa {serie} não vale em {m}")
    if futura is not None and _teve_pagamento(con, [futura["id"]]):
        raise ValueError(f"despesa {serie} não vale em {m}")
    alvo = v or futura
    novo = {**_como_dado(alvo), **campos}
    if "nome" in campos:
        novo["nome"] = campos["nome"].strip()
    nova_versao = alvo is v and v["valido_de"] != m
    novo_id = f"{serie}-{m.replace('-', '')}"

    def faz():
        if not nova_versao:
            linha = validar_linha(con, novo, alvo["id"])
            gravar_linha(con, linha, bool(alvo["ativo"]), alvo["obs"], False)
            return
        con.execute("update compromisso_linha set valido_ate=? where id=?", (_somar_mes(m, -1), v["id"]))
        linha = validar_linha(con, {**novo, "id": novo_id, "valido_de": m, "valido_ate": v["valido_ate"]}, novo_id)
        existe = con.execute("select 1 from compromisso_linha where id=?", (novo_id,)).fetchone()  # versão excluída de antes: volta
        gravar_linha(con, linha, bool(v["ativo"]), v["obs"], not existe, v["tipo"])
        if existe:
            con.execute("update compromisso_linha set excluido_em=null, tipo=? where id=?", (v["tipo"], novo_id))
        # o que foi decidido para um mês (valor/data ou dispensa) acompanha o mês para a versão nova; a baixa `pago` fica
        con.execute("update valor_do_mes set compromisso=? where compromisso=? and mes>=? and tipo in ('valor','dispensado')", (novo_id, v["id"], m))

    mudou = ", ".join(sorted(campos)) or "nada"
    _escrever(con, agora, quem, origem, f"despesa {serie} mudada a partir de {m}" + (f" (nova versão {novo_id})" if nova_versao else "") + f": {mudou}", faz)
    return {**_item(con, hoje, serie), "a_partir": m, "nova_versao": nova_versao}


def _versao_do_mes(con, id_: str, mes: str):
    v = _vigente(con, id_, _mes_valido(mes))
    if v is None:
        raise ValueError(f"despesa {_serie(id_)} não vale em {mes}")
    return v


def mudar_mes(con, agora: dt.datetime, quem: str, origem: str, id_: str, mes: str, valor: str | None = None, vencimento: str | None = None) -> dict:
    """Valor e/ou data de um mês só (`valor_do_mes` `valor` da versão que vale no mês); o que não vier fica como está.
    Mês já pago não muda."""
    if valor is None and vencimento is None:
        raise ValueError("informe o valor ou o vencimento do mês")
    v = _versao_do_mes(con, id_, mes)
    if mes_pago(con, _serie(id_), mes):
        raise ValueError("mês já pago")
    centavos = None
    if valor is not None:
        centavos = para_centavos(valor)
        if centavos is None or centavos < 0:
            raise ValueError(f"valor '{valor}' inválido")
    if vencimento is not None:
        try:
            dt.date.fromisoformat(vencimento)
        except (TypeError, ValueError):
            raise ValueError(f"vencimento '{vencimento}' não é AAAA-MM-DD")

    def faz():
        ja = con.execute("select id from valor_do_mes where compromisso=? and mes=? and tipo='valor'", (v["id"], mes)).fetchall()
        if not ja:
            con.execute("insert into valor_do_mes(mes, compromisso, tipo, valor_centavos, vencimento, origem) values (?,?,'valor',?,?,?)",
                        (mes, v["id"], centavos, vencimento, origem))
        for (vid,) in ja:
            if valor is not None:
                con.execute("update valor_do_mes set valor_centavos=? where id=?", (centavos, vid))
            if vencimento is not None:
                con.execute("update valor_do_mes set vencimento=? where id=?", (vencimento, vid))

    o_que = " e ".join(x for x in (valor is not None and f"valor {formatar(centavos)}", vencimento is not None and f"vencimento {vencimento}") if x)
    _escrever(con, agora, quem, origem, f"despesa {_serie(id_)} em {mes}: {o_que}", faz)
    return {**_item(con, agora.astimezone(BRT).date(), _serie(id_)), "mes": mes}


def dispensar_mes(con, agora: dt.datetime, quem: str, origem: str, id_: str, mes: str) -> dict:
    """Este mês não tem a despesa: grava `valor_do_mes` `dispensado` e tira a ocorrência não paga de A Pagar."""
    v = _versao_do_mes(con, id_, mes)
    serie = _serie(id_)
    if mes_pago(con, serie, mes):
        raise ValueError("mês já pago")

    def faz():
        if not con.execute("select 1 from valor_do_mes where compromisso=? and mes=? and tipo='dispensado'", (v["id"], mes)).fetchone():
            con.execute("insert into valor_do_mes(mes, compromisso, tipo, origem) values (?,?,'dispensado',?)", (mes, v["id"], origem))
        limpar_nao_pagas(con, serie, lambda ym: ym == mes)

    _escrever(con, agora, quem, origem, f"despesa {serie} dispensada em {mes}", faz)
    return {**_item(con, agora.astimezone(BRT).date(), serie), "mes": mes, "dispensado": True}


def desfazer_dispensa(con, agora: dt.datetime, quem: str, origem: str, id_: str, mes: str) -> dict:
    serie = _serie(id_)
    ids = _todas_as_versoes(con, serie)
    _mes_valido(mes)
    if not con.execute(f"select 1 from valor_do_mes where tipo='dispensado' and mes=? and compromisso in ({','.join('?' * len(ids))})", (mes, *ids)).fetchone():
        raise LookupError(f"despesa {serie} não está dispensada em {mes}")

    def faz():
        con.execute(f"delete from valor_do_mes where tipo='dispensado' and mes=? and compromisso in ({','.join('?' * len(ids))})", (mes, *ids))

    _escrever(con, agora, quem, origem, f"despesa {serie} volta em {mes} (dispensa desfeita)", faz)
    return {**_item(con, agora.astimezone(BRT).date(), serie), "mes": mes, "dispensado": False}


def encerrar(con, agora: dt.datetime, quem: str, origem: str, id_: str, ultimo_mes: str | None = None) -> dict:
    """Último mês = `ultimo_mes` ou o anterior a `mes_inicial` (nunca antes do último mês pago, mesmo pago adiantado).
    `ultimo_mes` antes de um mês pago é recusado. Versões que começariam depois viram excluídas (nunca
    `valido_ate` < `valido_de`); a que cobre o último mês termina nele. O que não foi pago depois sai de A Pagar."""
    hoje = agora.astimezone(BRT).date()
    serie = _serie(id_)
    vs = serie_de(con, serie)
    pagos = _meses_pagos(con, _todas_as_versoes(con, serie))
    if ultimo_mes is not None:
        u = _mes_valido(ultimo_mes, "ultimo_mes")
        depois = sorted(m for m in pagos if m > u)
        if depois:
            raise ValueError(f"já há pagamento em {depois[0]}; o último mês não pode ser antes dele")
    else:
        u = max([_somar_mes(mes_inicial(con, serie, hoje), -1), *pagos])
    quando = agora.astimezone(dt.timezone.utc).isoformat()

    def faz():
        for v in vs:
            if (v["valido_de"] or "") > u:
                con.execute("update compromisso_linha set excluido_em=? where id=?", (quando, v["id"]))
            elif (v["valido_ate"] or "9999-99") > u:
                con.execute("update compromisso_linha set valido_ate=? where id=?", (u, v["id"]))
        limpar_nao_pagas(con, serie, lambda ym: ym > u)

    _escrever(con, agora, quem, origem, f"despesa {serie} encerrada; último mês {u}", faz)
    return {"id": serie, "ultimo_mes": u}


def excluir(con, agora: dt.datetime, quem: str, origem: str, id_: str) -> dict:
    """Cadastro errado: some de vez se nunca teve ocorrência paga nem conciliada; senão é encerrada."""
    serie = _serie(id_)
    vs = serie_de(con, serie)
    if _teve_pagamento(con, _todas_as_versoes(con, serie)):
        return {"id": serie, "excluida": False, "encerrada": True, "ultimo_mes": encerrar(con, agora, quem, origem, serie)["ultimo_mes"]}
    quando = agora.astimezone(dt.timezone.utc).isoformat()

    def faz():
        for v in vs:
            con.execute("update compromisso_linha set excluido_em=? where id=?", (quando, v["id"]))
        limpar_nao_pagas(con, serie, lambda ym: True)

    _escrever(con, agora, quem, origem, f"despesa {serie} excluída", faz)
    return {"id": serie, "excluida": True, "encerrada": False}
