"""Fichas da família: lista, ficha completa, resolução de nome, vencimentos e auditoria de leitura.
Consome: pessoa (dados JSON), as visões familia_documento e familia_proposta (documentos de pessoa, migração 0081); grava em decisao (origem 'familia').
O número do documento só sai por `ficha`; listas, vencimentos, erros e a auditoria nunca o levam."""
import calendar
import datetime as dt
import json
import re

from gabi.envios.propostas import normalizar_nome

CAMPOS_DOC = ("emissao", "validade", "emissor", "numero")


def normalizar_numero(numero) -> str:
    """Número de documento comparável: sem espaços, pontos e hífens, em maiúsculas."""
    return re.sub(r"[\s.\-]", "", str(numero or "")).upper()


class ErroFamilia(Exception):
    """Falha com código fixo (nunca texto de usuário nem número de documento); `candidatos` só nos casos ambíguos."""

    def __init__(self, codigo: str, mensagem: str = "", candidatos: list | None = None):
        super().__init__(codigo)
        self.codigo, self.mensagem, self.candidatos = codigo, mensagem or codigo, candidatos


def _dados(r) -> dict:
    try:
        d = json.loads(r["dados"]) if r["dados"] else {}
    except (TypeError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _lista(dados: dict, singular: str, plural: str) -> list:
    """Junta o valor de texto e a lista, sem repetir e sem vazios, na ordem."""
    saida: list = []
    itens = [dados.get(singular)]
    mais = dados.get(plural)
    if isinstance(mais, list):
        itens += mais
    for v in itens:
        if isinstance(v, str):
            v = v.strip()
        if v and v not in saida:
            saida.append(v)
    return saida


def _nome_completo(r, d: dict) -> str | None:
    return d.get("nome_completo") or None


def listar(con) -> list[dict]:
    """Quem está no cadastro, sem número de documento."""
    qtd = {r["pessoa_id"]: r["n"] for r in con.execute(
        "select pessoa_id, count(*) n from familia_documento where excluido_em is null group by pessoa_id")}
    saida = []
    for r in con.execute("select id, nome, dados from pessoa where excluido_em is null order by nome collate nocase, id"):
        d = _dados(r)
        saida.append({"id": r["id"], "nome": r["nome"], "apelido": d.get("apelido"), "parentesco": d.get("parentesco"),
                      "nascimento": d.get("nascimento"), "documentos_qtd": qtd.get(r["id"], 0)})
    return saida


def divergencias(con, pessoa_id: str) -> list[dict]:
    """Propostas pendentes que apontam para um documento ativo com valores diferentes; só os nomes dos campos."""
    saida = []
    for p in con.execute(
            "select p.documento_id, p.tipo, p.emissao pe, p.validade pv, p.emissor pm, p.numero pn,"
            " d.emissao de, d.validade dv, d.emissor dm, d.numero dn"
            " from familia_proposta p join familia_documento d on d.id=p.documento_id"
            " where p.pessoa_id=? and p.estado='pendente' and d.excluido_em is null order by p.id", (pessoa_id,)):
        pares = {"emissao": (p["pe"], p["de"]), "validade": (p["pv"], p["dv"]),
                 "emissor": (p["pm"], p["dm"]), "numero": (p["pn"], p["dn"])}
        # Campo vazio na proposta não muda nada ao aprovar, então não é divergência; o número compara normalizado.
        campos = [c for c in CAMPOS_DOC if pares[c][0]
                  and (normalizar_numero(pares[c][0]) != normalizar_numero(pares[c][1]) if c == "numero"
                       else pares[c][0] != (pares[c][1] or None))]
        if campos:
            saida.append({"documento_id": p["documento_id"], "tipo": p["tipo"], "campos": campos})
    return saida


def ficha(con, pessoa_id: str) -> dict:
    """Ficha completa, com os números dos documentos ativos."""
    r = con.execute("select id, nome, dados from pessoa where id=? and excluido_em is null", (pessoa_id,)).fetchone()
    if r is None:
        raise ErroFamilia("nao_encontrado")
    d = _dados(r)
    docs = [dict(x) for x in con.execute(
        "select id, tipo, pais, numero, emissor, emissao, validade, paperless_id, origem, atualizado_em"
        " from familia_documento where pessoa_id=? and excluido_em is null order by id", (pessoa_id,))]
    enderecos = d.get("enderecos")
    return {"id": r["id"], "nome": r["nome"], "nome_completo": _nome_completo(r, d), "apelido": d.get("apelido"),
            "parentesco": d.get("parentesco"), "nascimento": d.get("nascimento"),
            "telefones": _lista(d, "telefone", "telefones"), "emails": _lista(d, "email", "emails"),
            "enderecos": enderecos if isinstance(enderecos, list) else [],
            "documentos": docs, "divergencias": divergencias(con, pessoa_id)}


def resolver_pessoa(con, texto: str) -> str:
    """Casa por igualdade (sem caixa e acento) do texto com o nome, o nome completo ou o apelido; sem igual, pelo começo em
    palavras inteiras ("Louise" casa "Louise Lavrik Esper"). Exatamente 1 pessoa: o id. Senão `pessoa_ambigua`, com os nomes
    candidatos (vazio se ninguém casar)."""
    alvo = normalizar_nome(texto)
    # Só valores texto casam (nome_completo/apelido de outro tipo no JSON são ignorados).
    linhas = [(r["id"], r["nome"], [normalizar_nome(v) for v in (r["nome"], d.get("nome_completo"), d.get("apelido")) if isinstance(v, str)])
              for r in con.execute("select id, nome, dados from pessoa where excluido_em is null") for d in (_dados(r),)]
    if alvo:
        exatos = [(i, n) for i, n, chaves in linhas if alvo in chaves]
        if len(exatos) == 1:
            return exatos[0][0]
        if exatos:
            raise ErroFamilia("pessoa_ambigua", candidatos=[n for _, n in exatos])
        comeco = [(i, n) for i, n, chaves in linhas if any(c.startswith(alvo + " ") for c in chaves)]
        if len(comeco) == 1:
            return comeco[0][0]
        parciais = [n for _, n, chaves in linhas if any(alvo in c for c in chaves)]
        raise ErroFamilia("pessoa_ambigua", candidatos=parciais)
    raise ErroFamilia("pessoa_ambigua", candidatos=[])


def _somar_meses(d: dt.date, meses: int) -> dt.date:
    m = d.month - 1 + meses
    ano, mes = d.year + m // 12, m % 12 + 1
    return dt.date(ano, mes, min(d.day, calendar.monthrange(ano, mes)[1]))


def vencimentos(con, hoje: dt.date, meses: int) -> list[dict]:
    """Documentos com validade entre hoje - 30 dias e hoje + `meses`, por validade; sem número."""
    ini, fim = (hoje - dt.timedelta(days=30)).isoformat(), _somar_meses(hoje, meses).isoformat()
    return [{"pessoa_id": r["pessoa_id"], "nome": r["nome"], "tipo": r["tipo"], "pais": r["pais"],
             "validade": r["validade"], "vencido": r["validade"] < hoje.isoformat()}
            for r in con.execute(
                "select d.pessoa_id, p.nome, d.tipo, d.pais, d.validade from familia_documento d join pessoa p on p.id=d.pessoa_id"
                " where d.excluido_em is null and p.excluido_em is null and d.validade between ? and ?"
                " order by d.validade, d.id", (ini, fim))]


def auditar_leitura(con, pessoa_id: str, tipos: list[str], quem: str, agora: dt.datetime) -> None:
    """Registra em `decisao` (origem 'familia') que a ficha foi lida; só id da pessoa e tipos, nunca números."""
    quando = agora.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if agora.tzinfo else agora.strftime("%Y-%m-%dT%H:%M:%SZ")
    texto = f"Hermes consultou a ficha de {pessoa_id} (documentos: {', '.join(tipos) if tipos else 'nenhum'})"
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?,'familia')", (quando, quem, texto))
