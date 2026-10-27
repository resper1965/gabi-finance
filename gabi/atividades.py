"""Atividades (ADR-033): to-do pessoal que o Hermes cria a partir de um recado do Ricardo, com lista no painel e aviso no Telegram.

Regras de criar, listar, concluir, cancelar e adiar; a API, o MCP e o painel só chamam daqui. `ValueError` = dado ou transição inválida; `LookupError` = id inexistente.
Datas entram e saem em Brasília (`AAAA-MM-DD` = dia todo, `AAAA-MM-DDTHH:MM` = com hora); no banco `vence_em` é UTC e `tem_hora=0` guarda 00:00 de Brasília.
Não existe reabrir: para voltar, cria de novo. Toda escrita grava `decisao`. Consome: db (atividade, projeto, decisao).
Projetos (ADR-034): a atividade pode ter `projeto_id`, `depende_de_id` (uma dependência) e `marco`; é `bloqueada` enquanto a atividade da qual depende está aberta (feita ou cancelada libera).
Bloqueada não gera aviso na hora, de manhã nem entra no resumo."""
import datetime as dt
import re
import unicodedata

from gabi.hoje import BRT

UTC = dt.timezone.utc
MAX_TEXTO = 500
_COM_HORA = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
_SO_DIA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# `bloqueada` sai de uma subconsulta, sem coluna física: depende de alguém que ainda está aberta.
_SEL = ("select a.*, (a.depende_de_id is not null and exists(select 1 from atividade d where d.id=a.depende_de_id and d.status='aberta')) as bloqueada "
        "from atividade a")


def _norm(s: str) -> str:
    """Sem acento, caixa e espaços repetidos; emoji e escrita não latina ficam (só os sinais de acento saem)."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", str(s or "")) if unicodedata.category(c) != "Mn")
    return " ".join(sem_acento.casefold().split())


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
            "status": row["status"], "origem": row["origem"], "criada_em": row["criada_em"], "concluida_em": row["concluida_em"], "prazo": _prazo(row, agora),
            "projeto_id": row["projeto_id"], "depende_de_id": row["depende_de_id"], "marco": bool(row["marco"]), "bloqueada": bool(row["bloqueada"])}


def _auditar(con, agora: dt.datetime, quem: str, origem: str, o_que: str) -> None:
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?,?)", (agora.astimezone(UTC).isoformat(), quem, o_que, origem))


def _ler(con, id_: int):
    r = con.execute(_SEL + " where a.id=?", (id_,)).fetchone()
    if r is None:
        raise LookupError(f"atividade {id_} não existe")
    return r


def criar(con, agora: dt.datetime, quem: str, origem: str, texto: str, vence_em: str | None = None,
          projeto_id: int | None = None, depende_de_id: int | None = None, marco: bool = False, auditar: bool = True) -> dict:
    texto = str(texto or "").strip()
    if not texto:
        raise ValueError("o texto da atividade não pode ficar vazio")
    if len(texto) > MAX_TEXTO:
        raise ValueError(f"o texto da atividade passa de {MAX_TEXTO} caracteres")
    utc, tem_hora = _parse(vence_em, agora)
    if projeto_id is not None:
        p = con.execute("select status from projeto where id=?", (projeto_id,)).fetchone()
        if p is None:
            raise LookupError(f"projeto {projeto_id} não existe")
        if p["status"] in ("concluido", "cancelado"):
            raise ValueError(f"o projeto {projeto_id} está {p['status']} e não aceita atividade nova")
    if depende_de_id is not None:
        _ler(con, depende_de_id)
    for r in con.execute(_SEL + " where a.status='aberta' and a.vence_em is ? and a.projeto_id is ?", (utc, projeto_id)):
        if _norm(r["texto"]) == _norm(texto):
            return {**_item(r, agora), "ja_existia": True}
    novo = con.execute("insert into atividade(texto, vence_em, tem_hora, origem, criada_em, projeto_id, depende_de_id, marco) values (?,?,?,?,?,?,?,?)",
                       (texto, utc, int(tem_hora), origem, agora.astimezone(UTC).isoformat(), projeto_id, depende_de_id, int(bool(marco)))).lastrowid
    if auditar:  # `projetos.criar` grava uma linha só para o projeto inteiro
        _auditar(con, agora, quem, origem, f"atividade {novo} criada: {texto[:80]}")
    return {**_item(_ler(con, novo), agora), "ja_existia": False}


_ORDEM = {"vencida": 0, "hoje": 1, "proxima": 2, "sem_data": 3}


def listar(con, agora: dt.datetime, status: str = "aberta", projeto_id: int | None = None) -> list[dict]:
    if status not in ("aberta", "feita", "cancelada"):
        raise ValueError("status deve ser aberta, feita ou cancelada")
    itens = [_item(r, agora) for r in con.execute(_SEL + " where a.status=? and (? is null or a.projeto_id=?) order by a.id", (status, projeto_id, projeto_id))]
    return sorted(itens, key=lambda i: (_ORDEM[i["prazo"]], i["vence_em"] or "", i["id"]))


def abertas_por_texto(con, trecho: str) -> list[dict]:
    t = _norm(trecho)
    agora = dt.datetime.now(UTC)
    return [_item(r, agora) for r in con.execute(_SEL + " where a.status='aberta' order by a.id") if t and t in _norm(r["texto"])]


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


def _criada_antes_da_manha(r, local: dt.datetime) -> bool:
    """Criada antes das 07:00 de hoje (Brasília): só essas ganham o aviso "para hoje"; as ditas durante o dia ele já sabe."""
    try:
        criada = dt.datetime.fromisoformat(r["criada_em"]).astimezone(BRT)
    except ValueError:
        return True
    return criada < local.replace(hour=MANHA.hour, minute=MANHA.minute, second=0, microsecond=0)


def montar_resumo(con, agora: dt.datetime) -> dict | None:
    """O resumo do dia (vencidas, para hoje, sem data; até 15 linhas, `contagens` e `total` reais) ou None se não há nada aberto assim."""
    abertas = [i for i in (_item(r, agora) for r in con.execute(_SEL + " where a.status='aberta' order by a.id")) if not i["bloqueada"]]
    ordem = sorted((i for i in abertas if i["prazo"] != "proxima"), key=lambda i: (_ORDEM[i["prazo"]], i["vence_em"] or "", i["id"]))
    if not ordem:
        return None
    visiveis = ordem[:MAX_RESUMO]
    payload = {chave: [_resumo_item(i) for i in visiveis if i["prazo"] == prazo] for prazo, chave in GRUPOS}
    payload["contagens"] = {chave: sum(1 for i in ordem if i["prazo"] == prazo) for prazo, chave in GRUPOS}
    payload["total"] = len(ordem)
    return payload


def avisos_devidos(con, agora: dt.datetime) -> list[tuple[str, str, dict]]:
    """Só leitura. -> [(tipo, chave, payload)] para `avisos.gerar_avisos` gravar em `aviso` (um por tipo+chave por dia, regra do `_novo`).
    `atividade_hora`: com hora, já chegou (até 2 dias atrás), uma vez só. `atividade_hoje`: vence hoje, a partir das 07:00 de Brasília, se foi criada antes
    das 07:00 e a hora (se houver) ainda não passou. `atividade_resumo`: a partir das 07:00."""
    local = agora.astimezone(BRT)
    manha = local.time() >= MANHA
    devidos: list[tuple[str, str, dict]] = []
    for r in con.execute(_SEL + " where a.status='aberta' order by a.id"):
        i = _item(r, agora)
        if i["bloqueada"]:
            continue
        p = _resumo_item(i)
        q = dt.datetime.fromisoformat(r["vence_em"]) if r["vence_em"] else None
        if r["tem_hora"] and agora - JANELA_HORA <= q <= agora:
            devidos.append(("atividade_hora", f"{r['id']}|{r['vence_em']}", p))
        if manha and i["vence_em"] and i["vence_em"][:10] == local.date().isoformat() and not (r["tem_hora"] and q <= agora) and _criada_antes_da_manha(r, local):
            devidos.append(("atividade_hoje", str(r["id"]), p))
    resumo = montar_resumo(con, agora) if manha else None
    if resumo:
        devidos.append(("atividade_resumo", local.date().isoformat(), resumo))
    return devidos


def revalidar_aviso(con, tipo: str, payload: dict) -> tuple[bool, dict]:
    """Releitura na entrega (usada por `avisos.revalidar`) -> (vale, payload_atual). hora/hoje valem se a atividade segue aberta no mesmo vencimento.
    Resumo: refeito com o que está aberto agora; não vale se não sobrou nada."""
    if tipo in ("atividade_hora", "atividade_hoje"):
        r = con.execute(_SEL + " where a.id=?", (payload.get("id"),)).fetchone()
        return bool(r and r["status"] == "aberta" and not r["bloqueada"] and _local(r["vence_em"], bool(r["tem_hora"])) == payload.get("vence_em")), payload
    atual = montar_resumo(con, dt.datetime.now(UTC))
    return (atual is not None), (atual or payload)
