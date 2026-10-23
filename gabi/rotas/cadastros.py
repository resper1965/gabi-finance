"""Cadastros (/api/v1/cadastros/{tipo}): empresas, contas, pessoas, compromissos e categorias (+ equivalência de categorias).

Exclusão é lógica (R10) e toda mudança vira `decisao`. Compromissos usam a MESMA validação da planilha do gabi-fin
(`planilha._linha`): linha aceita aqui é linha que a conciliação entende; ao mudar, a agenda do mês é recalculada.
Consome: dinheiro.{planilha,repositorio,contas_pagar}, envelope, identidade.
"""
import json
import logging
import re
import sqlite3
import unicodedata

from fastapi import APIRouter, Depends, Request

from gabi.dinheiro import contas_pagar as cp, planilha
from gabi.dinheiro.compromissos import _serie
from gabi.dinheiro.valor import formatar, para_centavos
from gabi.envelope import envelope
from gabi.identidade import Identidade, exigir
from gabi.mascara import mascarar_documento
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, erro

router = APIRouter(prefix="/api/v1/cadastros", dependencies=[Depends(exigir("boss"))])
RELACOES = {"contratante", "pj_titular", "outra"}
ESTADOS_CONTA = {"sim", "nao", "a_decidir"}
log = logging.getLogger("gabi.cadastros")


# ---------------- utilitários ----------------
def _slug(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "item"


def _id_unico(con, tabela: str, base: str) -> str:
    cand, n = base, 2
    while con.execute(f"select 1 from {tabela} where id=?", (cand,)).fetchone():
        cand, n = f"{base}-{n}", n + 1
    return cand


def _so(corpo: dict, permitidos: set) -> None:
    extra = set(corpo) - permitidos
    if extra:
        raise erro(400, "requisicao_invalida", f"campos desconhecidos: {sorted(extra)}")


def _texto(corpo: dict, campo: str, obrigatorio: bool = False):
    v = corpo.get(campo)
    if v is None:
        if obrigatorio:
            raise erro(400, "requisicao_invalida", f"{campo} é obrigatório")
        return None
    if not isinstance(v, str) or (obrigatorio and not v.strip()):
        raise erro(400, "requisicao_invalida", f"{campo} deve ser texto{' não vazio' if obrigatorio else ''}")
    return v.strip()


def _dados(corpo: dict, relacao: bool = False):
    if "dados" not in corpo:
        return None
    d = corpo["dados"]
    if not isinstance(d, dict):
        raise erro(400, "requisicao_invalida", "dados deve ser um objeto")
    if relacao and "relacao" in d and d["relacao"] not in RELACOES:
        raise erro(400, "requisicao_invalida", f"relacao deve ser uma de {sorted(RELACOES)}")
    return json.dumps(d, ensure_ascii=False)


def _auditar(con, quem: str, tipo: str, id_, acao: str) -> None:
    import datetime as dt
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'cadastros')",
                (dt.datetime.now(dt.timezone.utc).isoformat(), quem, f"cadastro {tipo} {id_} {acao}"))


def _tx(con, fn):
    con.execute("begin")
    try:
        r = fn()
        con.execute("commit")
        return r
    except sqlite3.IntegrityError as e:
        con.execute("rollback")
        raise erro(409, "conflito", f"já existe ou viola uma regra do cadastro: {e}")
    except BaseException:
        con.execute("rollback")
        raise


# ---------------- empresas e pessoas (mesmo molde) ----------------
class Simples:
    """Cadastro de id textual com colunas livres + `dados` (JSON). Serve a empresas e pessoas."""

    def __init__(self, tabela, campos, relacao=False):
        self.tabela, self.campos, self.relacao = tabela, campos, relacao

    def _ser(self, r):
        d = {"id": r["id"], **{c: r[c] for c in self.campos if c != "dados"}, "dados": json.loads(r["dados"] or "{}"), "origem": r["origem"], "excluido_em": r["excluido_em"]}
        return d

    def listar(self, con, busca, incluir):
        sql = f"select * from {self.tabela} where 1=1" + ("" if incluir else " and excluido_em is null")
        args = []
        if busca:
            sql += " and nome like ?"
            args.append(f"%{busca}%")
        return [self._ser(r) for r in con.execute(sql + " order by nome", args)]

    def obter(self, con, id_):
        r = con.execute(f"select * from {self.tabela} where id=? and excluido_em is null", (id_,)).fetchone()
        if r is None:
            raise erro(404, "nao_encontrado", f"{self.tabela} {id_} não existe")
        return self._ser(r)

    def criar(self, con, corpo, quem, tipo):
        _so(corpo, set(self.campos))
        nome = _texto(corpo, "nome", True)
        vals = {c: _texto(corpo, c) for c in self.campos if c not in ("nome", "dados")}
        dados = _dados(corpo, self.relacao) or "{}"

        def fazer():
            id_ = _id_unico(con, self.tabela, _slug(nome))
            cols = ["id", "nome", *vals, "dados", "origem"]
            con.execute(f"insert into {self.tabela}({','.join(cols)}) values ({','.join('?' * len(cols))})", [id_, nome, *vals.values(), dados, "manual"])
            _auditar(con, quem, tipo, id_, "criada")
            return id_
        return self.obter(con, _tx(con, fazer))

    def atualizar(self, con, id_, corpo, quem, tipo):
        self.obter(con, id_)
        _so(corpo, set(self.campos))
        if not corpo:
            raise erro(400, "requisicao_invalida", "informe ao menos um campo")
        sets = {}
        for c in corpo:
            sets[c] = _dados(corpo, self.relacao) if c == "dados" else _texto(corpo, c, c == "nome")

        def fazer():
            con.execute(f"update {self.tabela} set {', '.join(f'{c}=?' for c in sets)} where id=?", [*sets.values(), id_])
            _auditar(con, quem, tipo, id_, "alterada")
        _tx(con, fazer)
        return self.obter(con, id_)

    def excluir(self, con, id_, quem, tipo):
        self.obter(con, id_)

        def fazer():
            con.execute(f"update {self.tabela} set excluido_em=datetime('now') where id=?", (id_,))
            _auditar(con, quem, tipo, id_, "excluída")
        _tx(con, fazer)
        return {"id": id_, "excluido": True}


def _pessoa_existe(con, pid) -> bool:
    return isinstance(pid, str) and con.execute("select 1 from pessoa where id=? and excluido_em is null", (pid,)).fetchone() is not None


# ---------------- categorias ----------------
class Categorias:
    def _ser(self, r):
        return {"id": r["id"], "nome": r["nome"], "pai_id": r["pai_id"], "nibo_category_id": r["nibo_category_id"], "dono_padrao": r["dono_padrao"], "excluido_em": r["excluido_em"]}

    def listar(self, con, busca, incluir):
        sql = "select * from categoria where 1=1" + ("" if incluir else " and excluido_em is null")
        args = []
        if busca:
            sql += " and nome like ?"
            args.append(f"%{busca}%")
        return [self._ser(r) for r in con.execute(sql + " order by nome", args)]

    def obter(self, con, id_):
        r = con.execute("select * from categoria where id=? and excluido_em is null", (self._id(id_),)).fetchone()
        if r is None:
            raise erro(404, "nao_encontrado", f"categoria {id_} não existe")
        return self._ser(r)

    @staticmethod
    def _id(id_):
        try:
            return int(id_)
        except ValueError:
            raise erro(404, "nao_encontrado", f"categoria {id_} não existe")

    def _pai(self, con, corpo, proprio=None):
        pai = corpo.get("pai_id")
        if pai is None:
            return None
        if isinstance(pai, bool) or not isinstance(pai, int) or pai == proprio or con.execute("select 1 from categoria where id=?", (pai,)).fetchone() is None:
            raise erro(400, "requisicao_invalida", f"pai_id={pai!r} inválido")
        return pai

    def criar(self, con, corpo, quem, tipo):
        _so(corpo, {"nome", "pai_id", "nibo_category_id"})
        nome, pai, nibo = _texto(corpo, "nome", True), self._pai(con, corpo), _texto(corpo, "nibo_category_id")

        def fazer():
            cid = con.execute("insert into categoria(nome, pai_id, nibo_category_id) values (?,?,?)", (nome, pai, nibo or None)).lastrowid
            _auditar(con, quem, tipo, cid, "criada")
            return cid
        return self.obter(con, _tx(con, fazer))

    def atualizar(self, con, id_, corpo, quem, tipo):
        atual = self.obter(con, id_)
        _so(corpo, {"nome", "pai_id", "nibo_category_id", "dono_padrao"})
        if not corpo:
            raise erro(400, "requisicao_invalida", "informe ao menos um campo")
        nome = _texto(corpo, "nome", True) if "nome" in corpo else atual["nome"]
        pai = self._pai(con, corpo, atual["id"]) if "pai_id" in corpo else atual["pai_id"]
        nibo = (_texto(corpo, "nibo_category_id") or None) if "nibo_category_id" in corpo else atual["nibo_category_id"]
        dono = atual["dono_padrao"]
        if "dono_padrao" in corpo:
            dono = corpo["dono_padrao"]
            if dono is not None and not _pessoa_existe(con, dono):
                raise erro(400, "requisicao_invalida", f"dono_padrao={dono!r} não é uma pessoa cadastrada")

        def fazer():
            con.execute("update categoria set nome=?, pai_id=?, nibo_category_id=?, dono_padrao=? where id=?", (nome, pai, nibo, dono, atual["id"]))
            _auditar(con, quem, tipo, atual["id"], "alterada")
        _tx(con, fazer)
        return self.obter(con, id_)

    def excluir(self, con, id_, quem, tipo):
        atual = self.obter(con, id_)

        def fazer():
            con.execute("update categoria set excluido_em=datetime('now') where id=?", (atual["id"],))
            _auditar(con, quem, tipo, atual["id"], "excluída")
        _tx(con, fazer)
        return {"id": atual["id"], "excluido": True}


# ---------------- contas ----------------
class Contas:
    def _ser(self, r):
        return {"id": r["id"], "externo_id": r["externo_id"], "instituicao": r["instituicao"], "tipo": r["tipo"], "apelido": r["apelido"],
                "pj": bool(r["pj"]), "estado": r["estado"], "titular": r["titular"], "limite": None if r["limite_centavos"] is None else formatar(r["limite_centavos"]),
                "nibo_account_id": r["nibo_account_id"], "usuarios": json.loads(r["usuarios"]) if r["usuarios"] else [],
                "origem": "manual" if str(r["externo_id"]).startswith("manual-") else "open_finance",
                "excluido_em": r["excluido_em"]}

    def listar(self, con, busca, incluir):
        sql = "select * from conta where 1=1" + ("" if incluir else " and excluido_em is null")
        args = []
        if busca:
            sql += " and (apelido like ? or instituicao like ?)"
            args += [f"%{busca}%"] * 2
        return [self._ser(r) for r in con.execute(sql + " order by id", args)]

    def _linha(self, con, id_):
        try:
            r = con.execute("select * from conta where id=? and excluido_em is null", (int(id_),)).fetchone()
        except ValueError:
            r = None
        if r is None:
            raise erro(404, "nao_encontrado", f"conta {id_} não existe")
        return r

    def obter(self, con, id_):
        return self._ser(self._linha(con, id_))

    def criar(self, con, corpo, quem, tipo):
        _so(corpo, {"apelido", "instituicao", "tipo"})
        apelido, inst = _texto(corpo, "apelido", True), _texto(corpo, "instituicao")
        if corpo.get("tipo") not in ("BANK", "CREDIT"):
            raise erro(400, "requisicao_invalida", "tipo deve ser BANK ou CREDIT")

        def fazer():
            n = con.execute("select count(*) from conta where externo_id like 'manual-%'").fetchone()[0] + 1
            cid = con.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values (?,?,?,?, 'a_decidir')",
                              (f"manual-{n}", inst, corpo["tipo"], apelido)).lastrowid
            _auditar(con, quem, tipo, cid, "criada")
            return cid
        return self.obter(con, _tx(con, fazer))

    def atualizar(self, con, id_, corpo, quem, tipo):
        atual = self._linha(con, id_)
        _so(corpo, {"apelido", "estado", "pj", "nibo_account_id", "usuarios"})  # instituição e tipo vêm da fonte e não se editam
        if not corpo:
            raise erro(400, "requisicao_invalida", "informe ao menos um campo")
        if "estado" in corpo and corpo["estado"] not in ESTADOS_CONTA:
            raise erro(400, "requisicao_invalida", f"estado deve ser um de {sorted(ESTADOS_CONTA)}")
        if "pj" in corpo and not isinstance(corpo["pj"], bool):
            raise erro(400, "requisicao_invalida", "pj deve ser true ou false")
        usuarios = atual["usuarios"]
        if "usuarios" in corpo:
            u = corpo["usuarios"]
            if not isinstance(u, list) or len(set(u)) != len(u) or not all(_pessoa_existe(con, p) for p in u):
                raise erro(400, "requisicao_invalida", "usuarios deve ser uma lista, sem repetição, de pessoas cadastradas")
            usuarios = json.dumps(u, ensure_ascii=False) if u else None
        vals = {"apelido": _texto(corpo, "apelido", True) if "apelido" in corpo else atual["apelido"], "estado": corpo.get("estado", atual["estado"]),
                "pj": int(corpo["pj"]) if "pj" in corpo else atual["pj"], "nibo_account_id": _texto(corpo, "nibo_account_id") if "nibo_account_id" in corpo else atual["nibo_account_id"],
                "usuarios": usuarios}

        def fazer():
            con.execute("update conta set apelido=?, estado=?, pj=?, nibo_account_id=?, usuarios=? where id=?", (*vals.values(), atual["id"]))
            _auditar(con, quem, tipo, atual["id"], "alterada")
        _tx(con, fazer)
        return self.obter(con, id_)

    def excluir(self, con, id_, quem, tipo):
        atual = self._linha(con, id_)

        def fazer():
            con.execute("update conta set excluido_em=datetime('now') where id=?", (atual["id"],))
            _auditar(con, quem, tipo, atual["id"], "excluída")
        _tx(con, fazer)
        return {"id": atual["id"], "excluido": True}


# ---------------- compromissos (substituem a planilha) ----------------
CAMPOS_COMPROMISSO = {"id", "nome", "extrato", "apelidos", "vencimento", "ajuste_dia_util", "valor_tipo", "valor_padrao", "forma", "conta", "cartao",
                      "documento", "pix", "ativo", "valido_de", "valido_ate", "obs"}


class Compromissos:
    def __init__(self):
        self.recalcular = None  # preenchido na montagem: (con, request) -> None

    def _ser(self, r):
        return {"id": r["id"], "nome": r["nome"], "extrato": r["extrato"], "apelidos": json.loads(r["apelidos"]), "vencimento": r["vencimento"],
                "ajuste_dia_util": r["ajuste_dia_util"], "valor_tipo": r["valor_tipo"],
                "valor_padrao": None if r["valor_padrao_centavos"] is None else formatar(r["valor_padrao_centavos"]), "forma": r["forma"], "conta": r["conta"],
                "cartao": r["cartao"], "documento": r["documento"], "pix": r["pix"], "ativo": bool(r["ativo"]), "valido_de": r["valido_de"],
                "valido_ate": r["valido_ate"], "obs": r["obs"], "excluido_em": r["excluido_em"]}

    def listar(self, con, busca, incluir):
        sql = "select * from compromisso_linha where 1=1" + ("" if incluir else " and excluido_em is null")
        args = []
        if busca:
            sql += " and (nome like ? or extrato like ?)"
            args += [f"%{busca}%"] * 2
        return [self._ser(r) for r in con.execute(sql + " order by coalesce(linha_planilha, 1000000 + rowid), id", args)]

    def obter(self, con, id_):
        r = con.execute("select * from compromisso_linha where id=? and excluido_em is null", (id_,)).fetchone()
        if r is None:
            raise erro(404, "nao_encontrado", f"compromisso {id_} não existe")
        return self._ser(r)

    def _validar(self, con, d: dict, proprio: str | None):
        """Passa pela MESMA validação da planilha; devolve a linha normalizada ou levanta 400 com o motivo."""
        cols = planilha.COLUNAS_COMPROMISSOS
        apelidos = d.get("apelidos") or []
        if not isinstance(apelidos, list) or not all(isinstance(a, str) for a in apelidos):
            raise erro(400, "requisicao_invalida", "apelidos deve ser uma lista de textos")
        v = {**d, "apelidos": "; ".join(apelidos), "ativo": "sim"}  # a validação das regras vale mesmo para linha desativada
        celulas = ["" if v.get(c) is None else v.get(c) for c in cols]
        idx = {c: i for i, c in enumerate(cols)}
        linha, motivo = planilha._linha(idx, 2, celulas)
        if linha is None:
            raise erro(400, "requisicao_invalida", motivo or "linha inválida")
        for o in con.execute("select id, valido_de, valido_ate from compromisso_linha where excluido_em is null and id<>?", (proprio or "",)):
            if _serie(o["id"]) == _serie(linha["id"]) and planilha._meses_sobrepoe(linha, {"valido_de": o["valido_de"], "valido_ate": o["valido_ate"]}):
                raise erro(400, "requisicao_invalida", f"os meses de validade se sobrepõem aos de {o['id']}")
        return linha

    def _gravar(self, con, linha, ativo: bool, obs, inserir: bool):
        args = (linha["nome"], linha["extrato"], json.dumps(linha["apelidos"], ensure_ascii=False), linha["vencimento"], linha["ajuste_dia_util"],
                linha["valor_tipo"], None if linha["valor_padrao"] is None else para_centavos(round(linha["valor_padrao"], 2)), linha["forma"],
                linha["conta"], linha["cartao"], linha["documento"], linha["pix"], int(ativo), linha["valido_de"], linha["valido_ate"], obs)
        if inserir:
            con.execute("insert into compromisso_linha(id, nome, extrato, apelidos, vencimento, ajuste_dia_util, valor_tipo, valor_padrao_centavos, forma, conta, cartao, "
                        "documento, pix, ativo, valido_de, valido_ate, obs) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (linha["id"], *args))
        else:
            con.execute("update compromisso_linha set nome=?, extrato=?, apelidos=?, vencimento=?, ajuste_dia_util=?, valor_tipo=?, valor_padrao_centavos=?, forma=?, "
                        "conta=?, cartao=?, documento=?, pix=?, ativo=?, valido_de=?, valido_ate=?, obs=? where id=?", (*args, linha["id"]))

    def criar(self, con, corpo, quem, tipo):
        _so(corpo, CAMPOS_COMPROMISSO)
        if not isinstance(corpo.get("ativo", True), bool):
            raise erro(400, "requisicao_invalida", "ativo deve ser true ou false")
        nome = _texto(corpo, "nome", True)
        dado = {**corpo}
        if corpo.get("id"):
            if con.execute("select 1 from compromisso_linha where id=?", (corpo["id"],)).fetchone():
                raise erro(409, "conflito", f"já existe o compromisso {corpo['id']}")
        else:
            dado["id"] = _id_unico(con, "compromisso_linha", _slug(nome))
        linha = self._validar(con, dado, None)

        def fazer():
            self._gravar(con, linha, corpo.get("ativo", True), corpo.get("obs"), True)
            _auditar(con, quem, tipo, linha["id"], "criada")
        _tx(con, fazer)
        return linha["id"]

    def atualizar(self, con, id_, corpo, quem, tipo):
        atual = self.obter(con, id_)
        _so(corpo, CAMPOS_COMPROMISSO - {"id"})
        if not corpo:
            raise erro(400, "requisicao_invalida", "informe ao menos um campo")
        if "ativo" in corpo and not isinstance(corpo["ativo"], bool):
            raise erro(400, "requisicao_invalida", "ativo deve ser true ou false")
        mesclado = {**atual, **corpo}
        linha = self._validar(con, mesclado, id_)

        def fazer():
            self._gravar(con, linha, mesclado["ativo"], mesclado.get("obs"), False)
            _auditar(con, quem, tipo, id_, "alterada")
        _tx(con, fazer)
        return id_

    def excluir(self, con, id_, quem, tipo):
        self.obter(con, id_)

        def fazer():
            con.execute("update compromisso_linha set excluido_em=datetime('now') where id=?", (id_,))
            _auditar(con, quem, tipo, id_, "excluída")
        _tx(con, fazer)
        return {"id": id_, "excluido": True}


COMPROMISSOS = Compromissos()
TIPOS = {"empresas": Simples("empresa", ("nome", "cnpj", "dados"), relacao=True), "pessoas": Simples("pessoa", ("nome", "papel", "telefone", "dados")),
         "categorias": Categorias(), "contas": Contas(), "compromissos": COMPROMISSOS}


def _tipo(t: str):
    if t not in TIPOS:
        raise erro(404, "nao_encontrado", f"cadastro {t!r} não existe")
    return TIPOS[t]


def _recalcular(con, request):
    """A agenda do mês depende dos compromissos: recalcula; falha aqui não desfaz o cadastro (já gravado)."""
    try:
        agora = _agora(request)
        cp.atualizar_compromissos(con, agora.date(), agora)
    except Exception:
        log.exception("falha ao recalcular compromissos após mudança de cadastro")


# ---------------- equivalência de categorias (declaradas ANTES das rotas genéricas) ----------------
@router.get("/categorias/equivalencias")
def equivalencias(request: Request):
    """Equivalência entre a categoria do banco (Pluggy) e a nossa."""
    con = _con(request)
    try:
        return envelope(con, {"itens": [{"origem_pluggy": r[0], "categoria_id": r[1]} for r in con.execute("select origem_pluggy, categoria_id from equivalencia_categoria order by origem_pluggy")]},
                        agora=_agora(request))
    finally:
        con.close()


@router.get("/categorias/equivalencias/pendentes")
def equivalencias_pendentes(request: Request):
    """Categorias do banco que aparecem nos lançamentos e ainda não têm equivalência, as de maior volume primeiro."""
    con = _con(request)
    try:
        itens = [{"origem_pluggy": r[0], "lancamentos": r[1]} for r in con.execute(
            "select categoria_banco, count(*) as n from lancamento where categoria_banco is not null "
            "and categoria_banco not in (select origem_pluggy from equivalencia_categoria) group by 1 order by n desc, 1")]
        return envelope(con, {"itens": itens}, agora=_agora(request))
    finally:
        con.close()


@router.put("/categorias/equivalencias")
async def equivalencia_definir(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Cria ou troca uma equivalência de categoria."""
    corpo = _corpo(await _json(request))
    _so(corpo, {"origem_pluggy", "categoria_id"})
    origem = _texto(corpo, "origem_pluggy", True)
    con = _con(request)
    try:
        cat = corpo.get("categoria_id")
        if isinstance(cat, bool) or not isinstance(cat, int) or con.execute("select 1 from categoria where id=? and excluido_em is null", (cat,)).fetchone() is None:
            raise erro(400, "requisicao_invalida", f"categoria_id={cat!r} não existe")

        def fazer():
            con.execute("insert into equivalencia_categoria(origem_pluggy, categoria_id) values (?,?) on conflict(origem_pluggy) do update set categoria_id=excluded.categoria_id", (origem, cat))
            _auditar(con, ident.login, "categorias/equivalencias", origem, "alterada")
        _tx(con, fazer)
        return envelope(con, {"origem_pluggy": origem, "categoria_id": cat}, agora=_agora(request))
    finally:
        con.close()


@router.delete("/categorias/equivalencias/{origem}")
def equivalencia_excluir(origem: str, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Remove uma equivalência de categoria."""
    con = _con(request)
    try:
        if con.execute("select 1 from equivalencia_categoria where origem_pluggy=?", (origem,)).fetchone() is None:
            raise erro(404, "nao_encontrado", f"não há equivalência para {origem!r}")

        def fazer():
            con.execute("delete from equivalencia_categoria where origem_pluggy=?", (origem,))
            _auditar(con, ident.login, "categorias/equivalencias", origem, "excluída")
        _tx(con, fazer)
        return {"origem_pluggy": origem, "excluido": True}
    finally:
        con.close()


# ---------------- CPF/documento (só mascarado; consulta auditada) ----------------
@router.get("/pessoas/{pid}/cpf")
def pessoa_cpf(pid: str, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Documentos da pessoa (sempre mascarados); a consulta fica auditada."""
    con = _con(request)
    try:
        p = con.execute("select dados from pessoa where id=? and excluido_em is null", (pid,)).fetchone()
        if p is None:
            raise erro(404, "nao_encontrado", f"pessoa {pid} não existe")
        docs = [{"tipo": d["tipo"].upper(), "numero": mascarar_documento(d["numero"])} for d in con.execute(
            "select tipo, numero from familia_documento where pessoa_id=? and excluido_em is null order by id", (pid,))]
        _tx(con, lambda: _auditar(con, ident.login, "pessoas", pid, "documento consultado"))
        return envelope(con, {"id": pid, "documentos": docs, "mascarado": True}, agora=_agora(request))
    finally:
        con.close()


# ---------------- CRUD genérico ----------------
# ---------------- cobrança: sócio do Nibo e liberação de dado sensível (Fase 2) ----------------
@router.get("/nibo")
def nibo_ler(request: Request):
    """Parâmetros do Nibo: id do sócio (stakeholder) usado no lote diário."""
    con = _con(request)
    try:
        r = con.execute("select valor from parametro where chave='nibo_socio_id'").fetchone()
        return envelope(con, {"socio_id": json.loads(r["valor"]) if r else None}, agora=_agora(request))
    finally:
        con.close()


@router.put("/nibo")
async def nibo_definir(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Define o id do sócio no Nibo (stakeholderId), necessário para o lote "Lançar na PJ"."""
    corpo = _corpo(await _json(request))
    _so(corpo, {"socio_id"})
    socio = _texto(corpo, "socio_id", True)
    con = _con(request)
    try:
        def fazer():
            con.execute("insert into parametro(chave, valor) values ('nibo_socio_id', ?) on conflict(chave) do update set valor=excluded.valor", (json.dumps(socio),))
            _auditar(con, ident.login, "nibo", "socio_id", "definido")
        _tx(con, fazer)
        return envelope(con, {"socio_id": socio}, agora=_agora(request))
    finally:
        con.close()




@router.get("/{tipo}")
def listar(tipo: str, request: Request, busca: str | None = None, incluir_excluidos: bool = False):
    """Lista um cadastro: empresas, contas, pessoas, compromissos ou categorias."""
    t = _tipo(tipo)
    con = _con(request)
    try:
        return envelope(con, {"itens": t.listar(con, busca, incluir_excluidos)}, agora=_agora(request))
    finally:
        con.close()


@router.get("/{tipo}/{id_}")
def obter(tipo: str, id_: str, request: Request):
    """Um item de cadastro."""
    t = _tipo(tipo)
    con = _con(request)
    try:
        return envelope(con, t.obter(con, id_), agora=_agora(request))
    finally:
        con.close()


@router.post("/{tipo}", status_code=201)
async def criar(tipo: str, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Cria um item de cadastro."""
    t = _tipo(tipo)
    corpo = _corpo(await _json(request))
    con = _con(request)
    try:
        r = t.criar(con, corpo, ident.login, tipo)
        if tipo == "compromissos":
            _recalcular(con, request)
            r = t.obter(con, r)
        return envelope(con, r, agora=_agora(request))
    finally:
        con.close()


@router.patch("/{tipo}/{id_}")
async def atualizar(tipo: str, id_: str, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Atualiza campos de um item de cadastro."""
    t = _tipo(tipo)
    corpo = _corpo(await _json(request))
    con = _con(request)
    try:
        r = t.atualizar(con, id_, corpo, ident.login, tipo)
        if tipo == "compromissos":
            _recalcular(con, request)
            r = t.obter(con, id_)
        return envelope(con, r, agora=_agora(request))
    finally:
        con.close()


@router.delete("/{tipo}/{id_}")
def excluir(tipo: str, id_: str, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Exclusão lógica de um item de cadastro (nada é apagado)."""
    t = _tipo(tipo)
    con = _con(request)
    try:
        r = t.excluir(con, id_, ident.login, tipo)
        if tipo == "compromissos":
            _recalcular(con, request)
        return envelope(con, r, agora=_agora(request))
    finally:
        con.close()
