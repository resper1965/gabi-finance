"""Contato da pessoa gravado direto, com histórico e desfazer.
Consome: pessoa (dados JSON), pessoa_historico (migração 0077), gabi.contatos.telefone; grava em decisao (origem 'familia').
Listas ficam em dados.telefones/emails/enderecos (os campos singulares legados nunca são alterados). A auditoria leva só
o id da pessoa, o campo e a ação, nunca o valor."""
import datetime as dt
import json
import re

from gabi.contatos.telefone import normalizar_telefone
from gabi.db import transacao
from gabi.familia.fichas import ErroFamilia

TEXTOS = ("apelido", "parentesco", "nascimento")
LISTAS = ("telefones", "emails", "enderecos")
MAX_ITENS = 10
MAX_TEXTO = 200
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _ts(agora: dt.datetime) -> str:
    if agora.tzinfo:
        agora = agora.astimezone(dt.timezone.utc)
    return agora.strftime("%Y-%m-%dT%H:%M:%SZ")


def _texto(valor, limite: int = MAX_TEXTO) -> str:
    if not isinstance(valor, str) or not valor.strip() or len(valor.strip()) > limite:
        raise ErroFamilia("valor_invalido")
    return valor.strip()


def _normalizar(campo: str, valor):
    """Valor válido e na forma gravada; `valor_invalido` senão."""
    if campo == "telefones":
        n = normalizar_telefone(valor) if isinstance(valor, str) else None
        if not n:
            raise ErroFamilia("valor_invalido")
        return n
    if campo == "emails":
        v = _texto(valor).lower()
        if not _EMAIL.match(v):
            raise ErroFamilia("valor_invalido")
        return v
    return _texto(valor)


def _parte(v) -> str:
    return str(v).strip() if v is not None and not isinstance(v, bool) else ""


def formatar_endereco(item: dict) -> str:
    """Endereço em dict (forma do yaml) como texto: "logradouro, bairro, cidade/uf, cep", pulando as partes vazias.
    O mesmo formato do painel (`textoItem` em CadastrosFamilia.tsx)."""
    cidade_uf = "/".join(x for x in (_parte(item.get("cidade")), _parte(item.get("uf"))) if x)
    return ", ".join(x for x in (_parte(item.get("logradouro")), _parte(item.get("bairro")), cidade_uf, _parte(item.get("cep"))) if x)


def _texto_item(item):
    """Texto comparável de um item guardado (sem espaços nas pontas, como o valor recebido); None se não houver."""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for k in ("texto", "endereco"):
            if isinstance(item.get(k), str):
                return item[k].strip()
        return formatar_endereco(item) or None
    return None


def _canon(campo: str, item):
    """Forma comparável de um item já guardado (telefone E.164, e-mail minúsculo); None se não der para normalizar."""
    if campo == "telefones":
        return normalizar_telefone(item) if isinstance(item, str) else None
    if campo == "emails":
        return item.strip().lower() if isinstance(item, str) else None
    return None


def _casa(campo: str, item, valor) -> bool:
    if item == valor or _texto_item(item) == valor:
        return True
    c = _canon(campo, item)
    return c is not None and c == valor


def _dados_da(con, pessoa_id: str) -> dict:
    r = con.execute("select dados from pessoa where id=? and excluido_em is null", (pessoa_id,)).fetchone()
    if r is None:
        raise ErroFamilia("nao_encontrado")
    if not r["dados"]:
        return {}
    try:
        d = json.loads(r["dados"])
    except (TypeError, ValueError):
        raise ErroFamilia("requisicao_invalida")
    if not isinstance(d, dict):
        raise ErroFamilia("requisicao_invalida")
    return d


def _gravar(con, pessoa_id: str, dados: dict) -> None:
    con.execute("update pessoa set dados=? where id=?", (json.dumps(dados, ensure_ascii=False), pessoa_id))


def _atual(dados: dict, campo: str):
    if campo in LISTAS:
        v = dados.get(campo)
        if v is None:
            return []
        if not isinstance(v, list):
            raise ErroFamilia("requisicao_invalida")
        return list(v)
    return dados.get(campo)


def _colocar(dados: dict, campo: str, valor) -> None:
    if valor is None or valor == []:
        dados.pop(campo, None)
    else:
        dados[campo] = valor


def _auditar(con, quem: str, agora: dt.datetime, pessoa_id: str, campo: str, acao: str) -> None:
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?,'familia')",
                (_ts(agora), quem, f"Contato de {pessoa_id}: {acao} em {campo}"))


def _historico(con, pessoa_id, campo, antes, depois, quem, agora) -> int:
    return con.execute("insert into pessoa_historico(pessoa_id, campo, antes, depois, quem, quando) values (?,?,?,?,?,?)",
                       (pessoa_id, campo, json.dumps(antes, ensure_ascii=False), json.dumps(depois, ensure_ascii=False),
                        quem, _ts(agora))).lastrowid


def atualizar(con, pessoa_id: str, campo: str, acao: str, valor, quem: str, agora: dt.datetime) -> dict:
    """Grava `valor` em `campo` e registra o histórico, tudo na mesma transação. Devolve antes, depois e historico_id."""
    if campo not in TEXTOS and campo not in LISTAS:
        raise ErroFamilia("campo_invalido")
    if acao not in ("definir", "adicionar", "remover") or (campo in LISTAS) == (acao == "definir"):
        raise ErroFamilia("requisicao_invalida")
    if campo == "nascimento":
        try:
            if not (isinstance(valor, str) and _DATA.match(valor.strip())):
                raise ValueError
            dt.date.fromisoformat(valor.strip())
        except ValueError:
            raise ErroFamilia("valor_invalido")
    with transacao(con, imediata=True):
        dados = _dados_da(con, pessoa_id)
        antes = _atual(dados, campo)
        if acao == "definir":
            depois = _normalizar(campo, valor)
        elif acao == "adicionar":
            novo = _normalizar(campo, valor)
            if len(antes) >= MAX_ITENS or any(_casa(campo, i, novo) for i in antes):
                raise ErroFamilia("valor_invalido")
            depois = antes + [novo]
        else:
            alvo = _normalizar(campo, valor)
            ficam = [i for i in antes if not _casa(campo, i, alvo)]
            if len(ficam) == len(antes):
                raise ErroFamilia("valor_invalido")
            depois = ficam
        _colocar(dados, campo, depois)
        _gravar(con, pessoa_id, dados)
        hid = _historico(con, pessoa_id, campo, antes, depois, quem, agora)
        _auditar(con, quem, agora, pessoa_id, campo, acao)
    return {"antes": antes, "depois": depois, "historico_id": hid}


CARGA = ("telefone", "enderecos")
MAX_CAMPO_ENDERECO = 1000
MAX_CHAVES_ENDERECO = 20


def _endereco_carga(item):
    """Endereço da carga na forma nativa: texto (até 200) ou dict de valores simples (cada texto até 1000, até 20 chaves)."""
    if isinstance(item, str):
        return _texto(item)
    if not isinstance(item, dict) or not item or len(item) > MAX_CHAVES_ENDERECO:
        raise ErroFamilia("valor_invalido")
    for k, v in item.items():
        if not isinstance(k, str) or len(k) > 40 or not (v is None or isinstance(v, (str, int, float, bool))):
            raise ErroFamilia("valor_invalido")
        if isinstance(v, str) and len(v) > MAX_CAMPO_ENDERECO:
            raise ErroFamilia("valor_invalido")
    return dict(item)


def substituir(con, pessoa_id: str, campo: str, valor, quem: str, agora: dt.datetime) -> dict:
    """Só para a carga (`tools/carga_familia.py`, fora do MCP): troca o valor inteiro de `telefone` (texto legado) ou de
    `enderecos` (lista, itens texto ou dict como no yaml), com a mesma linha de histórico, desfazer e auditoria de `atualizar`."""
    if campo not in CARGA:
        raise ErroFamilia("campo_invalido")
    if campo == "telefone":
        depois = _normalizar("telefones", valor)
    else:
        if not isinstance(valor, list) or not 1 <= len(valor) <= MAX_ITENS:
            raise ErroFamilia("valor_invalido")
        depois = [_endereco_carga(v) for v in valor]
    with transacao(con, imediata=True):
        dados = _dados_da(con, pessoa_id)
        antes = dados.get(campo)
        _colocar(dados, campo, depois)
        _gravar(con, pessoa_id, dados)
        hid = _historico(con, pessoa_id, campo, antes, depois, quem, agora)
        _auditar(con, quem, agora, pessoa_id, campo, "definir")
    return {"antes": antes, "depois": depois, "historico_id": hid}


def desfazer(con, historico_id: int, quem: str, agora: dt.datetime) -> dict:
    """Restaura o `antes` de uma linha de histórico. Só se o valor atual ainda for o `depois` (senão `conflito`, sem sobrescrever)."""
    with transacao(con, imediata=True):
        h = con.execute("select * from pessoa_historico where id=?", (historico_id,)).fetchone()
        if h is None:
            raise ErroFamilia("nao_encontrado")
        if h["desfeito_em"]:
            raise ErroFamilia("conflito")
        dados = _dados_da(con, h["pessoa_id"])
        atual = _atual(dados, h["campo"])
        if atual != json.loads(h["depois"]):
            raise ErroFamilia("conflito")
        antes = json.loads(h["antes"])
        _colocar(dados, h["campo"], antes)
        _gravar(con, h["pessoa_id"], dados)
        novo = _historico(con, h["pessoa_id"], h["campo"], atual, antes, quem, agora)
        con.execute("update pessoa_historico set desfeito_em=? where id=?", (_ts(agora), historico_id))
        _auditar(con, quem, agora, h["pessoa_id"], h["campo"], "desfazer")
    return {"antes": atual, "depois": antes, "historico_id": novo}


def historico(con, pessoa_id: str | None = None, limite: int = 50) -> list[dict]:
    """Mudanças de contato, da mais nova para a mais antiga; `antes`/`depois` já decodificados."""
    sql = "select * from pessoa_historico" + (" where pessoa_id=?" if pessoa_id else "") + " order by id desc limit ?"
    args = ((pessoa_id,) if pessoa_id else ()) + (max(1, int(limite)),)
    return [{"id": r["id"], "pessoa_id": r["pessoa_id"], "campo": r["campo"], "antes": json.loads(r["antes"]),
             "depois": json.loads(r["depois"]), "quem": r["quem"], "quando": r["quando"], "desfeito_em": r["desfeito_em"]}
            for r in con.execute(sql, args)]
