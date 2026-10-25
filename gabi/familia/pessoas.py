"""Pessoa e pet ditados ao Hermes, gravados de verdade, com histórico e desfazer.
Consome: pessoa, pet, pessoa_historico (0077), gabi.familia.contato, gabi.familia.fichas.resolver_pessoa; grava em decisao
(origem 'familia', só id, campo e ação). Pessoa nova: linha 'criada' no histórico; pet: linha 'pet:<id>' na pessoa 'pets'."""
import datetime as dt
import json
import re

from gabi.db import transacao
from gabi.envios.propostas import normalizar_nome
from gabi.familia import contato
from gabi.familia.fichas import ErroFamilia, resolver_pessoa, rotulo

CAMPOS_PESSOA = ("parentesco", "apelido", "nascimento", "observacao")
DADOS_PET = ("raca", "nascimento", "dono")
LEGADO_PET = {"dono": "tutor", "nascimento": "aniversario"}  # chaves antigas da carga, lidas quando as novas faltam


def _slug(texto: str) -> str:
    """Só [a-z0-9-], sem hífen repetido nem nas pontas; vazio é `valor_invalido`."""
    s = re.sub(r"[^a-z0-9]+", "-", normalizar_nome(texto)).strip("-")
    if not s:
        raise ErroFamilia("valor_invalido")
    return s


def _sem_nome_completo(d) -> bool:
    return isinstance(d, dict) and not (isinstance(d.get("nome_completo"), str) and d["nome_completo"].strip())


def _ler(dados) -> dict | None:
    try:
        return json.loads(dados) if dados else {}
    except (TypeError, ValueError):
        return None


def _palavras(*textos) -> set[str]:
    return {p for t in textos if isinstance(t, str) for p in normalizar_nome(t).split()}


def _resolver(con, texto: str) -> str | None:
    """Id da pessoa que casa por igual ou começo de palavra (`resolver_pessoa`); sem isso, quem tem a mesma primeira palavra
    (no nome, nome completo ou apelido) e todas as palavras ditadas entre as suas ("Louise Esper" para "Louise Lavrik Esper",
    "Gigi Esper" para a Giovanna de apelido Gigi), ou quem não tem nome completo e cujo `nome` abre o texto ("Chafic" para
    "Chafic Esper"). None se ninguém casar; mais de um, `pessoa_ambigua` com os candidatos."""
    try:
        return resolver_pessoa(con, texto, parcial=False)
    except ErroFamilia as e:
        if e.codigo != "pessoa_ambigua" or e.candidatos:
            raise
    alvo = normalizar_nome(texto)
    ditas = alvo.split()
    if not ditas:
        return None
    achados = []
    for r in con.execute("select id, nome, dados from pessoa where excluido_em is null and coalesce(papel,'')<>'pets' order by id"):
        d = _ler(r["dados"])
        nomes = [v for v in (r["nome"], *((d.get("nome_completo"), d.get("apelido")) if isinstance(d, dict) else ()))
                 if isinstance(v, str) and normalizar_nome(v)]
        encurtado = ditas[0] in {normalizar_nome(v).split()[0] for v in nomes} and set(ditas) <= _palavras(*nomes)
        estende = bool(normalizar_nome(r["nome"])) and alvo.startswith(normalizar_nome(r["nome"]) + " ") and _sem_nome_completo(d)
        if encurtado or estende:
            achados.append((r["id"], rotulo(r["nome"], d)))
    if len(achados) > 1:
        raise ErroFamilia("pessoa_ambigua", candidatos=[n for _, n in achados])
    return achados[0][0] if achados else None


def _linha(con, pid: str):
    r = con.execute("select nome, papel, dados from pessoa where id=?", (pid,)).fetchone()
    d = _ler(r["dados"])
    return r, (d if isinstance(d, dict) else {})


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
    ids = (_slug(nome.split()[0]), _slug(nome))
    with transacao(con, imediata=True):
        pid = _resolver(con, nome)
        if pid is None and isinstance(apelido, str) and apelido.strip():
            pid = _resolver(con, apelido)
            if pid is not None:  # o apelido casou: o nome ditado não pode contradizer o cadastro
                r, d = _linha(con, pid)
                if normalizar_nome(nome).split()[0] not in _palavras(r["nome"], d.get("nome_completo"), d.get("apelido")):
                    raise ErroFamilia("pessoa_ambigua", candidatos=[rotulo(r["nome"], d)])
        if pid is not None:
            r, d = _linha(con, pid)
            if r["papel"] == "titular":  # a ficha do Ricardo nunca é escrita por aqui; o Hermes pergunta
                raise ErroFamilia("pessoa_ambigua", candidatos=[rotulo(r["nome"], d)])
        criada = pid is None
        if criada:
            pid = _livre(con, "pessoa", *ids)
            con.execute("insert into pessoa(id, nome, papel, dados, origem) values (?,?, 'familia', ?, 'hermes')",
                        (pid, nome.split()[0], json.dumps({"nome_completo": nome}, ensure_ascii=False)))
            contato._historico(con, pid, "criada", None, {"nome": nome}, quem, agora)
            contato._auditar(con, quem, agora, pid, "criada", "criar")
        mudancas = []
        dados = contato._dados_da(con, pid)
        linha = con.execute("select nome from pessoa where id=?", (pid,)).fetchone()
        if not criada and _sem_nome_completo(dados) and normalizar_nome(nome).startswith(normalizar_nome(linha["nome"]) + " "):
            antes = dados.get("nome_completo")  # sem campo próprio em contato: grava aqui, desfazível pelo desfazer comum
            dados["nome_completo"] = nome
            contato._gravar(con, pid, dados)
            hid = contato._historico(con, pid, "nome_completo", antes, nome, quem, agora)
            contato._auditar(con, quem, agora, pid, "nome_completo", "definir")
            mudancas.append({"campo": "nome_completo", "antes": antes, "depois": nome, "historico_id": hid})
        for campo, valor in campos:
            if contato._atual(contato._dados_da(con, pid), campo) == valor:
                continue
            r = contato._aplicar(con, pid, campo, "definir", valor, quem, agora)
            mudancas.append({"campo": campo, **r})
        r, d = _linha(con, pid)
    return {"pessoa_id": pid, "nome": r["nome"], "nome_completo": d.get("nome_completo") or None, "criada": criada,
            "mudancas": mudancas}


def _pet(con, pet_id: str) -> dict | None:
    r = con.execute("select * from pet where id=?", (pet_id,)).fetchone()
    if r is None:
        return None
    try:
        d = json.loads(r["dados"]) if r["dados"] else {}
    except (TypeError, ValueError):
        d = {}
    d = d if isinstance(d, dict) else {}
    return {"id": r["id"], "nome": r["nome"], "especie": r["especie"],
            **{k: d.get(k) if d.get(k) is not None else d.get(LEGADO_PET.get(k, k)) for k in DADOS_PET}}


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
    slug = _slug(nome)
    novos = {"especie": especie, "raca": raca}
    novos = {k: contato._texto(v) for k, v in novos.items() if not (isinstance(v, str) and not v.strip())}
    if not (isinstance(nascimento, str) and not nascimento.strip()):
        novos["nascimento"] = contato.data(nascimento)
    with transacao(con, imediata=True):
        if isinstance(dono, str) and dono.strip():
            novos["dono"] = _resolver(con, dono)
            if novos["dono"] is None:
                raise ErroFamilia("pessoa_ambigua", candidatos=[])
        alvo = normalizar_nome(nome)
        pet_id = next((r["id"] for r in con.execute("select id, nome from pet order by id") if normalizar_nome(r["nome"]) == alvo), None)
        antes = _pet(con, pet_id) if pet_id else None
        if antes is None:
            if "especie" not in novos:
                raise ErroFamilia("valor_invalido")
            pet_id = _livre(con, "pet", slug)
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


def _vazio(v):
    return None if v is None or v == [] else v


def _criacao_intacta(con, h) -> bool:
    """A pessoa ainda está como a chamada da criação a deixou? Só contam os campos tocados por linhas posteriores a essa
    chamada (desfeitas ou não); cada um precisa estar no valor que a criação gravou, ou vazio de novo (nada se perde ao
    excluir). As linhas da própria chamada (mesmo quem e quando da 'criada') definem os valores da criação."""
    criacao = {"nome_completo": (json.loads(h["depois"]) or {}).get("nome")}
    tocados = set()
    for x in con.execute("select campo, depois, quem, quando from pessoa_historico where pessoa_id=? and id>? and campo<>'criada'"
                         " order by id", (h["pessoa_id"], h["id"])):
        if (x["quem"], x["quando"]) == (h["quem"], h["quando"]) and not tocados:
            criacao[x["campo"]] = json.loads(x["depois"])
        else:
            tocados.add(x["campo"])
    dados = contato._dados_da(con, h["pessoa_id"])
    return all(_vazio(dados.get(c)) in (None, _vazio(criacao.get(c))) for c in tocados)


def desfazer_especial(con, h, quem: str, agora: dt.datetime) -> dict:
    """Desfaz 'criada' (exclui a pessoa e marca desfeitas as linhas da mesma chamada; refaz se a linha for o próprio desfazer) e 'pet:<id>' (restaura o pet, apaga se
    não existia). Chamado por `contato.desfazer` dentro da transação dele, que grava o histórico e a auditoria.
    Excluir só vale se a pessoa ainda estiver como a criação a deixou (`_criacao_intacta`): mudança posterior desfeita não
    bloqueia; mudança posterior que ficou devolve `conflito`. As linhas posteriores ficam como estão (a exclusão não mexe em `dados`)."""
    depois, antes = json.loads(h["depois"]), json.loads(h["antes"])
    if h["campo"] == "criada":
        r = con.execute("select excluido_em from pessoa where id=?", (h["pessoa_id"],)).fetchone()
        if r is None or (r["excluido_em"] is None) != (depois is not None):
            raise ErroFamilia("conflito")
        if depois is not None:
            if not _criacao_intacta(con, h):
                raise ErroFamilia("conflito")
            con.execute("update pessoa_historico set desfeito_em=? where pessoa_id=? and id>? and desfeito_em is null and quem=?"
                        " and quando=?", (contato._ts(agora), h["pessoa_id"], h["id"], h["quem"], h["quando"]))
        elif con.execute("select 1 from pessoa_historico where pessoa_id=? and id>? and desfeito_em is null",
                         (h["pessoa_id"], h["id"])).fetchone():
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
