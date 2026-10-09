"""Mede o aceite T1.14 da Fase 1 (7 dias seguidos conferidos, 90% classificado) e escreve docs/aceite-fase-1.md.
Uso: python -m tools.aceite [--banco CAMINHO] [--saida docs/aceite-fase-1.md]. Somente leitura. Consome: db (rodada, conferencia, lancamento)."""
import argparse
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

BRT = ZoneInfo("America/Sao_Paulo")
DIAS_ACEITE, META_CLASSIFICADO = 7, 0.90


def _dia_brt(iso: str) -> dt.date:
    return dt.datetime.fromisoformat(iso).astimezone(BRT).date()


def medir_fase1(con, hoje: dt.date) -> dict:
    por_dia: dict[dt.date, list] = {}
    ultima = None
    for r in con.execute("select id, fim from rodada where fonte='open-finance' and conferida=1 and fim is not null order by fim"):
        por_dia.setdefault(_dia_brt(r["fim"]), []).append(r["id"])
        ultima = r["fim"]
    fim_seq = hoje if hoje in por_dia else hoje - dt.timedelta(days=1)  # hoje ainda sem rodada não zera a sequência de ontem
    dias, d = 0, fim_seq
    ids_seq: list[int] = []
    while d in por_dia:
        dias += 1
        ids_seq += por_dia[d]
        d -= dt.timedelta(days=1)
    reprovado = 0
    if ids_seq:
        reprovado = con.execute(f"select count(*) from conferencia where tipo='saldo_final' and ok=0 and rodada_id in ({','.join('?' * len(ids_seq))})", ids_seq).fetchone()[0]
    total = con.execute("select count(*) from lancamento").fetchone()[0]
    bons = con.execute("select count(*) from lancamento where categoria_id is not null and para_quem_id is not null").fetchone()[0]
    return {"dias_seguidos_conferidos": dias, "saldo_final_reprovado": reprovado, "ultima_rodada_conferida": ultima,
            "classificado_pct": round(bons / total, 4) if total else 0.0, "lancamentos": total}


def escrever_relatorio(r: dict, caminho: Path, hoje: dt.date) -> None:
    ok = lambda c: "ATENDIDO" if c else "PENDENTE"
    linhas = [
        f"# Aceite da Fase 1 (T1.14), medido em {hoje.isoformat()}", "",
        f"- **{DIAS_ACEITE} dias seguidos** com rodada de extratos conferida (horário de Brasília): **{r['dias_seguidos_conferidos']}** dia(s), "
        f"última rodada conferida em {r['ultima_rodada_conferida'] or 'nunca'}: {ok(r['dias_seguidos_conferidos'] >= DIAS_ACEITE)}.",
        f"- Conferências `saldo_final` reprovadas nesses dias: **{r['saldo_final_reprovado']}**: {ok(r['saldo_final_reprovado'] == 0)}.",
        f"- **{META_CLASSIFICADO:.0%} classificado** (categoria e para quem), de {r['lancamentos']} lançamentos: **{r['classificado_pct']:.1%}**: {ok(r['classificado_pct'] >= META_CLASSIFICADO)}.", "",
        "Telas e MCP (T1.10, T1.12): verificar na tela, com o Ricardo.", ""]
    Path(caminho).write_text("\n".join(linhas), encoding="utf-8")


if __name__ == "__main__":
    from gabi.db import conectar
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", default="/var/lib/gabi-brain/gabi.db")
    ap.add_argument("--saida", default=None)
    a = ap.parse_args()
    hoje = dt.datetime.now(BRT).date()
    res = medir_fase1(conectar(a.banco), hoje)
    print(res)
    if a.saida:
        escrever_relatorio(res, Path(a.saida), hoje)
