"""Coletor do Teams: lê, pela ponte do Graph, só METADADOS das conversas (quando, quem, se é para mim) e atualiza `teams_conversa`.
O texto da mensagem nunca chega aqui (a ponte não o devolve); o único texto livre persistido é `de_nome`.

Erros pela ponte: o serviço de fontes devolve só o tipo e a mensagem; um `_ErroStatus` do Graph chega como `ErroGraphNess` com a mensagem
`_ErroStatus: GET <caminho> -> <status>`. O status é lido desse texto (regex ancorada em `GET ... -> NNN`): qualquer erro COM status (403, 404, 400, 500...) pula só o chat (um chat "envenenado" não trava os
outros) e é contado em `puladas`; 429 encerra a conta nesta rodada; erro SEM status (transporte/indisponível) encerra a conta e vai
(curto) para `teams_fonte.ultimo_erro`. Nunca se grava o texto de um erro com status."""
import datetime as dt
import re

from gabi.fontes.graph_ness import ErroGraphNess
from gabi.teams.regra import _dt, _parametro

JANELA_INICIAL_HORAS = 24
_STATUS = re.compile(r"^(?:_ErroStatus: )?GET .* -> (\d{3})\b")


def _status(e: Exception) -> int | None:
    s = getattr(e, "status", None)
    if isinstance(s, int):
        return s
    m = _STATUS.match(str(e))
    return int(m[1]) if m else None


def _janela(con) -> float:
    h = _parametro(con, "teams.janela_inicial_horas")
    return JANELA_INICIAL_HORAS if isinstance(h, bool) or not isinstance(h, (int, float)) or h <= 0 else h


def _chat(con, ponte, conta: str, c: dict, agora: dt.datetime, janela: float) -> tuple[int, int]:
    """(lido, novas) de um chat. Levanta ErroGraphNess; quem chama decide pular o chat ou encerrar a conta."""
    atual = con.execute("select * from teams_conversa where conta=? and chat_id=?", (conta, c["chat_id"])).fetchone()
    cursor = _dt(atual["cursor"]) if atual else None
    ultima = _dt(c["ultima_em"])
    if cursor is not None and ultima is not None and ultima <= cursor:
        return 0, 0
    # a fonte trunca para segundos e usa '>' estrito: recuar 1 s é inofensivo (as atualizações usam max)
    desde = (cursor - dt.timedelta(seconds=1)) if cursor else agora - dt.timedelta(hours=janela)
    msgs = ponte.teams_mensagens(conta, c["chat_id"], desde.isoformat())
    para_mim, resposta, nome, novo_cursor = (atual[k] if atual else None for k in ("ultima_para_mim_em", "minha_ultima_resposta_em", "de_nome", "cursor"))
    # leitura bem-sucedida devolveu tudo > desde até agora: o cursor avança até a última atividade conhecida do chat (ou ao `desde` lido)
    for q in [m["quando"] for m in msgs] + ([c["ultima_em"]] if c["ultima_em"] else []) or [desde.isoformat()]:
        if novo_cursor is None or _dt(q) > _dt(novo_cursor):
            novo_cursor = q
    for m in msgs:
        q = m["quando"]
        if m["de_eu"]:
            if resposta is None or _dt(q) > _dt(resposta):
                resposta = q
        elif c["tipo"] == "um_a_um" or m["mencoes_eu"]:
            if para_mim is None or _dt(q) > _dt(para_mim):
                para_mim = q
            nome = m["de_nome"]
    con.execute(
        "insert into teams_conversa(conta, chat_id, tipo, de_nome, ultima_para_mim_em, minha_ultima_resposta_em, cursor) values (?,?,?,?,?,?,?)"
        " on conflict(conta, chat_id) do update set tipo=excluded.tipo, de_nome=excluded.de_nome, ultima_para_mim_em=excluded.ultima_para_mim_em,"
        " minha_ultima_resposta_em=excluded.minha_ultima_resposta_em, cursor=excluded.cursor",
        (conta, c["chat_id"], c["tipo"], nome, para_mim, resposta, novo_cursor))
    return 1, len(msgs)


def _conta(con, ponte, conta: str, agora: dt.datetime, janela: float) -> dict:
    chats = novas = puladas = ok = 0
    for c in ponte.teams_chats(conta):
        try:
            lido, n = _chat(con, ponte, conta, c, agora, janela)
        except ErroGraphNess as e:
            st = _status(e)
            if st is not None and st != 429:
                puladas += 1  # este chat falhou (sem acesso, sumiu, 4xx/5xx): pula só ele
                continue
            raise  # 429 ou erro sem status: encerra a conta
        chats, novas, ok = chats + lido, novas + n, ok + 1  # `ok`: chats tratados sem erro (lidos ou pulados pelo cursor)
    if puladas and not ok:
        raise ErroGraphNess("todos os chats falharam na leitura")  # sem status: encerra a conta com falha, não é aviso suave
    return {"chats": chats, "novas": novas, **({"puladas": puladas} if puladas else {})}


def coletar(con, ponte, agora: dt.datetime) -> dict[str, dict]:
    """Por conta liberada (`estado='sim'`): {"chats": n, "novas": n} ou {"erro": str}. Uma conta falhar não para as outras."""
    janela = _janela(con)
    saida = {}
    for f in con.execute("select id, conta from teams_fonte where estado='sim' order by id").fetchall():
        try:
            r = _conta(con, ponte, f["conta"], agora, janela)
        except ErroGraphNess as e:
            msg = (_status(e) == 429 and "limite de requisições do Graph (429)") or str(e)[:200]
            r = {"erro": msg}
            con.execute("update teams_fonte set ultimo_erro=? where id=?", (msg, f["id"]))
        else:
            aviso = f"{r['puladas']} chat(s) pulado(s) por erro" if r.get("puladas") else None
            con.execute("update teams_fonte set coletada_em=?, ultimo_erro=? where id=?", (agora.isoformat(), aviso, f["id"]))
        saida[f["conta"]] = r
    return saida
