"""Carrega o staging (Plano 1) no banco, de forma idempotente e numa só transação. Consome: db, rodada."""
import datetime as dt
import hashlib
import json
import sqlite3
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from gabi.db import conectar, migrar
from gabi.dinheiro import planilha, repositorio
from gabi.rodada import registrar_rodada

MIGRACOES = Path(__file__).resolve().parent.parent / "migrations"
TABELAS = ("pessoa", "pet", "empresa", "compromisso_fixo", "matriz_acesso", "allowlist_vip", "compromisso",
           "agenda_estado", "agenda_eventos", "conciliacao", "fatura", "conta_estado", "memoria",
           "compromisso_linha", "valor_do_mes", "parametro")


def _centavos(v) -> int | None:
    if v is None or v == "":
        return None
    return int((Decimal(str(v)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _json(v) -> str | None:
    return v if isinstance(v, str) or v is None else json.dumps(v, ensure_ascii=False)


def _chave(*partes) -> str:
    return hashlib.sha1("|".join("" if p is None else str(p) for p in partes).encode("utf-8")).hexdigest()


def _upsert(con, tabela: str, pk: list[str], linha: dict) -> None:
    cols = list(linha)
    atualiza = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in pk)
    sql = (f"insert into {tabela}({', '.join(cols)}) values ({', '.join('?' * len(cols))}) "
           f"on conflict({', '.join(pk)}) do " + (f"update set {atualiza}" if atualiza else "nothing"))
    con.execute(sql, [linha[c] for c in cols])


def _ler(staging: Path) -> tuple[dict, dict, list[dict]]:
    familia = json.loads((staging / "familia.json").read_text(encoding="utf-8"))
    fin = json.loads((staging / "fin.json").read_text(encoding="utf-8"))
    memoria = [json.loads(l) for l in (staging / "memoria.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    return familia, fin, memoria


def _semear_cadastros(con, snapshot, hoje: dt.date, relatorio: dict | None) -> None:
    """Semeia os Cadastros de compromissos a partir do snapshot da planilha, SÓ se estiverem vazios: reimportar nunca
    sobrescreve o que o Ricardo editou no painel."""
    vazios = con.execute("select count(*) from compromisso_linha").fetchone()[0] == 0
    semear = bool(snapshot) and vazios
    if relatorio is not None:
        relatorio["cadastros_semeados"] = semear
        relatorio["cadastros_invalidas"] = []
    if not semear:
        return
    leitura = planilha.validar(snapshot["conteudo"], hoje)
    repositorio.gravar_leitura(con, leitura)
    if relatorio is not None:
        relatorio["cadastros_invalidas"] = leitura["invalidas"]


def importar_staging(con: sqlite3.Connection, staging: Path, relatorio: dict | None = None) -> dict[str, int]:
    staging = Path(staging)
    familia, fin, memoria = _ler(staging)  # falta de arquivo levanta ANTES de qualquer escrita
    con.execute("begin")
    try:
        for p in familia["pessoas"]:
            _upsert(con, "pessoa", ["id"], dict(id=p["id"], nome=p["nome"], papel=p.get("papel"),
                    telefone=p.get("telefone"), dados=_json(p), origem=p.get("origem")))
        for p in familia["pets"]:
            _upsert(con, "pet", ["id"], dict(id=p["id"], nome=p["nome"], especie=p.get("especie"),
                    dados=_json(p), origem=p.get("origem")))
        for e in familia["empresas"]:
            _upsert(con, "empresa", ["id"], dict(id=e["id"], nome=e["nome"], cnpj=e.get("cnpj"),
                    dados=_json(e), origem=e.get("origem")))
        for c in familia["compromissos_fixos"]:
            _upsert(con, "compromisso_fixo", ["id"], dict(
                id=c["id"], descricao=c["descricao"], pessoa_id=c.get("pessoa"), valor_texto=c.get("valor"),
                periodicidade=c.get("periodicidade"), dia_vencimento=c.get("dia_vencimento"),
                vigencia_ate=c.get("vigencia_ate"), dados=_json(c), origem=c.get("origem")))
        for l in familia["matriz_de_acesso"].get("linhas", []):
            _upsert(con, "matriz_acesso", ["informacao"], dict(
                informacao=l["informacao"], boss=l.get("boss"), familia_vip=l.get("familia_vip"),
                terceiros=l.get("terceiros")))
        for a in familia["allowlist_vip"]:
            _upsert(con, "allowlist_vip", ["chave"], dict(
                chave=_chave(a.get("pessoa"), a.get("rotulo"), a.get("telefone")),
                pessoa=a.get("pessoa"), rotulo=a.get("rotulo"), telefone=a.get("telefone")))
        for c in fin["compromissos"]:
            _upsert(con, "compromisso", ["id"], dict(
                id=c["id"], origem=c.get("origem"), linha_id=c.get("linha_id"), nome=c.get("nome"),
                vencimento=c.get("vencimento"), vencimento_util=c.get("vencimento_util"),
                valor_centavos=_centavos(c.get("valor")), valor_fonte=c.get("valor_fonte"), forma=c.get("forma"),
                account_id=c.get("account_id"), estado=c.get("estado"), motivo=c.get("motivo"),
                dados=_json(c.get("dados")), atualizado_em=c.get("atualizado_em")))
        for a in fin["agenda_estado"]:
            _upsert(con, "agenda_estado", ["chave"], dict(
                chave=_chave(a["item"], a.get("emissor"), a.get("vencimento")), item=a["item"],
                emissor=a.get("emissor"), vencimento=a.get("vencimento"), valor_centavos=_centavos(a.get("valor")),
                status=a.get("status"), visto_em=a.get("visto_em")))
        for a in fin["agenda_eventos"]:
            _upsert(con, "agenda_eventos", ["chave"], dict(
                chave=_chave(a.get("em"), a.get("item"), a.get("evento"), a.get("detalhe")), em=a.get("em"),
                item=a.get("item"), emissor=a.get("emissor"), vencimento=a.get("vencimento"),
                valor_centavos=_centavos(a.get("valor")), evento=a.get("evento"), detalhe=a.get("detalhe")))
        for c in fin["conciliacao"]:
            _upsert(con, "conciliacao", ["tx_id"], dict(
                tx_id=c["tx_id"], compromisso_id=c["compromisso_id"], metodo=c.get("metodo"),
                diferenca_centavos=_centavos(c.get("diferenca")), criado_em=c.get("criado_em")))
        for f in fin["faturas"]:
            _upsert(con, "fatura", ["id"], dict(
                id=f["id"], account_id=f.get("account_id"), vencimento=f.get("vencimento"),
                total_centavos=_centavos(f.get("total")), minimo_centavos=_centavos(f.get("minimo"))))
        for c in fin["contas_estado"]:
            _upsert(con, "conta_estado", ["account_id"], dict(
                account_id=c["account_id"], banco=c.get("banco"), nome=c.get("nome"), tipo=c.get("tipo"),
                pj=c.get("pj"), ult_tx_real=c.get("ult_tx_real"), ult_sync_ok=c.get("ult_sync_ok"),
                status_conexao=c.get("status_conexao"), saldo_centavos=_centavos(c.get("saldo")),
                atualizado_em=c.get("atualizado_em")))
        for m in memoria:
            _upsert(con, "memoria", ["chave"], dict(
                chave=_chave(m["tipo"], m.get("path"), m.get("bloco"), m.get("sessao"), m.get("mensagem")),
                tipo=m["tipo"], path=m.get("path"), sessao=m.get("sessao"), papel=m.get("papel"),
                timestamp=m.get("timestamp"), texto=m["texto"], origem=m.get("origem")))
        con.execute("commit")
    except BaseException:
        con.execute("rollback")
        raise
    _semear_cadastros(con, fin.get("planilha"), dt.date.today(), relatorio)
    return {t: con.execute(f"select count(*) from {t}").fetchone()[0] for t in TABELAS}


def main(banco: Path, staging: Path) -> int:
    con = conectar(banco)
    migrar(con, MIGRACOES)
    with registrar_rodada(con, "importacao-staging") as r:
        antes = {t: con.execute(f"select count(*) from {t}").fetchone()[0] for t in TABELAS}
        rel: dict = {}
        depois = importar_staging(con, staging, relatorio=rel)
        r.lidos = sum(depois.values())
        r.novos = sum(depois[t] - antes[t] for t in TABELAS)
    print("importado: " + ", ".join(f"{t}={n}" for t, n in depois.items()))
    if rel.get("cadastros_semeados"):
        print(f"cadastros de compromissos semeados; linhas rejeitadas pela validação: {len(rel['cadastros_invalidas'])}")
        for i in rel["cadastros_invalidas"]:
            print(f"  - {i['aba']} linha {i['linha']}: {i['motivo']}")
    elif rel.get("cadastros_semeados") is False:
        print("cadastros de compromissos já existem (ou o staging não traz a planilha): nada foi sobrescrito")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", required=True)
    ap.add_argument("--staging", required=True)
    a = ap.parse_args()
    sys.exit(main(Path(a.banco), Path(a.staging)))
