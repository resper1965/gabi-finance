"""Quem gastou: o portador da conta (conta.usuarios), separado de "para quem" (de quem é o gasto).

O Open Finance não diz qual cartão físico (titular ou adicional) fez a compra, então:
- cartão com UM portador e conta corrente preenchem sozinhos (origem 'cartao'; conta corrente sem usuário = pessoa de papel 'titular');
- cartão com 2+ portadores fica a indicar, salvo "sempre assim" daquela loja NAQUELE cartão (gastador_regra, origem 'regra');
- a indicação do Ricardo (origem 'voce') nunca é sobrescrita; nada é deduzido do histórico nem do "para quem".
Consome: db (lancamento, conta, pessoa, gastador_regra). Não abre transação: quem chama decide.
"""
import datetime as dt
import json

ORIGEM_FIXA = "voce"


def _usuarios(texto) -> list[str]:
    try:
        lista = json.loads(texto) if texto else []
    except ValueError:
        return []
    return [u for u in lista if isinstance(u, str)] if isinstance(lista, list) else []


def _titular(con) -> str | None:
    r = con.execute("select id from pessoa where papel='titular' order by id limit 1").fetchone()
    return r[0] if r else None


def portadores(con, conta_id: int) -> list[str]:
    """Quem pode ter gastado nesta conta: os usuários cadastrados; conta corrente sem usuário = o titular."""
    c = con.execute("select tipo, usuarios from conta where id=?", (conta_id,)).fetchone()
    if c is None:
        return []
    lista = _usuarios(c["usuarios"])
    if not lista and c["tipo"] != "CREDIT":
        t = _titular(con)
        return [t] if t else []
    return lista


def _automatico(con, r, cache: dict) -> tuple[str | None, str | None]:
    if r["conta_id"] not in cache:
        cache[r["conta_id"]] = portadores(con, r["conta_id"])
    ps = cache[r["conta_id"]]
    if len(ps) == 1:
        return ps[0], "cartao"
    chave = r["estabelecimento"] or r["descricao_original"]
    if len(ps) > 1 and chave:
        regra = con.execute("select pessoa_id from gastador_regra where conta_id=? and estabelecimento=?", (r["conta_id"], chave)).fetchone()
        if regra and regra[0] in ps:
            return regra[0], "regra"
    return None, None


def preencher(con, ids=None) -> dict:
    """Recalcula o gastador automático (todos ou só `ids`); a indicação 'voce' fica. Devolve contagem por origem e 'a_indicar'
    (saída que é gasto, sem gastador)."""
    sql = "select id, conta_id, estabelecimento, descricao_original, valor_centavos, natureza, gastador_id, gastador_origem from lancamento"
    args: list = []
    if ids is not None:
        ids = list(ids)
        if not ids:
            return {}
        sql += f" where id in ({','.join('?' * len(ids))})"
        args = ids
    cache: dict = {}
    contagem = {"cartao": 0, "regra": 0, "voce": 0, "a_indicar": 0}
    for r in con.execute(sql, args).fetchall():
        if r["gastador_origem"] == ORIGEM_FIXA:
            novo = (r["gastador_id"], ORIGEM_FIXA)
        else:
            novo = _automatico(con, r, cache)
            if novo != (r["gastador_id"], r["gastador_origem"]):
                con.execute("update lancamento set gastador_id=?, gastador_origem=? where id=?", (*novo, r["id"]))
        if novo[1]:
            contagem[novo[1]] += 1
        elif r["valor_centavos"] < 0 and "custo" in (r["natureza"] or ""):
            contagem["a_indicar"] += 1
    return contagem


def indicar(con, ids: list[int], pessoa: str | None, regra: bool = False) -> None:
    """O Ricardo indica quem gastou (origem 'voce'); None tira a indicação e o automático volta. Tudo ou nada: pessoa que não é portadora de
    alguma das contas → ValueError('nao_portador: ...'); lançamento inexistente → LookupError. `regra`: "sempre assim" desta loja neste cartão."""
    linhas = []
    for i in ids:
        r = con.execute("select id, conta_id, estabelecimento, descricao_original from lancamento where id=?", (i,)).fetchone()
        if r is None:
            raise LookupError(f"lançamento {i} não existe")
        if pessoa is not None and pessoa not in portadores(con, r["conta_id"]):
            raise ValueError(f"nao_portador: {pessoa} não é portador da conta do lançamento {i}")
        linhas.append(r)
    for r in linhas:
        con.execute("update lancamento set gastador_id=?, gastador_origem=? where id=?",
                    (pessoa, ORIGEM_FIXA if pessoa else None, r["id"]))
    if pessoa is None:
        preencher(con, ids)
        return
    if regra:
        agora = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        contas = set()
        for r in linhas:
            chave = r["estabelecimento"] or r["descricao_original"]
            if chave:
                con.execute("insert into gastador_regra(conta_id, estabelecimento, pessoa_id, criado_em) values (?,?,?,?) "
                            "on conflict(conta_id, estabelecimento) do update set pessoa_id=excluded.pessoa_id, criado_em=excluded.criado_em",
                            (r["conta_id"], chave, pessoa, agora))
                contas.add(r["conta_id"])
        if contas:
            preencher(con, [x[0] for x in con.execute(f"select id from lancamento where conta_id in ({','.join('?' * len(contas))})", list(contas))])


if __name__ == "__main__":  # preenche o histórico todo: python -m gabi.dinheiro.gastador --banco /var/lib/gabi-finance/gabi.db
    import argparse
    from pathlib import Path

    from gabi.db import conectar, transacao

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--banco", type=Path, required=True)
    con = conectar(ap.parse_args().banco)
    with transacao(con):
        print(preencher(con))
    for r in con.execute("select coalesce(gastador_id, '(a indicar)'), count(*), round(sum(-valor_centavos)/100.0, 2) from lancamento "
                         "where valor_centavos<0 and natureza like '%custo%' group by 1 order by 3 desc"):
        print(tuple(r))
