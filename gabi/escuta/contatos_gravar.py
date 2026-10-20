"""Aplica no Graph da ness as propostas de contato APROVADAS pelo dono (contato_proposta, migração 0072). Programa: python -m gabi.escuta.contatos_gravar,
rodado logo após a sincronização de contatos (ExecStartPost da mesma unit). Interruptor `contatos.escrita` em `parametro` (JSON "ligado"); qualquer outro
valor ou ausência = desligado: nada é enviado e as aprovadas só são contadas como simuladas. Sem rede: a escrita passa pela ponte do serviço de fontes.
Cada proposta roda no seu try (uma falha não aborta as outras) e termina `aplicada` ou `falhou` com motivo FIXO (nunca texto de exceção, nome ou número).
Saída e logs só com contagens."""
import fcntl
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from gabi.db import conectar, migrar, transacao
from gabi.escuta.contatos import _parametro, contas_contatos

CONTATO_ALTERADO, JA_EXISTE, GRAPH_INDISPONIVEL = "contato_alterado", "ja_existe", "graph_indisponivel"


def escrita_ligada(con) -> bool:
    return _parametro(con, "contatos.escrita", "desligado") == "ligado"


@contextmanager
def trava(banco: Path):
    """Uma aplicação por vez (flock não bloqueante em <pasta do banco>/locks/contatos_gravar.lock): rodadas sobrepostas nunca enviam o mesmo POST
    duas vezes. Rende True com a trava, False se outra rodada a tem."""
    pasta = Path(banco).parent / "locks"
    pasta.mkdir(parents=True, exist_ok=True)
    f = open(pasta / "contatos_gravar.lock", "w")
    try:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        f.close()  # fechar libera a trava, mesmo em erro


def _falhou(con, pid: int, motivo: str) -> None:
    con.execute("update contato_proposta set estado='falhou', motivo=? where id=? and estado='aprovada'", (motivo, pid))


def _registrar(con, gravar) -> bool:
    """Grava o resultado local depois do Graph. Erro do banco não sobe (o laço segue); devolve False para a proposta virar falha."""
    try:
        with transacao(con):
            gravar()
        return True
    except Exception:  # noqa: BLE001 - nunca reenvia; quem chama tenta ao menos marcar 'falhou'
        return False


def _conta_fora(con, p) -> bool:
    """A conta saiu de escuta.contas_contatos: a sincronização apagou o contato_graph dela, então a revalidação local não enxerga mais nada."""
    return p["conta"] not in contas_contatos(con)


def _remetente_mudou(con, p) -> bool:
    r = con.execute("select nome, estado from escuta_remetente where numero=?", (p["telefone_depois"],)).fetchone()
    return r is None or r["estado"] != "aprovado" or not isinstance(r["nome"], str) or r["nome"].strip() != p["nome_depois"]


def _aplicar_criar(con, graph, p, agora: str) -> str | None:
    tel = p["telefone_depois"]
    if _conta_fora(con, p) or _remetente_mudou(con, p):
        return CONTATO_ALTERADO
    if con.execute("select 1 from contato_graph where telefone=?", (tel,)).fetchone() or \
            con.execute("select 1 from contato_google where telefone=?", (tel,)).fetchone():
        return JA_EXISTE
    try:
        r = graph.contato_criar(p["conta"], p["nome_depois"], tel)
        gid = r.get("id") if isinstance(r, dict) else None
        if not isinstance(gid, str) or not gid:
            return GRAPH_INDISPONIVEL
    except Exception:  # noqa: BLE001 - ErroGraphNess ou falha da ponte: motivo fixo, sem o texto
        return GRAPH_INDISPONIVEL

    def gravar():
        con.execute("insert or replace into contato_graph(conta, graph_id, nome, telefone_original, telefone, campo, atualizado_em) values (?,?,?,?,?,'mobile',?)",
                    (p["conta"], gid, p["nome_depois"], tel, tel, agora))
        con.execute("update contato_proposta set estado='aplicada', motivo=null, aplicada_em=? where id=? and estado='aprovada'", (agora, p["id"]))
    return None if _registrar(con, gravar) else GRAPH_INDISPONIVEL


def _aplicar_corrigir(con, graph, p, agora: str) -> str | None:
    chave = (p["conta"], p["graph_id"], p["telefone_antes"])
    atual = con.execute("select nome from contato_graph where conta=? and graph_id=? and telefone_original=? and campo='mobile' and nome is ?",
                        (*chave, p["nome_antes"])).fetchone()
    if p["graph_id"] is None or p["telefone_antes"] is None or atual is None or _conta_fora(con, p):
        return CONTATO_ALTERADO
    try:
        r = graph.contato_corrigir(p["conta"], p["graph_id"], {"nome": p["nome_antes"], "telefone": p["telefone_antes"]},
                                   {"nome": p["nome_depois"], "telefone": p["telefone_depois"]})
        resultado = r.get("resultado") if isinstance(r, dict) else None
    except Exception:  # noqa: BLE001 - idem
        return GRAPH_INDISPONIVEL
    if resultado == "alterado":
        return CONTATO_ALTERADO
    if resultado != "ok":
        return GRAPH_INDISPONIVEL

    def gravar():
        con.execute("update contato_graph set nome=?, telefone_original=?, telefone=?, atualizado_em=? where conta=? and graph_id=? and telefone_original=?",
                    (p["nome_depois"], p["telefone_depois"], p["telefone_depois"], agora, *chave))
        con.execute("update contato_proposta set estado='aplicada', motivo=null, aplicada_em=? where id=? and estado='aprovada'", (agora, p["id"]))
    return None if _registrar(con, gravar) else GRAPH_INDISPONIVEL


def aplicar(con, graph, agora: str) -> dict:
    return _aplicar(con, graph, agora)[0]


def _aplicar(con, graph, agora: str) -> tuple[dict, int]:
    """Só `aprovada`. Desligado: nenhuma chamada ao `graph`, estado intacto, tudo conta como simulada. Ligado: revalida contra o banco antes de
    escrever: conta fora de escuta.contas_contatos -> contato_alterado; criar: remetente não está mais aprovado com o mesmo nome -> contato_alterado,
    número já existe em contato_graph/contato_google (qualquer conta) -> ja_existe; corrigir: a linha lida não é mais a mesma -> contato_alterado."""
    r = {"aplicadas": 0, "falhas": 0, "descartadas": 0, "simuladas": 0}
    indisponivel = 0
    aprovadas = con.execute("select * from contato_proposta where estado='aprovada' order by id").fetchall()
    if not escrita_ligada(con):
        r["simuladas"] = len(aprovadas)
        return r, 0
    for p in aprovadas:
        try:  # segunda guarda (a primeira é a trava do main): outra rodada pode já ter tratado esta proposta
            atual = con.execute("select estado from contato_proposta where id=?", (p["id"],)).fetchone()
            if atual is None or atual["estado"] != "aprovada":
                continue
            motivo = (_aplicar_criar if p["tipo"] == "criar" else _aplicar_corrigir)(con, graph, p, agora)
        except Exception:  # noqa: BLE001 - erro local inesperado também não deixa a proposta presa em 'aprovada'
            motivo = GRAPH_INDISPONIVEL
        if motivo is None:
            r["aplicadas"] += 1
            continue
        try:
            _falhou(con, p["id"], motivo)
        except Exception:  # noqa: BLE001 - banco indisponível ao registrar: conta como falha e segue com as outras
            motivo = GRAPH_INDISPONIVEL
        r["falhas"] += 1
        if motivo == CONTATO_ALTERADO:
            r["descartadas"] += 1
        if motivo == GRAPH_INDISPONIVEL:
            indisponivel += 1
    return r, indisponivel


def main(banco: Path | None = None, *, graph=None) -> int:
    """Só contagens. 2 sem socket; 1 se alguma proposta falhou por indisponibilidade do Graph; 0 nos demais casos."""
    banco = Path(banco or os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db"))
    if graph is None:
        sock = os.environ.get("GABI_FONTES_SOCKET")
        if not sock:
            print("ERRO: GABI_FONTES_SOCKET não configurado", file=sys.stderr)
            return 2
        from gabi.fontes.ponte import PonteGraph
        graph = PonteGraph(sock)
    with trava(banco) as minha:
        if not minha:
            print("contatos-gravar: ja_em_execucao=1")
            return 0
        con = conectar(banco)
        migrar(con, Path(__file__).resolve().parent.parent.parent / "migrations")
        try:
            ligada = escrita_ligada(con)
            aprovadas = con.execute("select count(*) from contato_proposta where estado='aprovada'").fetchone()[0]
            r, indisponivel = _aplicar(con, graph, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        finally:
            con.close()
    print(f"contatos-gravar: escrita={'ligada' if ligada else 'desligada'} aprovadas={aprovadas} simuladas={r['simuladas']} "
          f"aplicadas={r['aplicadas']} falhas={r['falhas']} descartadas={r['descartadas']}")
    return 1 if indisponivel else 0


if __name__ == "__main__":
    sys.exit(main())
