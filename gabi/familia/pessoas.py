"""Pessoa e pet ditados ao Hermes, gravados de verdade, com histórico e desfazer.
Consome: pessoa, pet, pessoa_historico (0077), gabi.familia.contato, gabi.familia.fichas.resolver_pessoa; grava em decisao
(origem 'familia', só id, campo e ação). Pessoa nova: linha 'criada' no histórico; pet: linha 'pet:<id>' na pessoa 'pets'."""
import datetime as dt
import json

from gabi.db import transacao
from gabi.envios.propostas import normalizar_nome
from gabi.familia import contato
from gabi.familia.fichas import ErroFamilia, resolver_pessoa

CAMPOS_PESSOA = ("parentesco", "apelido", "nascimento", "observacao")
DADOS_PET = ("raca", "nascimento", "dono")


def _slug(texto: str) -> str:
    return "-".join(normalizar_nome(texto).split())


def _resolver(con, texto: str) -> str | None:
    """Id da pessoa que casa; None se ninguém casar; `pessoa_ambigua` (com candidatos) propagado."""
    try:
        return resolver_pessoa(con, texto)
    except ErroFamilia as e:
        if e.codigo == "pessoa_ambigua" and not e.candidatos:
            return None
        raise


def _livre(con, tabela: str, *ids: str) -> str:
    """Primeiro id sem linha (excluídas contam); esgotados, o último com sufixo -2, -3..."""
    existe = lambda i: con.execute(f"select 1 from {tabela} where id=?", (i,)).fetchone() is not None
    for i in ids:
        if not existe(i):
            return i
    n = 2
    while existe(f"{ids[-1]}-{n}"):
        n += 1
    return f"{ids[-1]}-{n}"


def registrar_pessoa(con, *, nome: str, parentesco: str, apelido: str = "", nascimento: str = "", falecido: bool = False,
                     observacao: str = "", quem: str, agora: dt.datetime) -> dict:
    """Acha a pessoa pelo nome (ou apelido) ou cria; aplica os campos não vazios, só os que mudam. Tudo numa transação."""
    nome = contato._texto(nome)
    if not isinstance(falecido, bool):
        raise ErroFamilia("valor_invalido")
    campos = [(c, contato.validar(c, "definir", v)) for c, v in zip(CAMPOS_PESSOA, (parentesco, apelido, nascimento, observacao))
              if not (isinstance(v, str) and not v.strip())] + ([("falecido", True)] if falecido else [])
    with transacao(con, imediata=True):
        pid = _resolver(con, nome)
        if pid is None and isinstance(apelido, str) and apelido.strip():
            pid = _resolver(con, apelido)
        criada = pid is None
        if criada:
            pid = _livre(con, "pessoa", _slug(nome.split()[0]), _slug(nome))
            con.execute("insert into pessoa(id, nome, papel, dados, origem) values (?,?, 'familia', ?, 'hermes')",
                        (pid, nome.split()[0], json.dumps({"nome_completo": nome}, ensure_ascii=False)))
            contato._historico(con, pid, "criada", None, {"nome": nome}, quem, agora)
            contato._auditar(con, quem, agora, pid, "criada", "criar")
        mudancas = []
        for campo, valor in campos:
            if contato._atual(contato._dados_da(con, pid), campo) == valor:
                continue
            r = contato._aplicar(con, pid, campo, "definir", valor, quem, agora)
            mudancas.append({"campo": campo, **r})
    return {"pessoa_id": pid, "criada": criada, "mudancas": mudancas}


def _pet(con, pet_id: str) -> dict | None:
    r = con.execute("select * from pet where id=?", (pet_id,)).fetchone()
    if r is None:
        return None
    try:
        d = json.loads(r["dados"]) if r["dados"] else {}
    except (TypeError, ValueError):
        d = {}
    d = d if isinstance(d, dict) else {}
    return {"id": r["id"], "nome": r["nome"], "especie": r["especie"], **{k: d.get(k) for k in DADOS_PET}}


def _gravar_pet(con, pet: dict) -> None:
    """Grava o dict do pet; as outras chaves de `dados` (legado) ficam como estão."""
    r = con.execute("select dados from pet where id=?", (pet["id"],)).fetchone()
    try:
        d = json.loads(r["dados"]) if r and r["dados"] else {}
    except (TypeError, ValueError):
        d = {}
    d = d if isinstance(d, dict) else {}
    for k in DADOS_PET:
        contato._colocar(d, k, pet.get(k))
    dados = json.dumps(d, ensure_ascii=False)
    if r is None:
        con.execute("insert into pet(id, nome, especie, dados, origem) values (?,?,?,?,'hermes')",
                    (pet["id"], pet["nome"], pet["especie"], dados))
    else:
        con.execute("update pet set nome=?, especie=?, dados=? where id=?", (pet["nome"], pet["especie"], dados, pet["id"]))


def _garantir_pets(con) -> None:
    con.execute("insert or ignore into pessoa(id, nome, papel, dados, origem) values ('pets','Pets','pets','{}','sistema')")


def registrar_pet(con, *, nome: str, especie: str, raca: str = "", nascimento: str = "", dono: str = "", quem: str,
                  agora: dt.datetime) -> dict:
    """Cria ou atualiza o pet (mesmo nome, sem caixa e acento, é o mesmo pet); campo vazio fica como está. Uma transação."""
    nome = contato._texto(nome)
    novos = {"especie": especie, "raca": raca}
    novos = {k: contato._texto(v) for k, v in novos.items() if not (isinstance(v, str) and not v.strip())}
    if not (isinstance(nascimento, str) and not nascimento.strip()):
        novos["nascimento"] = contato.data(nascimento)
    with transacao(con, imediata=True):
        if isinstance(dono, str) and dono.strip():
            novos["dono"] = resolver_pessoa(con, dono)
        alvo = normalizar_nome(nome)
        pet_id = next((r["id"] for r in con.execute("select id, nome from pet order by id") if normalizar_nome(r["nome"]) == alvo), None)
        antes = _pet(con, pet_id) if pet_id else None
        if antes is None:
            if "especie" not in novos:
                raise ErroFamilia("valor_invalido")
            pet_id = _livre(con, "pet", _slug(nome))
        depois = {**(antes or {"id": pet_id, **{k: None for k in DADOS_PET}}), "nome": nome, **novos}
        hid = None
        if depois != antes:
            _gravar_pet(con, depois)
            _garantir_pets(con)
            hid = contato._historico(con, "pets", f"pet:{pet_id}", antes, depois, quem, agora)
            contato._auditar(con, quem, agora, "pets", f"pet:{pet_id}", "definir")
    return {"pet_id": pet_id, "criado": antes is None, "historico_id": hid}


def listar_pets(con) -> list[dict]:
    """Pets por nome: id, nome, espécie, raça, nascimento e dono (pessoa_id)."""
    return [_pet(con, r["id"]) for r in con.execute("select id from pet order by nome, id")]


def desfazer_especial(con, h, quem: str, agora: dt.datetime) -> dict:
    """Desfaz 'criada' (exclui a pessoa; refaz se a linha for o próprio desfazer) e 'pet:<id>' (restaura o pet, apaga se
    não existia). Chamado por `contato.desfazer` dentro da transação dele, que grava o histórico e a auditoria."""
    depois, antes = json.loads(h["depois"]), json.loads(h["antes"])
    if h["campo"] == "criada":
        r = con.execute("select excluido_em from pessoa where id=?", (h["pessoa_id"],)).fetchone()
        posterior = con.execute("select 1 from pessoa_historico where pessoa_id=? and id>? and desfeito_em is null",
                                (h["pessoa_id"], h["id"])).fetchone()
        if r is None or posterior or (r["excluido_em"] is None) != (depois is not None):
            raise ErroFamilia("conflito")
        con.execute("update pessoa set excluido_em=? where id=?", (None if antes else contato._ts(agora), h["pessoa_id"]))
        return {"antes": depois, "depois": antes}
    atual = _pet(con, h["campo"][4:])
    if atual != depois:
        raise ErroFamilia("conflito")
    if antes is None:
        con.execute("delete from pet where id=?", (h["campo"][4:],))
    else:
        _gravar_pet(con, antes)
    return {"antes": atual, "depois": antes}
