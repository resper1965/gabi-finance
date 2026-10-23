"""Propostas de documento da família: o Hermes e a carga propõem, o Ricardo aprova no painel.
Consome: pessoa, pessoa_documento e pessoa_proposta (migração 0077), gabi.mascara (dígito do CPF); grava em decisao (origem 'familia').
Proposta com campo opcional vazio não apaga o valor do documento ativo ao ser aprovada. A auditoria leva só ids, tipo e
estado, nunca o número; os erros têm código fixo. Documento ativo com "*" no número é "mascarado" (cópia de 08/10): a proposta
sem documento igual aponta para ele e aprovar grava também o número completo."""
import datetime as dt
import re

from gabi.db import transacao
from gabi.familia.contato import _ts
from gabi.familia.fichas import ErroFamilia, normalizar_numero
from gabi.mascara import _cpf_valido

TIPOS = ("cpf", "rg", "cnh", "passaporte", "outro")
ORIGENS = ("hermes", "carga")
ORIGEM_DOC = {"hermes": "ricardo", "carga": "carga"}
_PAIS = re.compile(r"^[A-Z]{2}$")
_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
OPCIONAIS = ("emissor", "emissao", "validade", "paperless_id")


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
    for d in con.execute("select * from pessoa_documento where pessoa_id=? and tipo=? and pais=? and excluido_em is null order by id",
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
    mascarados = [d for d in con.execute("select * from pessoa_documento where pessoa_id=? and tipo=? and pais=? and excluido_em is null"
                                         " order by id", (pessoa_id, tipo, pais)) if mascarado(d["numero"])]
    for d in mascarados:
        if _visiveis_batem(d["numero"], numero):
            return d, True
    return (mascarados[0], False) if mascarados else (None, True)


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
        for p in con.execute("select id, numero from pessoa_proposta where pessoa_id=? and tipo=? and pais=? and estado='pendente'"
                             " order by id", (pessoa_id, tipo, pais)):
            if normalizar_numero(p["numero"]) == alvo:
                return p["id"]
        # A carga não repropõe o que o Ricardo já recusou (rodar de novo não desfaz a decisão); o Hermes pode.
        if origem == "carga" and any(normalizar_numero(p["numero"]) == alvo for p in con.execute(
                "select numero from pessoa_proposta where pessoa_id=? and tipo=? and pais=? and estado='recusada'", (pessoa_id, tipo, pais))):
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
        return con.execute(
            "insert into pessoa_proposta(pessoa_id, documento_id, tipo, pais, numero, emissor, emissao, validade, paperless_id,"
            " origem, conferir, criada_em) values (?,?,?,?,?,?,?,?,?,?,?,?)",
            (pessoa_id, ativo["id"] if ativo is not None else None, tipo, pais, numero, emissor, emissao, validade,
             paperless_id, origem, 1 if conferir else 0, _ts(agora))).lastrowid


def decidir(con, proposta_id: int, estado: str, quem: str, agora: dt.datetime) -> dict:
    """Aprova (cria ou atualiza o documento, na mesma transação) ou recusa (nada muda). Já decidida: `conflito`."""
    if estado not in ("aprovada", "recusada"):
        raise ErroFamilia("requisicao_invalida")
    with transacao(con, imediata=True):
        p = con.execute("select * from pessoa_proposta where id=?", (proposta_id,)).fetchone()
        if p is None:
            raise ErroFamilia("nao_encontrado")
        if p["estado"] != "pendente":
            raise ErroFamilia("conflito")
        ts = _ts(agora)
        documento_id = None
        if estado == "aprovada":
            ativo = None
            if p["documento_id"] is not None:
                ativo = con.execute("select * from pessoa_documento where id=? and excluido_em is null", (p["documento_id"],)).fetchone()
                # O alvo só vale se ainda for mascarado ou tiver o mesmo número (outra proposta pode já ter trocado o
                # mascarado): senão um documento receberia os dados de outro.
                if ativo is not None and not (mascarado(ativo["numero"]) or normalizar_numero(ativo["numero"]) == normalizar_numero(p["numero"])):
                    ativo = None
            if ativo is None:
                ativo = _ativo(con, p["pessoa_id"], p["tipo"], p["pais"], p["numero"])
            if ativo is not None:
                # Campo vazio na proposta mantém o valor atual; o número fica como está (só muda a formatação), salvo
                # sobre o mascarado, que ganha o número completo.
                novos = {c: p[c] for c in OPCIONAIS if p[c] is not None}
                if mascarado(ativo["numero"]):
                    novos["numero"] = p["numero"]
                    novos["origem"] = ORIGEM_DOC[p["origem"]]  # o número completo veio da proposta, não é mais o legado
                sets = "".join(f"{c}=?, " for c in novos)
                con.execute(f"update pessoa_documento set {sets}atualizado_em=? where id=?", (*novos.values(), ts, ativo["id"]))
                documento_id = ativo["id"]
            else:
                documento_id = con.execute(
                    "insert into pessoa_documento(pessoa_id, tipo, pais, numero, emissor, emissao, validade, paperless_id, origem,"
                    " criado_em, atualizado_em) values (?,?,?,?,?,?,?,?,?,?,?)",
                    (p["pessoa_id"], p["tipo"], p["pais"], p["numero"], p["emissor"], p["emissao"], p["validade"],
                     p["paperless_id"], ORIGEM_DOC[p["origem"]], ts, ts)).lastrowid
        con.execute("update pessoa_proposta set estado=?, decidida_em=?, decidida_por=?, documento_id=coalesce(?, documento_id) where id=?",
                    (estado, ts, quem, documento_id, proposta_id))
        con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?,'familia')",
                    (ts, quem, f"Proposta {proposta_id} de documento ({p['tipo']}) da pessoa {p['pessoa_id']}: {estado}"))
    return {"proposta_id": proposta_id, "estado": estado, "documento_id": documento_id}


_CAMPOS = ("tipo", "pais", "numero", "emissor", "emissao", "validade", "paperless_id")


def listar_propostas(con, estado: str = "pendente") -> list[dict]:
    """Propostas no estado dado, da mais antiga para a mais nova, com o documento `atual` (ou None) e o `proposto`."""
    if estado not in ("pendente", "aprovada", "recusada"):
        raise ErroFamilia("requisicao_invalida")
    saida = []
    for p in con.execute("select p.*, n.nome from pessoa_proposta p join pessoa n on n.id=p.pessoa_id where p.estado=? order by p.id", (estado,)):
        atual = None
        if p["documento_id"] is not None:
            d = con.execute("select * from pessoa_documento where id=?", (p["documento_id"],)).fetchone()
            if d is not None:
                atual = {c: d[c] for c in ("id", *_CAMPOS)}
        saida.append({"id": p["id"], "pessoa_id": p["pessoa_id"], "nome": p["nome"], "documento_id": p["documento_id"],
                      "origem": p["origem"], "conferir": bool(p["conferir"]), "estado": p["estado"], "criada_em": p["criada_em"],
                      "decidida_em": p["decidida_em"], "decidida_por": p["decidida_por"],
                      "atual": atual, "proposto": {c: p[c] for c in _CAMPOS}})
    return saida
