"""Programa do correio (timer de 15 min): sincroniza as fontes liberadas, confere quem o dono já respondeu, classifica, move o obviamente inútil para a
lixeira (só em conta com a lixeira ligada), alerta emergências, resume o dia e apaga trechos antigos e poda mensagens velhas (`email.retencao_msg_dias`). Imprime SÓ contagens, nunca remetente, assunto ou trecho.
O Gmail, o Graph da ness e o modelo chegam pela ponte do serviço de fontes (GABI_FONTES_SOCKET); este processo não tem rede nem segredo.
Sai 0 se ao menos uma fonte sincronizou ou não há fonte liberada; 1 só se todas falham e alguma por motivo diferente de "conta não autorizada".
Uso: python -m gabi.correio"""
import datetime as dt
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from gabi.correio.processar import processar, purgar_mensagens, purgar_trechos, resumo_do_dia, retencao_msg_dias
from gabi.correio.sincronizar import atualizar_respondidos, respondidos_prontos, sincronizar
from gabi.db import conectar, migrar
from gabi.dinheiro.modelo import orcamento_do_banco
from gabi.correio.modelo import ModeloComCusto, cliente_da_ponte
from gabi.rodada import registrar_rodada

BRT = ZoneInfo("America/Sao_Paulo")
DIAS_RESPONDIDOS = 365
_AUTO = object()


def _retencao_dias(con) -> int:
    r = con.execute("select valor from parametro where chave='email.retencao_dias'").fetchone()
    try:
        v = json.loads(r[0]) if r else 30
    except (ValueError, TypeError):
        return 30
    return v if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 365 else 30


def _conferir_respondidos(con, ponte, resultados: dict, agora: str) -> None:
    """Na primeira leitura da conta e a cada recarga completa (e enquanto ainda não conferiu), refaz a lista de quem o dono respondeu.
    Falhou: a conta segue sem a marca de conferência e NADA é movido para a lixeira nela (a proteção 'já respondi' não existiria)."""
    for fid, r in resultados.items():
        if "erro" in r or not (r.get("recarga") or not respondidos_prontos(con, fid)):
            continue
        conta = con.execute("select conta from email_fonte where id=?", (fid,)).fetchone()["conta"]
        try:
            atualizar_respondidos(con, fid, ponte.enviados_recentes(conta, DIAS_RESPONDIDOS), agora)
        except Exception:  # noqa: BLE001 - ponte fora do ar: tenta de novo na próxima rodada
            continue


def _contas_graph(banco: Path) -> list[str]:
    """Contas cadastradas com provedor `graph`: é o cadastro (e não a entrada livre) que decide que a conta vai ao Graph."""
    con = conectar(banco)
    try:
        migrar(con, Path(__file__).resolve().parent.parent.parent / "migrations")
        return [r["conta"] for r in con.execute("select conta from email_fonte where provedor='graph'")]
    finally:
        con.close()


def main(banco: Path | None = None, *, listar=None, ponte=None, cliente=_AUTO, agora: dt.datetime | None = None) -> int:
    banco = Path(banco or os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db"))
    sock = os.environ.get("GABI_FONTES_SOCKET")
    if listar is None or ponte is None:
        if not sock:
            print("ERRO: GABI_FONTES_SOCKET não configurado", file=sys.stderr)
            return 2
        from gabi.fontes.roteador import email_pela_ponte
        p = email_pela_ponte(sock, _contas_graph(banco))
        if p is None:
            print("ERRO: nem o e-mail do Google nem o Graph da ness estão configurados no serviço de fontes", file=sys.stderr)
            return 2
        ponte = ponte or p
        listar = listar or p.listar_novos
    agora = agora or dt.datetime.now(dt.timezone.utc)
    agora_s = agora.astimezone(dt.timezone.utc).isoformat()
    if cliente is _AUTO:
        cliente = cliente_da_ponte(sock)
        if cliente is not None:
            cliente = ModeloComCusto(cliente, banco, tarefa="email")
    con = conectar(banco)
    migrar(con, Path(__file__).resolve().parent.parent.parent / "migrations")
    try:
        with registrar_rodada(con, "correio") as rod:  # alimenta o frescor do envelope; rodada ok sem fonte liberada
            r = sincronizar(con, listar, agora_s)
            _conferir_respondidos(con, ponte, r, agora_s)
            c = processar(con, cliente, orcamento_do_banco(con, agora.astimezone(BRT).date()), ponte, agora_s)
            resumo_do_dia(con, agora)
            purgados = purgar_trechos(con, agora_s, _retencao_dias(con))
            podadas = purgar_mensagens(con, agora_s, retencao_msg_dias(con))
            rod.lidos = sum(v.get("lidos", 0) for v in r.values())
            rod.novos = sum(v.get("novos", 0) for v in r.values())
            falhas = sum(1 for v in r.values() if "erro" in v)
            if r and falhas == len(r):  # nenhuma fonte lida: não vale como "dados frescos"
                rod.falha = f"todas as {len(r)} fonte(s) falharam"
            elif falhas:
                rod.aviso = f"{falhas} fonte(s) com falha"
        contas = {x["id"]: x["conta"] for x in con.execute("select id, conta from email_fonte")}
    finally:
        con.close()
        if isinstance(cliente, ModeloComCusto):
            cliente.fechar()
    ok = {k: v for k, v in r.items() if "erro" not in v}
    erros = {k: v["erro"] for k, v in r.items() if "erro" in v}
    for fid, v in ok.items():
        print(f"correio: fonte={fid} lidos={v['lidos']} novos={v['novos']} pulados={v['pulados']} recarga={'sim' if v['recarga'] else 'nao'}")
    print(f"correio: fontes={len(r)} ok={len(ok)}")
    print("correio: " + " ".join(f"{k}={int(v) if isinstance(v, bool) else v}" for k, v in c.items()) + f" purgados={purgados} purgadas={podadas}")
    for fid, msg in erros.items():
        print(f"AVISO: fonte {contas.get(fid, fid)} falhou: {msg}", file=sys.stderr)
    todas = bool(r) and not ok
    inesperado = any(not m.startswith("conta não autorizada") for m in erros.values())
    return 1 if todas and inesperado else 0


if __name__ == "__main__":
    sys.exit(main())
