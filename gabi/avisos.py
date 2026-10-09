"""Produtor de avisos: grava em `aviso` o que o Ricardo precisa saber (rodada parada, conta atrasada, assinatura cancelada e cobrada,
o que vence hoje, serviço que falhou). Consome: db (rodada, compromisso, assinatura, lancamento, aviso). Só grava; entregar é outra etapa.

Um aviso por (tipo, chave) por dia de Brasília, aberto ou lido. O payload leva só nome, valor e datas: nunca CPF, documento, conta ou chave PIX.
Uso: python -m gabi.avisos            (timer de 15 min)    |    python -m gabi.avisos --falha gabi-brain-saldos.service  (OnFailure=)"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from gabi.db import conectar, migrar
from gabi.dinheiro.valor import formatar

BRT = ZoneInfo("America/Sao_Paulo")
HORAS_DADOS_ANTIGOS = 72


def _inicio_do_dia_utc(agora: dt.datetime) -> str:
    d = agora.astimezone(BRT).date()
    return dt.datetime(d.year, d.month, d.day, tzinfo=BRT).astimezone(dt.timezone.utc).isoformat()


def _novo(con, agora: dt.datetime, tipo: str, chave, payload: dict) -> int | None:
    ja = con.execute("select 1 from aviso where tipo=? and json_extract(payload,'$.chave')=? and criado_em>=?", (tipo, str(chave), _inicio_do_dia_utc(agora))).fetchone()
    if ja:
        return None
    return con.execute("insert into aviso(tipo, payload, criado_em) values (?,?,?)",
                       (tipo, json.dumps({"chave": str(chave), **payload}, ensure_ascii=False), agora.astimezone(dt.timezone.utc).isoformat())).lastrowid


def _valor(c) -> str | None:
    return None if c is None else formatar(c)


def gerar_avisos(con, agora: dt.datetime) -> list[int]:
    criados: list[int] = []
    hoje = agora.astimezone(BRT).date()

    def novo(*a):
        i = _novo(con, agora, *a)
        if i is not None:
            criados.append(i)

    ult = con.execute("select conferida, fim from rodada where fonte='open-finance' and fim is not null order by id desc limit 2").fetchall()
    if len(ult) == 2 and not any(r["conferida"] for r in ult):
        novo("rodada_parada", "duas_nao_conferidas", {"motivo": "as 2 últimas rodadas de extratos não foram conferidas"})
    elif ult:
        conf = con.execute("select max(fim) from rodada where fonte='open-finance' and conferida=1").fetchone()[0]
        if conf is None or agora - dt.datetime.fromisoformat(conf) > dt.timedelta(hours=HORAS_DADOS_ANTIGOS):
            novo("rodada_parada", "dados_antigos", {"motivo": f"nenhuma rodada conferida nas últimas {HORAS_DADOS_ANTIGOS} horas"})

    for c in con.execute("select id, nome, vencimento, valor_centavos from compromisso where estado='atrasado' and vencimento<? order by vencimento", (hoje.isoformat(),)):
        novo("conta_atrasada", c["id"], {"nome": c["nome"], "vencimento": c["vencimento"], "valor": _valor(c["valor_centavos"])})

    for a in con.execute("select id, estabelecimento, status_em from assinatura where status='cancelar' and status_em is not null"):
        d = con.execute("select data, -valor_centavos v from lancamento where natureza like '%custo%' and valor_centavos<0 and data>? "
                        "and (estabelecimento=? or descricao_original like ?) order by data desc limit 1", (a["status_em"][:10], a["estabelecimento"], f"{a['estabelecimento']}%")).fetchone()
        if d:
            novo("cobrada_apos_cancelar", a["id"], {"nome": a["estabelecimento"], "ultimo_debito": d["data"], "valor": formatar(d["v"])})

    itens = [{"nome": c["nome"], "valor": _valor(c["valor_centavos"]), "vencimento": c["vencimento"]} for c in con.execute(
        "select nome, vencimento, valor_centavos from compromisso where vencimento=? and estado in ('aberto','previsto') order by nome", (hoje.isoformat(),))]
    if itens:
        novo("vence_hoje", hoje.isoformat(), {"itens": itens})
    return criados


def registrar_servico_falhou(con, unidade: str, agora: dt.datetime) -> int | None:
    return _novo(con, agora, "servico_falhou", unidade, {"unidade": unidade})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", default=os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db"))
    ap.add_argument("--falha", default=None, help="nome da unidade systemd que falhou (usado por OnFailure=)")
    a = ap.parse_args(argv)
    con = conectar(Path(a.banco))
    migrar(con, Path(__file__).resolve().parent.parent / "migrations")
    agora = dt.datetime.now(dt.timezone.utc)
    if a.falha:
        print("servico_falhou:", a.falha, "->", registrar_servico_falhou(con, a.falha, agora))
    else:
        print("avisos criados:", gerar_avisos(con, agora))
    return 0


if __name__ == "__main__":
    sys.exit(main())
