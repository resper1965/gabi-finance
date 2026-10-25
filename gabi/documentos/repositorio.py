"""Documentos de pessoas e bens: propostas, aprovação, consulta, vencimentos e resolução do titular.
Consome: bem, documento, documento_numero, documento_data, documento_proposta (migração 0081), pessoa, gabi.familia.fichas
(resolver_pessoa); grava em decisao (origem 'documentos').
Número "as is": guardado exatamente como veio; só a comparação ignora espaços e `.`, `-`, `/` (nenhum dígito verificador).
Tudo entra como proposta; só `decidir` cria ou muda documento e bem. `decisao.o_que` leva ids, tipo e estado, nunca número."""
import datetime as dt
import json
import re

from gabi.db import transacao
from gabi.envios.propostas import normalizar_nome
from gabi.familia.fichas import ErroFamilia, _somar_meses, resolver_pessoa

TIPOS_DATA = ("emissao", "validade", "vigencia_inicio", "vigencia_fim", "vencimento", "renovacao")
DATAS_VENCE = ("validade", "vigencia_fim", "vencimento")
TITULARES = ("pessoa", "bem")
TIPOS_BEM = ("imovel", "veiculo", "outro")
ORIGENS = ("hermes", "carga", "leitura")
ORIGEM_DOC = {"hermes": "ricardo", "carga": "carga", "leitura": "leitura"}
NUMEROS_BEM = ("placa", "renavam", "chassi", "matricula", "inscricao_iptu")
CAMPOS = ("titular_tipo", "titular_id", "tipo", "pais", "emissor", "numeros", "datas")
ESTADOS = ("pendente", "aprovada", "recusada")
_PAIS = re.compile(r"^[A-Z]{2}$")
_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIPO = re.compile(r"^[a-z][a-z_]{0,39}$")


class ErroDocumentos(Exception):
    """Falha com código fixo (nunca número nem texto do documento)."""

    def __init__(self, codigo: str):
        super().__init__(codigo)
        self.codigo = codigo


def chave(valor) -> str:
    """Número comparável: sem espaços, `.`, `-` e `/`, em maiúsculas. Só para comparar; o guardado é o original."""
    return re.sub(r"[\s.\-/]", "", str(valor or "")).upper()


def mascarado(valor) -> bool:
    return "*" in str(valor or "")


def ts(agora: dt.datetime) -> str:
    if agora.tzinfo:
        agora = agora.astimezone(dt.timezone.utc)
    return agora.strftime("%Y-%m-%dT%H:%M:%SZ")


def _texto(v) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normalizar_nome(v if isinstance(v, str) else "")).split())


def _invalido():
    return ErroDocumentos("valor_invalido")


def _str(v, maximo: int, obrigatorio: bool = True):
    if v is None or (isinstance(v, str) and not v.strip()):
        if obrigatorio:
            raise _invalido()
        return None
    if not isinstance(v, str) or len(v.strip()) > maximo:
        raise _invalido()
    return v.strip()


def _data(v) -> str:
    if not (isinstance(v, str) and _DATA.match(v.strip())):
        raise _invalido()
    try:
        dt.date.fromisoformat(v.strip())
    except ValueError:
        raise _invalido() from None
    return v.strip()


def _tipo(v) -> str:
    """Tipo normalizado (sem acento, minúsculas, espaços viram `_`); só letras e `_`: o tipo vai para `decisao.o_que`, que
    nunca leva número."""
    t = "_".join(normalizar_nome(_str(v, 40)).split())
    if not _TIPO.match(t):
        raise _invalido()
    return t


def validar(doc) -> dict:
    """Documento proposto no formato canônico (chaves em ordem, datas na ordem de TIPOS_DATA); `valor_invalido` se não serve."""
    if not isinstance(doc, dict) or set(doc) - set(CAMPOS):
        raise ErroDocumentos("requisicao_invalida")
    if doc.get("titular_tipo") not in TITULARES:
        raise _invalido()
    pais = doc.get("pais") or "BR"
    pais = pais.strip().upper() if isinstance(pais, str) else ""
    if not _PAIS.match(pais):
        raise _invalido()
    numeros, datas = doc.get("numeros") or [], doc.get("datas") or []
    if not isinstance(numeros, list) or not isinstance(datas, list):
        raise _invalido()
    nums = []
    for n in numeros:
        if not isinstance(n, dict):
            raise _invalido()
        nums.append({"nome": _str(n.get("nome"), 40).lower(), "valor": _str(n.get("valor"), 60)})
    porti = {}
    for d in datas:
        if not isinstance(d, dict) or d.get("tipo") not in TIPOS_DATA or d["tipo"] in porti:
            raise _invalido()
        porti[d["tipo"]] = _data(d.get("data"))
    return {"titular_tipo": doc["titular_tipo"], "titular_id": _str(doc.get("titular_id"), 80, obrigatorio=False),
            "tipo": _tipo(doc.get("tipo")), "pais": pais, "emissor": _str(doc.get("emissor"), 200, obrigatorio=False),
            "numeros": nums, "datas": [{"tipo": t, "data": porti[t]} for t in TIPOS_DATA if t in porti]}


def _validar_bem(bem) -> dict:
    if not isinstance(bem, dict) or bem.get("tipo") not in TIPOS_BEM:
        raise _invalido()
    dados = bem.get("dados") or {}
    if not isinstance(dados, dict):
        raise _invalido()
    return {"tipo": bem["tipo"], "nome": _str(bem.get("nome"), 120), "dados": dados}


def _paperless(v):
    if v is None or v == 0:
        return None
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        raise _invalido()
    return v


def _principal(doc: dict) -> str:
    return chave(doc["numeros"][0]["valor"]) if doc["numeros"] else ""


def _nome_titular(con, titular_tipo, titular_id):
    """Nome da pessoa ou do bem ativo; None se não existe ou saiu."""
    tabela = "pessoa" if titular_tipo == "pessoa" else "bem"
    r = con.execute(f"select nome from {tabela} where id=? and excluido_em is null", (titular_id,)).fetchone()
    return r["nome"] if r else None


def documento(con, documento_id: int) -> dict | None:
    """Documento (ativo ou não) com números e datas; None se não existe."""
    d = con.execute("select * from documento where id=?", (documento_id,)).fetchone()
    if d is None:
        return None
    return {"id": d["id"], "titular_tipo": d["titular_tipo"], "titular_id": d["titular_id"], "tipo": d["tipo"], "pais": d["pais"],
            "emissor": d["emissor"], "paperless_id": d["paperless_id"], "origem": d["origem"],
            "numeros": [{"nome": n["nome"], "valor": n["valor"]} for n in con.execute(
                "select nome, valor from documento_numero where documento_id=? order by id", (d["id"],))],
            "datas": sorted(({"tipo": x["tipo"], "data": x["data"]} for x in con.execute(
                "select tipo, data from documento_data where documento_id=?", (d["id"],))), key=lambda x: TIPOS_DATA.index(x["tipo"])),
            "criado_em": d["criado_em"], "atualizado_em": d["atualizado_em"], "excluido_em": d["excluido_em"]}


def ativo(con, doc: dict) -> dict | None:
    """Documento ativo do mesmo titular, tipo e país com o mesmo número principal (o primeiro por id)."""
    alvo = _principal(doc)
    for (i,) in con.execute("select id from documento where titular_tipo=? and titular_id=? and tipo=? and pais=? and excluido_em is null"
                            " order by id", (doc["titular_tipo"], doc["titular_id"], doc["tipo"], doc["pais"])):
        d = documento(con, i)
        if (chave(d["numeros"][0]["valor"]) if d["numeros"] else "") == alvo:
            return d
    return None


def _igual(atual: dict, doc: dict, paperless_id) -> bool:
    """Aprovar não mudaria nada: campo vazio na proposta mantém o atual."""
    datas = {x["tipo"]: x["data"] for x in atual["datas"]}
    return ((doc["emissor"] is None or doc["emissor"] == atual["emissor"])
            and (paperless_id is None or paperless_id == atual["paperless_id"])
            and all(datas.get(x["tipo"]) == x["data"] for x in doc["datas"])
            and all(any(m["nome"] == n["nome"] and chave(m["valor"]) == chave(n["valor"]) for m in atual["numeros"]) for n in doc["numeros"]))


def _pendentes_iguais(con, doc: dict, paperless_id=None) -> list:
    """Propostas pendentes para o mesmo titular, tipo, país e número principal (as linhas, da mais antiga para a mais nova). Sem
    titular (bem novo), também o mesmo documento do Paperless: bens novos de documentos diferentes não se juntam."""
    def k(o, pl):
        return (o["titular_tipo"], o["titular_id"], o["tipo"], o["pais"], _principal(o), pl if o["titular_id"] is None else None)
    alvo = k(doc, paperless_id)
    return [p for p in con.execute("select id, doc, paperless_id from documento_proposta where estado='pendente' order by id")
            if k(json.loads(p["doc"]), p["paperless_id"]) == alvo]


def _recusada(con, doc: dict, paperless_id) -> bool:
    """O Ricardo já recusou isto: mesmo titular, tipo, país, número principal e datas; ou o mesmo documento do Paperless com o mesmo
    número principal. Vale também para as recusas copiadas da família pela 0081."""
    alvo = _principal(doc)
    for p in con.execute("select doc, paperless_id from documento_proposta where estado='recusada'"):
        try:
            r = json.loads(p["doc"])
            if _principal(r) != alvo:
                continue
            if paperless_id is not None and p["paperless_id"] == paperless_id:
                return True
            if ((r["titular_tipo"], r["titular_id"], r["tipo"], r["pais"]) == (doc["titular_tipo"], doc["titular_id"], doc["tipo"], doc["pais"])
                    and {x["tipo"]: x["data"] for x in r.get("datas") or []} == {x["tipo"]: x["data"] for x in doc["datas"]}):
                return True
        except (TypeError, ValueError, KeyError, IndexError, AttributeError):
            continue  # proposta antiga com formato estranho não bloqueia nada
    return False


def _vence(doc: dict) -> list[str]:
    return [x["data"] for x in doc["datas"] if x["tipo"] in DATAS_VENCE]


def _mais_antiga(atual: dict, doc: dict) -> bool:
    """Todas as datas de vencimento propostas são anteriores à última do documento ativo (scan antigo do mesmo documento)."""
    novas, velhas = _vence(doc), _vence(atual)
    return bool(novas) and bool(velhas) and max(novas) < max(velhas)


def _titular_existe(con, doc: dict) -> bool:
    return doc["titular_id"] is not None and _nome_titular(con, doc["titular_tipo"], doc["titular_id"]) is not None


def inserir_proposta(con, doc: dict, *, documento_id, paperless_id, conferir: bool, motivos: list, origem: str, criada_em: str,
                     bem_novo: dict | None = None) -> int:
    """Grava a proposta (doc já canônico), sem conferências; o chamador abre a transação."""
    return con.execute(
        "insert into documento_proposta(doc, documento_id, bem_novo, paperless_id, conferir, motivos, origem, criada_em)"
        " values (?,?,?,?,?,?,?,?)",
        (json.dumps(doc, ensure_ascii=False), documento_id, json.dumps(bem_novo, ensure_ascii=False) if bem_novo else None,
         paperless_id, 1 if conferir else 0, json.dumps(list(motivos), ensure_ascii=False), origem, criada_em)).lastrowid


def propor(con, doc: dict, *, origem: str, paperless_id: int | None, conferir: bool, motivos: list[str], agora: dt.datetime,
           bem_novo: dict | None = None) -> int | None:
    """Cria a proposta e devolve o id; None se não há o que propor. Na ordem:
    - leitura e carga: None se o Ricardo já recusou isto (`_recusada`); pelo Hermes (o próprio Ricardo) pode propor de novo;
    - None se o documento ativo já tem esses valores, ou se todas as datas de vencimento são mais antigas que as dele (scan antigo);
    - pendente igual (titular, tipo, país e número principal) do mesmo documento do Paperless: atualizada no lugar (doc, motivos,
      conferir, bem novo) e o id dela; de outro documento com as mesmas datas, o id dela; com datas diferentes, uma proposta nova
      (as duas ficam visíveis ao Ricardo).
    Com o mesmo número principal de um ativo, a proposta o substitui (`documento_id`). Sem titular, só com `bem_novo` (o bem nasce
    na aprovação)."""
    if origem not in ORIGENS:
        raise ErroDocumentos("requisicao_invalida")
    doc, paperless_id = validar(doc), _paperless(paperless_id)
    bem_novo = _validar_bem(bem_novo) if bem_novo is not None else None
    if not isinstance(motivos, list) or not all(isinstance(m, str) for m in motivos):
        raise _invalido()
    with transacao(con, imediata=True):
        if doc["titular_id"] is None:
            if bem_novo is None or doc["titular_tipo"] != "bem":
                raise ErroDocumentos("titular_invalido")
        elif not _titular_existe(con, doc):
            raise ErroDocumentos("titular_invalido")
        if origem in ("leitura", "carga") and _recusada(con, doc, paperless_id):
            return None
        atual = ativo(con, doc) if doc["titular_id"] is not None else None
        if atual is not None and (_igual(atual, doc, paperless_id) or _mais_antiga(atual, doc)):
            return None
        abertas = _pendentes_iguais(con, doc, paperless_id)
        mesma = next((p for p in abertas if p["paperless_id"] == paperless_id), None)
        if mesma is not None:
            con.execute("update documento_proposta set doc=?, documento_id=?, bem_novo=?, conferir=?, motivos=? where id=?",
                        (json.dumps(doc, ensure_ascii=False), atual["id"] if atual else None,
                         json.dumps(bem_novo, ensure_ascii=False) if bem_novo else None, 1 if conferir else 0,
                         json.dumps(list(motivos), ensure_ascii=False), mesma["id"]))
            return mesma["id"]
        datas = {x["tipo"]: x["data"] for x in doc["datas"]}
        for p in abertas:
            if {x["tipo"]: x["data"] for x in json.loads(p["doc"])["datas"]} == datas:
                return p["id"]
        return inserir_proposta(con, doc, documento_id=atual["id"] if atual else None, paperless_id=paperless_id, conferir=conferir,
                                motivos=motivos, origem=origem, criada_em=ts(agora), bem_novo=bem_novo)


def _criar_bem(con, bem: dict, quando: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", normalizar_nome(bem["nome"])).strip("-") or "bem"
    bid, n = base, 1
    while con.execute("select 1 from bem where id=?", (bid,)).fetchone():
        n += 1
        bid = f"{base}-{n}"
    con.execute("insert into bem(id, tipo, nome, dados, criado_em) values (?,?,?,?,?)",
                (bid, bem["tipo"], bem["nome"], json.dumps(bem["dados"], ensure_ascii=False), quando))
    return bid


def _criar(con, doc: dict, paperless_id, origem: str, quando: str) -> int:
    i = con.execute("insert into documento(titular_tipo, titular_id, tipo, pais, emissor, paperless_id, origem, criado_em, atualizado_em)"
                    " values (?,?,?,?,?,?,?,?,?)", (doc["titular_tipo"], doc["titular_id"], doc["tipo"], doc["pais"], doc["emissor"],
                                                    paperless_id, ORIGEM_DOC[origem], quando, quando)).lastrowid
    for n in doc["numeros"]:
        con.execute("insert into documento_numero(documento_id, nome, valor) values (?,?,?)", (i, n["nome"], n["valor"]))
    for x in doc["datas"]:
        con.execute("insert into documento_data(documento_id, tipo, data) values (?,?,?)", (i, x["tipo"], x["data"]))
    return i


def _atualizar(con, alvo: dict, doc: dict, paperless_id, origem: str, quando: str) -> None:
    """Campo vazio mantém o atual. Número igual (sem formatação) fica como está; diferente (o mascarado) é trocado, e o
    documento passa a ter a origem da proposta. O principal casa com o principal; os outros, pelo nome."""
    novos = {}
    if doc["emissor"] is not None:
        novos["emissor"] = doc["emissor"]
    if paperless_id is not None:
        novos["paperless_id"] = paperless_id
    linhas = [dict(r) for r in con.execute("select id, nome, valor from documento_numero where documento_id=? order by id", (alvo["id"],))]
    for k, n in enumerate(doc["numeros"]):
        ex = linhas[0] if k == 0 and linhas else next((r for r in linhas[1:] if r["nome"] == n["nome"]), None)
        if ex is None:
            con.execute("insert into documento_numero(documento_id, nome, valor) values (?,?,?)", (alvo["id"], n["nome"], n["valor"]))
        elif chave(ex["valor"]) != chave(n["valor"]):
            con.execute("update documento_numero set nome=?, valor=? where id=?", (n["nome"], n["valor"], ex["id"]))
            if k == 0:
                novos["origem"] = ORIGEM_DOC[origem]
    for x in doc["datas"]:
        con.execute("insert into documento_data(documento_id, tipo, data) values (?,?,?)"
                    " on conflict(documento_id, tipo) do update set data=excluded.data", (alvo["id"], x["tipo"], x["data"]))
    sets = "".join(f"{c}=?, " for c in novos)
    con.execute(f"update documento set {sets}atualizado_em=? where id=?", (*novos.values(), quando, alvo["id"]))


def _alvo(con, p, doc: dict) -> dict | None:
    """O documento indicado pela proposta, se ainda ativo, do mesmo titular, tipo e país e com o mesmo número (ou mascarado:
    outra proposta pode já ter trocado o número); senão o ativo igual."""
    if p["documento_id"] is not None:
        d = documento(con, p["documento_id"])
        if (d is not None and d["excluido_em"] is None
                and (d["titular_tipo"], d["titular_id"], d["tipo"], d["pais"]) == (doc["titular_tipo"], doc["titular_id"], doc["tipo"], doc["pais"])
                and d["numeros"] and (mascarado(d["numeros"][0]["valor"]) or chave(d["numeros"][0]["valor"]) == _principal(doc))):
            return d
    return ativo(con, doc)


def _sem_vazios(campos: dict) -> dict:
    """Correção: número ou data com valor vazio é removido da lista (o resto `validar` confere)."""
    def vazio(v):
        return v is None or (isinstance(v, str) and not v.strip())
    saida = dict(campos)
    for chave_lista, campo in (("numeros", "valor"), ("datas", "data")):
        if isinstance(saida.get(chave_lista), list):
            saida[chave_lista] = [x for x in saida[chave_lista] if not (isinstance(x, dict) and vazio(x.get(campo)))]
    return saida


def _quem(doc: dict) -> str:
    if doc["titular_tipo"] == "pessoa" and doc["titular_id"]:
        return f"da pessoa {doc['titular_id']}"
    return "de um bem" if doc["titular_tipo"] == "bem" else "sem titular"


def decidir(con, proposta_id: int, estado: str, quem: str, agora: dt.datetime, correcao: dict | None = None) -> dict:
    """Aprova (cria ou atualiza o documento e, se for o caso, o bem novo, na mesma transação) ou recusa (nada muda).
    `correcao` troca campos do documento proposto antes de aprovar (listas `numeros` e `datas` inteiras: item com valor vazio sai,
    item novo entra); `bem_nome` dá o nome do bem novo; trocar o titular descarta o bem novo. Já decidida: `conflito`."""
    if estado not in ("aprovada", "recusada"):
        raise ErroDocumentos("requisicao_invalida")
    if correcao is not None and (not isinstance(correcao, dict) or set(correcao) - set(CAMPOS) - {"bem_nome"}):
        raise ErroDocumentos("requisicao_invalida")
    bem_nome = _str((correcao or {}).get("bem_nome"), 120, obrigatorio=False)
    campos = _sem_vazios({k: v for k, v in (correcao or {}).items() if k != "bem_nome"})
    with transacao(con, imediata=True):
        p = con.execute("select * from documento_proposta where id=?", (proposta_id,)).fetchone()
        if p is None:
            raise ErroDocumentos("nao_encontrado")
        if p["estado"] != "pendente":
            raise ErroDocumentos("conflito")
        quando, doc = ts(agora), json.loads(p["doc"])
        documento_id = bem_id = None
        if estado == "aprovada":
            if campos:
                doc = validar({**doc, **campos})
            trocou = "titular_id" in campos or "titular_tipo" in campos
            if doc["titular_id"] is None:
                if not p["bem_novo"] or trocou or doc["titular_tipo"] != "bem":
                    raise ErroDocumentos("titular_invalido")
                bem = _validar_bem(json.loads(p["bem_novo"]))
                if bem_nome:
                    bem["nome"] = bem_nome
                    con.execute("update documento_proposta set bem_novo=? where id=?", (json.dumps(bem, ensure_ascii=False), proposta_id))
                bem_id = _criar_bem(con, bem, quando)
                doc["titular_id"] = bem_id
            elif not _titular_existe(con, doc):
                raise ErroDocumentos("titular_invalido")
            alvo = _alvo(con, p, doc)
            if alvo is not None:
                _atualizar(con, alvo, doc, p["paperless_id"], p["origem"], quando)
                documento_id = alvo["id"]
            else:
                documento_id = _criar(con, doc, p["paperless_id"], p["origem"], quando)
        con.execute("update documento_proposta set estado=?, decidida_em=?, decidida_por=?, documento_id=coalesce(?, documento_id), doc=?"
                    " where id=?", (estado, quando, quem, documento_id, json.dumps(doc, ensure_ascii=False), proposta_id))
        con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?,'documentos')",
                    (quando, quem, f"Proposta {proposta_id} de documento ({doc['tipo']}) {_quem(doc)}: {estado}"))
    return {"proposta_id": proposta_id, "estado": estado, "documento_id": documento_id, "bem_id": bem_id}


def listar_propostas(con, estado: str = "pendente") -> list[dict]:
    """Propostas no estado dado, da mais antiga para a mais nova, com o titular (ou None: bem novo) e o documento `atual`."""
    if estado not in ESTADOS:
        raise ErroDocumentos("requisicao_invalida")
    saida = []
    for p in con.execute("select * from documento_proposta where estado=? order by id", (estado,)):
        doc = json.loads(p["doc"])
        titular = None
        if doc.get("titular_id") is not None:
            titular = {"tipo": doc["titular_tipo"], "id": doc["titular_id"], "nome": _nome_titular(con, doc["titular_tipo"], doc["titular_id"])}
        saida.append({"id": p["id"], "titular": titular, "doc": doc, "bem_novo": json.loads(p["bem_novo"]) if p["bem_novo"] else None,
                      "conferir": bool(p["conferir"]), "motivos": json.loads(p["motivos"]), "paperless_id": p["paperless_id"],
                      "origem": p["origem"], "estado": p["estado"], "criada_em": p["criada_em"],
                      "atual": documento(con, p["documento_id"]) if p["documento_id"] is not None else None})
    return saida


def consultar(con, *, titular_tipo=None, titular_id=None, tipo=None, texto=None) -> list[dict]:
    """Documentos ativos de titulares ativos, com `titular_nome`. `texto` procura no tipo, emissor, nome do titular, nome dos
    números e nos próprios números (sem formatação)."""
    filtros, args = ["excluido_em is null"], []
    for col, v in (("titular_tipo", titular_tipo), ("titular_id", titular_id), ("tipo", tipo)):
        if v is not None:
            filtros.append(f"{col}=?")
            args.append(v)
    alvo, alvo_num = _texto(texto), chave(texto)
    saida = []
    for (i,) in con.execute(f"select id from documento where {' and '.join(filtros)} order by id", args):
        d = documento(con, i)
        nome = _nome_titular(con, d["titular_tipo"], d["titular_id"])
        if nome is None:
            continue
        if texto is not None:
            palheiro = _texto(" ".join([d["tipo"], d["emissor"] or "", nome, *(n["nome"] for n in d["numeros"])]))
            if not ((alvo and alvo in palheiro) or (alvo_num and any(alvo_num in chave(n["valor"]) for n in d["numeros"]))):
                continue
        saida.append({**d, "titular_nome": nome})
    return saida


def vencimentos(con, hoje: dt.date, meses: int) -> list[dict]:
    """Documentos ativos cuja última data entre validade, fim de vigência e vencimento cai entre hoje - 30 dias e hoje + `meses`;
    por data. Sem número."""
    ini, fim = (hoje - dt.timedelta(days=30)).isoformat(), _somar_meses(hoje, meses).isoformat()
    ultima: dict = {}
    for r in con.execute("select d.id, d.titular_tipo, d.titular_id, d.tipo, x.tipo data_tipo, x.data from documento d"
                         " join documento_data x on x.documento_id=d.id where d.excluido_em is null and x.tipo in (?,?,?)", DATAS_VENCE):
        if r["id"] not in ultima or r["data"] > ultima[r["id"]]["data"]:
            ultima[r["id"]] = r
    saida = []
    for r in sorted(ultima.values(), key=lambda r: (r["data"], r["id"])):
        nome = _nome_titular(con, r["titular_tipo"], r["titular_id"])
        if nome is None or not ini <= r["data"] <= fim:
            continue
        saida.append({"documento_id": r["id"], "titular_tipo": r["titular_tipo"], "titular_id": r["titular_id"], "titular_nome": nome,
                      "tipo": r["tipo"], "data_tipo": r["data_tipo"], "data": r["data"], "vencido": r["data"] < hoje.isoformat()})
    return saida


def bens(con) -> list[dict]:
    saida = []
    for r in con.execute("select * from bem where excluido_em is null order by id"):
        try:
            dados = json.loads(r["dados"])
        except (TypeError, ValueError):
            dados = {}
        saida.append({"id": r["id"], "tipo": r["tipo"], "nome": r["nome"], "dados": dados if isinstance(dados, dict) else {},
                      "criado_em": r["criado_em"]})
    return saida


def resolver_titular(con, pistas: dict) -> tuple[str, str] | None:
    """Titular pelas pistas, na ordem da spec §2.5: pessoa pelo CPF; pelo nome (`resolver_pessoa`, ambíguo não serve); bem
    por placa, Renavam, chassi, matrícula ou inscrição (documento aprovado do bem ou dados do bem); bem pelo endereço igual."""
    if not isinstance(pistas, dict):
        return None
    cpf = chave(pistas.get("cpf")) if isinstance(pistas.get("cpf"), str) else ""
    if cpf:
        for r in con.execute("select d.titular_id, n.valor from documento d join documento_numero n on n.documento_id=d.id"
                             " join pessoa p on p.id=d.titular_id and p.excluido_em is null"
                             " where d.titular_tipo='pessoa' and d.tipo='cpf' and d.excluido_em is null order by d.id, n.id"):
            if chave(r["valor"]) == cpf:
                return "pessoa", r["titular_id"]
    if isinstance(pistas.get("nome"), str) and pistas["nome"].strip():
        try:
            return "pessoa", resolver_pessoa(con, pistas["nome"])
        except ErroFamilia:
            pass
    lista = bens(con)
    for nome in NUMEROS_BEM:
        v = chave(pistas.get(nome)) if isinstance(pistas.get(nome), str) else ""
        if not v:
            continue
        for r in con.execute("select d.titular_id, n.valor from documento d join documento_numero n on n.documento_id=d.id"
                             " join bem b on b.id=d.titular_id and b.excluido_em is null"
                             " where d.titular_tipo='bem' and d.excluido_em is null and n.nome=? order by d.id", (nome,)):
            if chave(r["valor"]) == v:
                return "bem", r["titular_id"]
        for b in lista:
            if isinstance(b["dados"].get(nome), str) and chave(b["dados"][nome]) == v:
                return "bem", b["id"]
    end = _texto(pistas.get("endereco"))
    if end:
        for b in lista:
            if _texto(b["dados"].get("endereco")) == end:
                return "bem", b["id"]
    return None
