"""Lixeira do correio, em três passos que o painel (rota) e o chat (ferramenta `email_lixeira`) compartilham: `planejar` (banco), `aplicar` (rede, sem banco) e
`marcar` (banco, e fecha o aviso emergencial da conversa, como restaurar e dispensar). A conexão sqlite não cruza threads: quem chama roda só `aplicar` dentro de `asyncio.to_thread`.
Só trash (recuperável): nada é apagado de vez; restaurar é pelo painel. Nenhum texto de erro da origem sai daqui (pode citar conta ou id).
Consome: a ponte do serviço de fontes (método `lixeira`), tabelas email_msg e email_fonte."""
import datetime as dt

from gabi.correio.processar import fechar_alerta
from gabi.fontes.google_oauth import ErroGoogleOAuth
from gabi.fontes.graph_ness import ErroGraphNess

TRIADAS = ("classificada", "alertada", "restaurada")  # mensagens que ainda estão na caixa e já passaram pela triagem


def planejar(con, ids: list[int], *, so_lixo: bool) -> tuple[dict[tuple[str, str, int], list[tuple[int, str]]], list[dict], list[int]]:
    """Separa os ids em lotes por conta `(provedor, conta, fonte_id)` com `(id, externo_id)`, falhas `{"id", "codigo"}` e `ja_estavam` (já na lixeira).
    Códigos: `nao_encontrado`, `nao_triada` (com `so_lixo`, também a que não é `classificada` de classe `lixo`), `conta_desligada`, `conta_sem_lixeira`."""
    lotes: dict[tuple[str, str, int], list[tuple[int, str]]] = {}
    falhas: list[dict] = []
    ja: list[int] = []
    for mid in dict.fromkeys(ids):
        m = con.execute("select m.id, m.externo_id, m.estado, m.classe, f.id as fonte_id, f.conta, f.provedor, f.estado as conta_estado, f.lixeira as conta_lixeira "
                        "from email_msg m join email_fonte f on f.id=m.fonte_id where m.id=?", (mid,)).fetchone()
        if m is None:
            codigo = "nao_encontrado"
        elif m["estado"] == "na_lixeira":
            ja.append(mid)
            continue
        elif (m["estado"] != "classificada" or m["classe"] != "lixo") if so_lixo else m["estado"] not in TRIADAS:
            codigo = "nao_triada"
        elif m["conta_estado"] != "sim":
            codigo = "conta_desligada"
        elif not m["conta_lixeira"]:
            codigo = "conta_sem_lixeira"
        else:
            lotes.setdefault((m["provedor"], m["conta"], m["fonte_id"]), []).append((mid, m["externo_id"]))
            continue
        falhas.append({"id": mid, "codigo": codigo})
    return lotes, falhas, ja


def aplicar(ponte, conta: str, itens: list[tuple[int, str]]) -> tuple[list[int], list[dict]]:
    """Manda o lote para a lixeira da origem (só rede, sem banco). Devolve os ids que a origem confirmou `"ok"` e as falhas; erro da ponte ou resposta
    que não confirma vira `fonte_indisponivel`."""
    try:
        res = ponte.lixeira(conta, [ext for _, ext in itens])
    except (ErroGoogleOAuth, ErroGraphNess):
        res = None
    if not isinstance(res, dict):
        return [], [{"id": i, "codigo": "fonte_indisponivel"} for i, _ in itens]
    ok = [i for i, ext in itens if res.get(ext) == "ok"]
    return ok, [{"id": i, "codigo": "fonte_indisponivel"} for i, ext in itens if res.get(ext) != "ok"]


def marcar(con, ids: list[int], agora: dt.datetime) -> list[int]:
    """Marca `na_lixeira` só onde a mensagem ainda é triada (o estado pode ter mudado entre planejar e marcar). Devolve os ids que mudaram. Quem chama abre a transação."""
    quando = agora.astimezone(dt.timezone.utc).isoformat()
    mudou = []
    for i in ids:
        m = con.execute("select thread_id, externo_id from email_msg where id=?", (i,)).fetchone()
        if con.execute("update email_msg set estado='na_lixeira', atualizado_em=? where id=? and estado in ('classificada','alertada','restaurada')", (quando, i)).rowcount:
            mudou.append(i)
            fechar_alerta(con, m["thread_id"] or m["externo_id"], quando)   # a mensagem saiu da caixa: o aviso emergencial dela perde o sentido
    return mudou
