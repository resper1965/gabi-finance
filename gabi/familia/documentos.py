"""Propostas de documento da família: o Hermes e a carga propõem, o Ricardo aprova no painel.
Consome: pessoa, as visões familia_documento/familia_proposta (migração 0081), gabi.documentos.repositorio (grava a proposta e
decide; decisao com origem 'documentos'), gabi.mascara (dígito do CPF). Valida a entrada da família (TIPOS, ORIGENS) e mantém as
respostas de antes da 0081.
Proposta com campo opcional vazio não apaga o valor do documento ativo ao ser aprovada. A auditoria leva só ids, tipo e
estado, nunca o número; os erros têm código fixo. Documento ativo com "*" no número é "mascarado" (cópia de 08/10): a proposta
sem documento igual aponta para ele e aprovar grava também o número completo."""
import datetime as dt
import re

import json

from gabi.db import transacao
from gabi.documentos import repositorio
from gabi.documentos.repositorio import ErroDocumentos
from gabi.familia.fichas import ErroFamilia, normalizar_numero
from gabi.mascara import _cpf_valido

TIPOS = ("cpf", "rg", "cnh", "passaporte", "outro")
ORIGENS = ("hermes", "carga")
_PAIS = re.compile(r"^[A-Z]{2}$")
_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _data(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    try:
        if not (isinstance(v, str) and _DATA.match(v.strip())):
            raise ValueError
        dt.date.fromisoformat(v.strip())
    except ValueError:
        raise ErroFamilia("valor_invalido")
    return v.strip()


def _emissor(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if not isinstance(v, str) or len(v.strip()) > 200:
        raise ErroFamilia("valor_invalido")
    return v.strip()


def _paperless(v):
    if v is None or v == 0:
        return None
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        raise ErroFamilia("valor_invalido")
    return v


def _ativo(con, pessoa_id, tipo, pais, numero):
    alvo = normalizar_numero(numero)
    for d in con.execute("select * from familia_documento where pessoa_id=? and tipo=? and pais=? and excluido_em is null order by id",
                         (pessoa_id, tipo, pais)):
        if normalizar_numero(d["numero"]) == alvo:
            return d
    return None


def mascarado(numero) -> bool:
    return "*" in str(numero or "")


def _visiveis_batem(mascarado_numero, numero) -> bool:
    """Os dígitos visíveis do mascarado são o fim dos dígitos do número novo."""
    visiveis = re.sub(r"\D", "", str(mascarado_numero))
    return re.sub(r"\D", "", numero).endswith(visiveis)


def _mascarado(con, pessoa_id, tipo, pais, numero):
    """(mascarado ativo do mesmo tipo e país, dígitos visíveis batem?). Prefere o primeiro (por id) cujos dígitos visíveis
    são o fim do número novo; sem nenhum assim, o primeiro por id, com bate=False. (None, True) se não há mascarado."""
    mascarados = [d for d in con.execute("select * from familia_documento where pessoa_id=? and tipo=? and pais=? and excluido_em is null"
                                         " order by id", (pessoa_id, tipo, pais)) if mascarado(d["numero"])]
    for d in mascarados:
        if _visiveis_batem(d["numero"], numero):
            return d, True
    return (mascarados[0], False) if mascarados else (None, True)


def _doc(pessoa_id, tipo, pais, numero, emissor, emissao, validade) -> dict:
    return {"titular_tipo": "pessoa", "titular_id": pessoa_id, "tipo": tipo, "pais": pais, "emissor": emissor,
            "numeros": [{"nome": "numero", "valor": numero}],
            "datas": [{"tipo": t, "data": v} for t, v in (("emissao", emissao), ("validade", validade)) if v is not None]}


def propor(con, pessoa_id: str, *, tipo: str, numero: str, emissor=None, emissao=None, validade=None, pais: str = "BR",
           paperless_id=None, origem: str, conferir: bool = False, agora: dt.datetime) -> int | None:
    """Cria a proposta e devolve o id. None se o documento ativo já tem esses valores; se já há proposta aberta para a
    mesma pessoa, tipo e número, devolve o id dela; da carga, None se o mesmo número já foi recusado. CPF sem dígito
    verificador válido entra com conferir=1. Sem documento igual, aponta para o mascarado do mesmo tipo e país; dígitos
    visíveis que não batem com o fim do número dão conferir=1."""
    if tipo not in TIPOS:
        raise ErroFamilia("campo_invalido")
    if origem not in ORIGENS:
        raise ErroFamilia("requisicao_invalida")
    if not isinstance(numero, str) or not 1 <= len(numero.strip()) <= 40:
        raise ErroFamilia("valor_invalido")
    numero = numero.strip()
    pais = pais.strip().upper() if isinstance(pais, str) else ""
    if not _PAIS.match(pais):
        raise ErroFamilia("valor_invalido")
    emissor, emissao, validade, paperless_id = _emissor(emissor), _data(emissao), _data(validade), _paperless(paperless_id)
    if tipo == "cpf" and not _cpf_valido(re.sub(r"\D", "", numero)):
        conferir = True
    with transacao(con, imediata=True):
        if con.execute("select 1 from pessoa where id=? and excluido_em is null", (pessoa_id,)).fetchone() is None:
            raise ErroFamilia("nao_encontrado")
        alvo = normalizar_numero(numero)
        for p in con.execute("select id, numero from familia_proposta where pessoa_id=? and tipo=? and pais=? and estado='pendente'"
                             " order by id", (pessoa_id, tipo, pais)):
            if normalizar_numero(p["numero"]) == alvo:
                return p["id"]
        # A carga não repropõe o que o Ricardo já recusou (rodar de novo não desfaz a decisão); o Hermes pode.
        if origem == "carga" and any(normalizar_numero(p["numero"]) == alvo for p in con.execute(
                "select numero from familia_proposta where pessoa_id=? and tipo=? and pais=? and estado='recusada'", (pessoa_id, tipo, pais))):
            return None
        ativo = _ativo(con, pessoa_id, tipo, pais, numero)
        if ativo is not None:
            novos = {"emissor": emissor, "emissao": emissao, "validade": validade, "paperless_id": paperless_id}
            if all(v is None or v == ativo[c] for c, v in novos.items()):
                return None
        else:
            ativo, bate = _mascarado(con, pessoa_id, tipo, pais, numero)
            if not bate:
                conferir = True
        return repositorio.inserir_proposta(
            con, _doc(pessoa_id, tipo, pais, numero, emissor, emissao, validade), documento_id=ativo["id"] if ativo is not None else None,
            paperless_id=paperless_id, conferir=conferir, motivos=[], origem=origem, criada_em=repositorio.ts(agora))


def completar_proposta(con, proposta_id: int, *, validade=None, conferir=None, paperless_id=None) -> None:
    """Completa a proposta ainda pendente (validade, conferir, paperless_id), na transação do chamador (a carga)."""
    p = con.execute("select doc from documento_proposta where id=? and estado='pendente'", (proposta_id,)).fetchone()
    if p is None:
        return
    sets, args = [], []
    if validade is not None:
        doc = json.loads(p["doc"])
        doc["datas"] = [x for x in doc["datas"] if x["tipo"] != "validade"] + [{"tipo": "validade", "data": validade}]
        sets.append("doc=?")
        args.append(json.dumps(repositorio.validar(doc), ensure_ascii=False))
    for col, v in (("conferir", conferir), ("paperless_id", paperless_id)):
        if v is not None:
            sets.append(f"{col}=?")
            args.append(v)
    if sets:
        con.execute(f"update documento_proposta set {', '.join(sets)} where id=?", (*args, proposta_id))


def decidir(con, proposta_id: int, estado: str, quem: str, agora: dt.datetime) -> dict:
    """Aprova (cria ou atualiza o documento, na mesma transação) ou recusa (nada muda). Já decidida: `conflito`.
    Delegado ao repositório de documentos (que registra em decisao com origem 'documentos')."""
    try:
        r = repositorio.decidir(con, proposta_id, estado, quem, agora)
    except ErroDocumentos as e:
        raise ErroFamilia(e.codigo) from None
    return {"proposta_id": r["proposta_id"], "estado": r["estado"], "documento_id": r["documento_id"]}


_CAMPOS = ("tipo", "pais", "numero", "emissor", "emissao", "validade", "paperless_id")


def listar_propostas(con, estado: str = "pendente") -> list[dict]:
    """Propostas no estado dado, da mais antiga para a mais nova, com o documento `atual` (ou None) e o `proposto`."""
    if estado not in ("pendente", "aprovada", "recusada"):
        raise ErroFamilia("requisicao_invalida")
    saida = []
    for p in con.execute("select p.*, n.nome from familia_proposta p join pessoa n on n.id=p.pessoa_id where p.estado=? order by p.id", (estado,)):
        atual = None
        if p["documento_id"] is not None:
            d = con.execute("select * from familia_documento where id=?", (p["documento_id"],)).fetchone()
            if d is not None:
                atual = {c: d[c] for c in ("id", *_CAMPOS)}
        saida.append({"id": p["id"], "pessoa_id": p["pessoa_id"], "nome": p["nome"], "documento_id": p["documento_id"],
                      "origem": p["origem"], "conferir": bool(p["conferir"]), "estado": p["estado"], "criada_em": p["criada_em"],
                      "decidida_em": p["decidida_em"], "decidida_por": p["decidida_por"],
                      "atual": atual, "proposto": {c: p[c] for c in _CAMPOS}})
    return saida
