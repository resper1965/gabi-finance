"""Atividades (ADR-033): to-do pessoal que o Hermes cria a partir de um recado do Ricardo, com lista no painel e aviso no Telegram.

Regras de criar, listar, concluir, cancelar e adiar; a API, o MCP e o painel só chamam daqui. `ValueError` = dado ou transição inválida; `LookupError` = id inexistente.
Datas entram e saem em Brasília (`AAAA-MM-DD` = dia todo, `AAAA-MM-DDTHH:MM` = com hora); no banco `vence_em` é UTC e `tem_hora=0` guarda 00:00 de Brasília.
Não existe reabrir: para voltar, cria de novo. Toda escrita grava `decisao`. Consome: db (atividade, decisao)."""
import datetime as dt
import re
import unicodedata

from gabi.hoje import BRT

UTC = dt.timezone.utc
MAX_TEXTO = 500
_COM_HORA = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
_SO_DIA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().casefold().split())


def _parse(vence_em: str | None, agora: dt.datetime) -> tuple[str | None, bool]:
    """Texto local → (UTC ISO, tem_hora); recusa o passado (dia anterior a hoje; hora que já passou)."""
    if vence_em in (None, ""):
        return None, False
    v = str(vence_em).strip()
    try:
        if _COM_HORA.match(v):
            quando, tem_hora = dt.datetime.fromisoformat(v).replace(tzinfo=BRT), True
        elif _SO_DIA.match(v):
            quando, tem_hora = dt.datetime.fromisoformat(v).replace(tzinfo=BRT), False
        else:
            raise ValueError
    except ValueError:
        raise ValueError("vencimento deve ser AAAA-MM-DD ou AAAA-MM-DDTHH:MM (horário de Brasília)") from None
    if tem_hora and quando <= agora:
        raise ValueError("esse horário já passou")
    if not tem_hora and quando.date() < agora.astimezone(BRT).date():
        raise ValueError("essa data já passou")
    return quando.astimezone(UTC).isoformat(), tem_hora


def _local(vence_em: str | None, tem_hora: bool) -> str | None:
    if not vence_em:
        return None
    q = dt.datetime.fromisoformat(vence_em).astimezone(BRT)
    return q.strftime("%Y-%m-%dT%H:%M") if tem_hora else q.strftime("%Y-%m-%d")


def _prazo(row, agora: dt.datetime) -> str:
    if not row["vence_em"]:
        return "sem_data"
    q = dt.datetime.fromisoformat(row["vence_em"]).astimezone(BRT)
    if row["tem_hora"] and q < agora:
        return "vencida"
    hoje = agora.astimezone(BRT).date()
    return "vencida" if q.date() < hoje else "hoje" if q.date() == hoje else "proxima"


def _item(row, agora: dt.datetime) -> dict:
    return {"id": row["id"], "texto": row["texto"], "vence_em": _local(row["vence_em"], bool(row["tem_hora"])), "tem_hora": bool(row["tem_hora"]),
            "status": row["status"], "origem": row["origem"], "criada_em": row["criada_em"], "concluida_em": row["concluida_em"], "prazo": _prazo(row, agora)}


def _auditar(con, agora: dt.datetime, quem: str, origem: str, o_que: str) -> None:
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?,?)", (agora.astimezone(UTC).isoformat(), quem, o_que, origem))


def _ler(con, id_: int):
    r = con.execute("select * from atividade where id=?", (id_,)).fetchone()
    if r is None:
        raise LookupError(f"atividade {id_} não existe")
    return r


def criar(con, agora: dt.datetime, quem: str, origem: str, texto: str, vence_em: str | None = None) -> dict:
    texto = str(texto or "").strip()
    if not texto:
        raise ValueError("o texto da atividade não pode ficar vazio")
    if len(texto) > MAX_TEXTO:
        raise ValueError(f"o texto da atividade passa de {MAX_TEXTO} caracteres")
    utc, tem_hora = _parse(vence_em, agora)
    for r in con.execute("select * from atividade where status='aberta' and vence_em is ?", (utc,)):
        if _norm(r["texto"]) == _norm(texto):
            return {**_item(r, agora), "ja_existia": True}
    novo = con.execute("insert into atividade(texto, vence_em, tem_hora, origem, criada_em) values (?,?,?,?,?)",
                       (texto, utc, int(tem_hora), origem, agora.astimezone(UTC).isoformat())).lastrowid
    _auditar(con, agora, quem, origem, f"atividade {novo} criada: {texto[:80]}")
    return {**_item(_ler(con, novo), agora), "ja_existia": False}


_ORDEM = {"vencida": 0, "hoje": 1, "proxima": 2, "sem_data": 3}


def listar(con, agora: dt.datetime, status: str = "aberta") -> list[dict]:
    if status not in ("aberta", "feita", "cancelada"):
        raise ValueError("status deve ser aberta, feita ou cancelada")
    itens = [_item(r, agora) for r in con.execute("select * from atividade where status=? order by id", (status,))]
    return sorted(itens, key=lambda i: (_ORDEM[i["prazo"]], i["vence_em"] or "", i["id"]))


def abertas_por_texto(con, trecho: str) -> list[dict]:
    t = _norm(trecho)
    agora = dt.datetime.now(UTC)
    return [_item(r, agora) for r in con.execute("select * from atividade where status='aberta' order by id") if t and t in _norm(r["texto"])]


def _fechar(con, agora, quem, origem, id_: int, estado: str, verbo: str) -> dict:
    r = _ler(con, id_)
    if r["status"] == estado:
        return _item(r, agora)
    if r["status"] != "aberta":
        raise ValueError(f"a atividade {id_} já está {r['status']}")
    con.execute("update atividade set status=?, concluida_em=? where id=?", (estado, agora.astimezone(UTC).isoformat(), id_))
    _auditar(con, agora, quem, origem, f"atividade {id_} {verbo}: {r['texto'][:80]}")
    return _item(_ler(con, id_), agora)


def concluir(con, agora, quem, origem, id_: int) -> dict:
    return _fechar(con, agora, quem, origem, id_, "feita", "concluída")


def cancelar(con, agora, quem, origem, id_: int) -> dict:
    return _fechar(con, agora, quem, origem, id_, "cancelada", "cancelada")


def adiar(con, agora, quem, origem, id_: int, vence_em: str) -> dict:
    r = _ler(con, id_)
    if r["status"] != "aberta":
        raise ValueError(f"a atividade {id_} já está {r['status']}")
    utc, tem_hora = _parse(vence_em, agora)
    if utc is None:
        raise ValueError("informe o novo vencimento")
    con.execute("update atividade set vence_em=?, tem_hora=? where id=?", (utc, int(tem_hora), id_))
    _auditar(con, agora, quem, origem, f"atividade {id_} adiada para {vence_em}: {r['texto'][:80]}")
    return _item(_ler(con, id_), agora)


MANHA = dt.time(7, 0)  # início da manhã em Brasília: hora do aviso "para hoje" e do resumo
MAX_RESUMO = 15
JANELA_HORA = dt.timedelta(days=2)  # mesma janela de entrega do Telegram: hora mais velha que isso só aparece no resumo
GRUPOS = (("vencida", "vencidas"), ("hoje", "hoje"), ("sem_data", "sem_data"))


def _resumo_item(i: dict) -> dict:
    return {"id": i["id"], "texto": i["texto"], "vence_em": i["vence_em"]}


def avisos_devidos(con, agora: dt.datetime) -> list[tuple[str, str, dict]]:
    """Só leitura. -> [(tipo, chave, payload)] para `avisos.gerar_avisos` gravar em `aviso` (um por tipo+chave por dia, regra do `_novo`).
    `atividade_hora`: com hora, já chegou (até 2 dias atrás). `atividade_hoje` e `atividade_resumo`: a partir das 07:00 de Brasília."""
    local = agora.astimezone(BRT)
    manha = local.time() >= MANHA
    devidos: list[tuple[str, str, dict]] = []
    abertas = []
    for r in con.execute("select * from atividade where status='aberta' order by id"):
        i = _item(r, agora)
        abertas.append(i)
        p = _resumo_item(i)
        if r["tem_hora"]:
            q = dt.datetime.fromisoformat(r["vence_em"])
            if agora - JANELA_HORA <= q <= agora:
                devidos.append(("atividade_hora", f"{r['id']}|{r['vence_em']}", p))
        if manha and i["vence_em"] and i["vence_em"][:10] == local.date().isoformat():
            devidos.append(("atividade_hoje", str(r["id"]), p))
    if manha:
        ordem = sorted((i for i in abertas if i["prazo"] != "proxima"), key=lambda i: (_ORDEM[i["prazo"]], i["vence_em"] or "", i["id"]))
        if ordem:
            visiveis = ordem[:MAX_RESUMO]
            payload = {chave: [_resumo_item(i) for i in visiveis if i["prazo"] == prazo] for prazo, chave in GRUPOS}
            payload["contagens"] = {chave: sum(1 for i in ordem if i["prazo"] == prazo) for prazo, chave in GRUPOS}
            payload["total"] = len(ordem)
            devidos.append(("atividade_resumo", local.date().isoformat(), payload))
    return devidos


def revalidar_aviso(con, tipo: str, payload: dict) -> tuple[bool, dict]:
    """Releitura na entrega (usada por `avisos.revalidar`) -> (vale, payload_atual). hora/hoje valem se a atividade segue aberta no mesmo vencimento.
    Resumo: tira as que já foram feitas ou canceladas; sem nenhuma restante, não vale (as além das 15 do aviso não são relidas)."""
    if tipo in ("atividade_hora", "atividade_hoje"):
        r = con.execute("select status, vence_em, tem_hora from atividade where id=?", (payload.get("id"),)).fetchone()
        return bool(r and r["status"] == "aberta" and _local(r["vence_em"], bool(r["tem_hora"])) == payload.get("vence_em")), payload
    abertas = {r[0] for r in con.execute("select id from atividade where status='aberta'")}
    atual, restante = dict(payload), 0
    contagens = dict(payload.get("contagens") or {})
    for _, chave in GRUPOS:
        itens = [i for i in payload.get(chave) or []]
        vivos = [i for i in itens if i["id"] in abertas]
        if chave in contagens:
            contagens[chave] -= len(itens) - len(vivos)
        atual[chave] = vivos
        restante += len(vivos)
    atual["contagens"] = contagens
    atual["total"] = payload.get("total", restante) - sum(len(payload.get(c) or []) - len(atual[c]) for _, c in GRUPOS)
    return restante > 0, atual
