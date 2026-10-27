"""Projetos (ADR-034): gestão de projetos de qualquer tipo, conduzida pelo Hermes (ou outro agente MCP) e vista no painel.

Regras de criar (com atividades e dependências), listar, atualizar e resolver; a API, o MCP e o painel só chamam daqui. `ValueError` = dado ou transição inválida; `LookupError` = id inexistente.
As atividades do projeto são as de `gabi.atividades` (`projeto_id`, `depende_de_id`, `marco`). Estados: ativo, pausado, concluido, cancelado; os dois últimos não aceitam atividade nova e não reabrem.
Cancelar o projeto cancela as atividades abertas dele. Prazo em Brasília (`AAAA-MM-DD`; passado é aceito: o projeto pode estar atrasado). Toda escrita grava `decisao`. Consome: db, gabi.atividades."""
import datetime as dt
import re

from gabi import atividades as ativs
from gabi.atividades import UTC, _auditar, _norm

MAX_ATIVIDADES = 30
MAX_NOME = 200
MAX_OBJETIVO = 2000
STATUS = ("ativo", "pausado", "concluido", "cancelado")
FINAIS = ("concluido", "cancelado")
_DIA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _ler(con, id_: int):
    r = con.execute("select * from projeto where id=?", (id_,)).fetchone()
    if r is None:
        raise LookupError(f"projeto {id_} não existe")
    return r


def _progresso(con, id_: int) -> dict:
    feitas, total = con.execute("select coalesce(sum(status='feita'),0), count(*) from atividade where projeto_id=? and status!='cancelada'", (id_,)).fetchone()
    return {"feitas": feitas, "total": total}


def _item(con, row) -> dict:
    return {"id": row["id"], "nome": row["nome"], "objetivo": row["objetivo"], "status": row["status"], "prazo": row["prazo"],
            "orcamento_centavos": row["orcamento_centavos"], "criado_em": row["criado_em"], "encerrado_em": row["encerrado_em"], "origem": row["origem"],
            "progresso": _progresso(con, row["id"])}


def _nome(nome: str) -> str:
    nome = " ".join(str(nome or "").split())
    if not nome:
        raise ValueError("o nome do projeto não pode ficar vazio")
    if len(nome) > MAX_NOME:
        raise ValueError(f"o nome do projeto passa de {MAX_NOME} caracteres")
    return nome


def _objetivo(objetivo: str | None) -> str:
    objetivo = str(objetivo or "").strip()
    if len(objetivo) > MAX_OBJETIVO:
        raise ValueError(f"o objetivo passa de {MAX_OBJETIVO} caracteres")
    return objetivo


def _prazo(prazo: str | None) -> str | None:
    if prazo in (None, ""):
        return None
    p = str(prazo).strip()
    try:
        if not _DIA.match(p):
            raise ValueError
        dt.date.fromisoformat(p)
    except ValueError:
        raise ValueError("prazo deve ser AAAA-MM-DD (horário de Brasília)") from None
    return p


def _orcamento(centavos: int | None) -> int | None:
    if centavos is None:
        return None
    if isinstance(centavos, bool) or not isinstance(centavos, int) or centavos <= 0:
        raise ValueError("o orçamento deve ser maior que zero")
    return centavos


def _validar_lista(lista: list[dict] | None) -> list[dict]:
    lista = list(lista or [])
    if len(lista) > MAX_ATIVIDADES:
        raise ValueError(f"um projeto novo aceita até {MAX_ATIVIDADES} atividades")
    for n, a in enumerate(lista, 1):
        if not isinstance(a, dict):
            raise ValueError(f"atividade {n}: deve ser um objeto com 'texto'")
        d = a.get("depois_de")
        if d is not None and (isinstance(d, bool) or not isinstance(d, int) or not 1 <= d < n):
            raise ValueError(f"atividade {n}: 'depois_de' deve apontar para uma atividade anterior da lista (1 a {n - 1})")
    return lista


def criar(con, agora: dt.datetime, quem: str, origem: str, nome: str, objetivo: str = "", prazo: str | None = None,
          orcamento_centavos: int | None = None, atividades: list[dict] | None = None) -> dict:
    """Cria o projeto e a lista inicial numa transação só: qualquer dado inválido recusa tudo."""
    lista = _validar_lista(atividades)
    nome, objetivo, prazo, orcamento = _nome(nome), _objetivo(objetivo), _prazo(prazo), _orcamento(orcamento_centavos)
    con.execute("savepoint projeto_criar")
    try:
        novo = con.execute("insert into projeto(nome, objetivo, prazo, orcamento_centavos, criado_em, origem) values (?,?,?,?,?,?)",
                           (nome, objetivo, prazo, orcamento, agora.astimezone(UTC).isoformat(), origem)).lastrowid
        ids: list[int] = []
        for a in lista:
            d = a.get("depois_de")
            item = _criar_atividade(con, agora, quem, origem, a, novo, ids[d - 1] if d else None)
            ids.append(item["id"])
        _auditar(con, agora, quem, origem, f"projeto {novo} criado: {nome[:80]} ({len(ids)} atividades)")
    except BaseException:
        con.execute("rollback to projeto_criar")
        raise
    finally:
        con.execute("release projeto_criar")
    return _item(con, _ler(con, novo))


def _criar_atividade(con, agora, quem, origem, a: dict, projeto_id: int, depende_de_id: int | None) -> dict:
    item = ativs.criar(con, agora, quem, origem, a.get("texto"), a.get("vence"), projeto_id=projeto_id, depende_de_id=depende_de_id, marco=bool(a.get("marco")), auditar=False)
    if item.get("ja_existia"):
        raise ValueError(f"a atividade '{item['texto']}' aparece duas vezes na lista")
    return item


def listar(con, agora: dt.datetime, status: str = "ativo") -> list[dict]:
    if status not in STATUS:
        raise ValueError("status deve ser ativo, pausado, concluido ou cancelado")
    return [_item(con, r) for r in con.execute("select * from projeto where status=? order by id", (status,))]


def atualizar(con, agora: dt.datetime, quem: str, origem: str, id_: int, *, status: str | None = None, prazo: str | None = None,
              objetivo: str | None = None, orcamento_centavos: int | None = None, nome: str | None = None) -> dict:
    r = _ler(con, id_)
    campos: dict = {}
    if status is not None:
        if status not in STATUS:
            raise ValueError("status deve ser ativo, pausado, concluido ou cancelado")
        if status != r["status"]:
            if r["status"] in FINAIS:
                raise ValueError(f"o projeto {id_} já está {r['status']} e não reabre; crie de novo")
            campos["status"] = status
            if status in FINAIS:
                campos["encerrado_em"] = agora.astimezone(UTC).isoformat()
    if prazo is not None:
        campos["prazo"] = _prazo(prazo)
    if objetivo is not None:
        campos["objetivo"] = _objetivo(objetivo)
    if orcamento_centavos is not None:
        campos["orcamento_centavos"] = _orcamento(orcamento_centavos)
    if nome is not None:
        campos["nome"] = _nome(nome)
    if not campos:
        return _item(con, r)
    con.execute("savepoint projeto_atualizar")
    try:
        con.execute(f"update projeto set {', '.join(f'{k}=?' for k in campos)} where id=?", (*campos.values(), id_))
        if campos.get("status") == "cancelado":
            for (aid,) in con.execute("select id from atividade where projeto_id=? and status='aberta'", (id_,)).fetchall():
                ativs.cancelar(con, agora, quem, origem, aid)
        _auditar(con, agora, quem, origem, f"projeto {id_} atualizado ({', '.join(campos)}): {r['nome'][:80]}")
    except BaseException:
        con.execute("rollback to projeto_atualizar")
        raise
    finally:
        con.execute("release projeto_atualizar")
    return _item(con, _ler(con, id_))


def resolver(con, projeto: str | int) -> int:
    """Id numérico (qualquer estado) ou trecho do nome entre os ativos e pausados; sem acento nem caixa."""
    t = str(projeto).strip()
    if t.isdigit():
        return _ler(con, int(t))["id"]
    n = _norm(t)
    achados = [r for r in con.execute("select id, nome from projeto where status in ('ativo','pausado') order by id") if n and n in _norm(r["nome"])]
    if not achados:
        raise LookupError(f"nenhum projeto ativo com '{t}' no nome")
    if len(achados) > 1:
        raise ValueError("mais de um projeto combina: " + "; ".join(f"{r['id']}: {r['nome']}" for r in achados))
    return achados[0]["id"]
