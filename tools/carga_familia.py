"""Carga inicial da família: o `familia.yaml` da base cadastral antiga (OP-Gabi) primeiro, o OCR do Paperless como complemento.
O brain já tem a base de 08/10 com números mascarados; a carga traz o número completo e o que mudou depois. Documento vira
proposta (`origem='carga'`) para o Ricardo aprovar; contato vazio ou nunca editado é gravado com histórico e desfazer; empresa
é atualizada no lugar com auditoria sem valor; pets e obrigações só conferem. Leitura duvidosa entra com `conferir=1`.
Sem `--aplicar` roda numa cópia do banco em memória e só conta. A saída são só contagens: nunca número, nome ou valor.
Rodar de novo não duplica nada nem desfaz decisões: número recusado não volta como proposta e contato da carga que foi
desfeito não é gravado de novo.
Consome: gabi.familia (documentos.propor, contato.atualizar/substituir, fichas), pessoa, pet, empresa, compromisso_fixo,
familia_documento/familia_proposta (migração 0081), pessoa_historico (0077), gabi.fontes.ponte (Paperless: docs, texto); grava em decisao
(origem 'familia'). Uso: python -m tools.carga_familia [--yaml CAMINHO] [--sem-ocr] [--aplicar] [--socket CAMINHO] [--banco CAMINHO]"""
import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

from gabi.contatos.telefone import normalizar_telefone
from gabi.db import conectar, transacao
from gabi.envios.propostas import normalizar_nome
from gabi.familia import contato, documentos
from gabi.familia.fichas import ErroFamilia, normalizar_numero, resolver_pessoa
from gabi.mascara import _cpf_valido

YAML_PADRAO = "~/OP-Gabi-fechamento/familia.yaml"
TERMOS = ("cpf", "rg", "cnh", "passaporte", "identidade", "carteira de motorista")
QUEM = "carga"
LIMITE_POR_TERMO = 200
_TIPOS = {"cpf": "cpf", "rg": "rg", "identidade": "rg", "carteira de identidade": "rg",
          "cnh": "cnh", "carteira de motorista": "cnh", "carteira nacional de habilitacao": "cnh", "habilitacao": "cnh",
          "passaporte": "passaporte"}  # o mesmo mapa da migração 0077
_PAISES = {"brasil": "BR", "brazil": "BR", "portugal": "PT", "italia": "IT", "espanha": "ES", "estados unidos": "US", "eua": "US"}
_VAZIOS = {"", "none", "null", "nenhum", "-", "--", "?", "n/a", "na", "nao informado", "nao tem", "sem", "a confirmar"}
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BR = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


# ---- utilitários -------------------------------------------------------------------------------------------------

def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c)).lower().strip()


def _vazio(v) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        t = _sem_acento(v)
        return t in _VAZIOS or t.startswith("pendente")
    return v == [] or v == {}


def _puro(v):
    """Valor do yaml comparável ao JSON do banco: datas viram texto ISO."""
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): _puro(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_puro(x) for x in v]
    return v


def _data_iso(v):
    """(data YYYY-MM-DD ou None, descartada?) — o yaml pode trazer `date` (sem aspas) ou texto."""
    if _vazio(v):
        return None, False
    if isinstance(v, dt.datetime):
        v = v.date()
    if isinstance(v, dt.date):
        return v.isoformat(), False
    if isinstance(v, str) and _ISO.match(v.strip()):
        try:
            return dt.date.fromisoformat(v.strip()).isoformat(), False
        except ValueError:
            pass
    return None, True


def tipo_normalizado(v) -> str:
    return _TIPOS.get(_sem_acento(str(v or "")), "outro")


def _numero(v) -> str | None:
    if _vazio(v) or isinstance(v, bool):
        return None
    n = str(v).strip()
    if "*" in n or not re.search(r"\d", n) or len(n) > 40:
        return None
    return n


def _pais(v):
    """(ISO-2, duvidoso?)."""
    if _vazio(v):
        return "BR", False
    t = str(v).strip()
    if re.fullmatch(r"[A-Za-z]{2}", t):
        return t.upper(), False
    p = _PAISES.get(_sem_acento(t))
    return (p, False) if p else ("BR", True)


def _dados(texto) -> dict:
    try:
        d = json.loads(texto) if texto else {}
    except (TypeError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _copia(con) -> sqlite3.Connection:
    """Cópia do banco em memória para a simulação (sem `--aplicar`): as funções do domínio abrem transação própria."""
    mem = sqlite3.connect(":memory:", isolation_level=None)
    mem.row_factory = sqlite3.Row
    con.backup(mem)
    mem.execute("pragma foreign_keys=on")
    return mem


def _max_proposta(con) -> int:
    return con.execute("select coalesce(max(id), 0) from documento_proposta").fetchone()[0]


def _contar_novas(con, desde: int, r: dict) -> None:
    for p in con.execute("select p.conferir, d.numero dn from familia_proposta p left join familia_documento d on d.id=p.documento_id"
                         " where p.id>?", (desde,)):
        r["propostas"] += 1
        r["conferir"] += p["conferir"]
        r["substituem_mascarado"] += 1 if p["dn"] is not None and documentos.mascarado(p["dn"]) else 0


def _simular(fn, con, *a, aplicar: bool):
    if aplicar:
        return fn(con, *a)
    copia = _copia(con)
    try:
        return fn(copia, *a)
    finally:
        copia.close()


# ---- etapa 1: familia.yaml ---------------------------------------------------------------------------------------

def _doc_yaml(item: dict, r: dict) -> dict | None:
    numero = _numero(item.get("numero"))
    if numero is None:
        r["documentos_descartados"] += 1
        return None
    tipo = tipo_normalizado(item.get("tipo"))
    emissor = next((str(item[k]).strip() for k in ("emissor", "autoridade_emissora") if not _vazio(item.get(k))), None)
    emissao, d1 = _data_iso(next((item[k] for k in ("emissao", "expedicao") if not _vazio(item.get(k))), None))
    validade, d2 = _data_iso(item.get("validade"))
    r["datas_descartadas"] += d1 + d2
    pais, duvida = _pais(item.get("pais"))
    conferir = duvida or (tipo == "cpf" and not _cpf_valido(re.sub(r"\D", "", numero))) \
        or (tipo in ("passaporte", "cnh") and validade is None)
    return dict(tipo=tipo, numero=numero, emissor=emissor[:200] if emissor else None, emissao=emissao, validade=validade,
                pais=pais, conferir=conferir)


def _endereco(item):
    """Item de endereço na forma nativa: texto ou o dict do yaml (tipo, logradouro, bairro, cidade, uf, cep, observacao)."""
    if isinstance(item, str):
        return item.strip() or None
    if isinstance(item, dict):
        return _puro(item) or None
    return None


def _contato_yaml(rec: dict, r: dict) -> dict:
    """Valores do yaml já na forma gravada; inválido entra em `contatos_descartados`."""
    novos = {}
    if not _vazio(rec.get("apelido")):
        novos["apelido"] = str(rec["apelido"]).strip()
    if not _vazio(rec.get("nascimento")):
        v = rec["nascimento"]
        m = _BR.match(v.strip()) if isinstance(v, str) else None
        iso, ruim = _data_iso(f"{m[3]}-{m[2]}-{m[1]}" if m else v)
        if iso:
            novos["nascimento"] = iso
        r["contatos_descartados"] += ruim
    if not _vazio(rec.get("telefone")):
        t = normalizar_telefone(str(rec["telefone"]))
        if t:
            novos["telefone"] = t
        else:
            r["contatos_descartados"] += 1
    if not _vazio(rec.get("enderecos")):
        bruto = rec["enderecos"] if isinstance(rec["enderecos"], list) else [rec["enderecos"]]
        itens = [e for e in (_endereco(x) for x in bruto) if e]
        if itens:
            novos["enderecos"] = itens
    return novos


def _atual_contato(dados: dict, campo: str):
    v = dados.get(campo)
    if campo == "telefone":
        return (normalizar_telefone(v) or v) if isinstance(v, str) and v.strip() else None
    if campo == "enderecos":
        return v if isinstance(v, list) and v else None
    return v if not _vazio(v) else None


def _editado(con, pessoa_id: str, campo: str) -> bool:
    """Editado depois de 08/10 por alguém que não a própria carga (a carga pode corrigir o que ela mesma gravou).
    O `telefone` legado conta também a lista `telefones`."""
    campos = ("telefone", "telefones") if campo == "telefone" else (campo,)
    return con.execute(f"select 1 from pessoa_historico where pessoa_id=? and campo in ({','.join('?' * len(campos))})"
                       " and quem<>? limit 1", (pessoa_id, *campos, QUEM)).fetchone() is not None


def _desfeito(con, pessoa_id: str, campo: str) -> bool:
    """Gravação da carga neste campo que alguém desfez: decisão do dono, a carga não grava o campo de novo."""
    return con.execute("select 1 from pessoa_historico where pessoa_id=? and campo=? and quem=? and desfeito_em is not null limit 1",
                       (pessoa_id, campo, QUEM)).fetchone() is not None


def _pessoa(con, rec: dict, agora, r: dict) -> None:
    pid = rec["id"]
    for item in rec.get("documentos") or []:
        if not isinstance(item, dict):
            continue
        d = _doc_yaml(item, r)
        if d is None:
            continue
        try:
            documentos.propor(con, pid, origem=QUEM, agora=agora, **d)
        except ErroFamilia:
            r["documentos_descartados"] += 1
    linha = con.execute("select dados from pessoa where id=?", (pid,)).fetchone()
    for campo, novo in _contato_yaml(rec, r).items():
        atual = _atual_contato(_dados(linha["dados"]), campo)
        if atual == novo:
            continue
        if (atual is not None and _editado(con, pid, campo)) or _desfeito(con, pid, campo):
            r["divergencias"] += 1  # já editado (Ricardo, painel ou Hermes) ou gravação da carga desfeita: não sobrescreve
            continue
        try:
            if campo in contato.CARGA:
                contato.substituir(con, pid, campo, novo, QUEM, agora)
            else:
                contato.atualizar(con, pid, campo, "definir", novo, QUEM, agora)
            r["contatos_gravados"] += 1
        except ErroFamilia:
            r["contatos_descartados"] += 1
        linha = con.execute("select dados from pessoa where id=?", (pid,)).fetchone()


def _empresa(con, rec: dict, agora, r: dict) -> None:
    linha = con.execute("select dados from empresa where id=? and excluido_em is null", (rec["id"],)).fetchone()
    dados = _dados(linha["dados"])
    trocados = [c for c in ("documentos", "dados_bancarios") if not _vazio(rec.get(c)) and _puro(rec[c]) != dados.get(c)]
    if not trocados:
        return
    with transacao(con, imediata=True):
        for c in trocados:
            dados[c] = _puro(rec[c])
            con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?,'familia')",
                        (contato._ts(agora), QUEM, f"carga atualizou {c} da empresa {rec['id']}"))
        con.execute("update empresa set dados=? where id=?", (json.dumps(dados, ensure_ascii=False), rec["id"]))
    r["empresa_campos"] += len(trocados)


def _confere(con, tabela: str, rec: dict) -> bool | None:
    """None sem cadastro; True se alguma chave presente nos dois (fora `origem`) difere entre o yaml e o `dados` do brain."""
    linha = con.execute(f"select dados from {tabela} where id=?", (rec["id"],)).fetchone()
    if linha is None:
        return None
    dados = _dados(linha["dados"])
    return any(_puro(v) != dados[k] for k, v in rec.items() if k != "origem" and k in dados)


def _carregar_yaml(con, dados: dict, agora) -> dict:
    r = dict.fromkeys(("pessoas_lidas", "empresas_lidas", "pets_lidos", "obrigacoes_lidas", "sem_cadastro", "propostas",
                       "substituem_mascarado", "conferir", "documentos_descartados", "datas_descartadas", "contatos_gravados",
                       "contatos_descartados", "divergencias", "empresa_campos", "empresas_sem_cadastro", "pets_divergentes", "pets_sem_cadastro",
                       "obrigacoes_divergentes", "obrigacoes_sem_cadastro"), 0)
    desde = _max_proposta(con)
    for rec in dados.get("pessoas") or []:
        if not isinstance(rec, dict) or not isinstance(rec.get("id"), str):
            continue
        r["pessoas_lidas"] += 1
        if con.execute("select 1 from pessoa where id=? and excluido_em is null", (rec["id"],)).fetchone() is None:
            r["sem_cadastro"] += 1
            continue
        _pessoa(con, rec, agora, r)
    for rec in dados.get("empresas") or []:
        if not isinstance(rec, dict) or not isinstance(rec.get("id"), str):
            continue
        r["empresas_lidas"] += 1
        if con.execute("select 1 from empresa where id=? and excluido_em is null", (rec["id"],)).fetchone() is None:
            r["empresas_sem_cadastro"] += 1
            continue
        _empresa(con, rec, agora, r)
    for chave, tabela, lidos, div, sem in (("pets", "pet", "pets_lidos", "pets_divergentes", "pets_sem_cadastro"),
                                           ("obrigacoes", "compromisso_fixo", "obrigacoes_lidas", "obrigacoes_divergentes",
                                            "obrigacoes_sem_cadastro")):
        for rec in dados.get(chave) or (dados.get("compromissos_fixos") if chave == "obrigacoes" else None) or []:
            if not isinstance(rec, dict) or not isinstance(rec.get("id"), str):
                continue
            r[lidos] += 1
            c = _confere(con, tabela, rec)
            if c is None:
                r[sem] += 1
            elif c:
                r[div] += 1
    # matriz_de_acesso, assistente e documento (configuração da época do OpenClaw) ficam de fora.
    _contar_novas(con, desde, r)
    return r


def carregar_yaml(con, dados: dict, agora: dt.datetime, aplicar: bool) -> dict:
    """Etapa 1. Devolve só contagens. Sem `aplicar`, roda numa cópia em memória e nada é gravado."""
    if not isinstance(dados, dict):
        raise ValueError("familia.yaml sem o formato esperado")
    return _simular(_carregar_yaml, con, dados, agora, aplicar=aplicar)


# ---- etapa 2: OCR do Paperless -----------------------------------------------------------------------------------

_CPF = re.compile(r"(?<![\d.])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?![\d])")
_PASSAPORTE = re.compile(r"(?<![A-Z0-9])[A-Z]{2}\d{6}(?!\d)")
_RG = re.compile(r"(?<![\d.])\d{1,2}\.?\d{3}\.?\d{3}-?[\dxX](?![\dA-Za-z])")
_CNH = re.compile(r"(?<!\d)\d{11}(?!\d)")
_CHAVE_VALIDADE = re.compile(r"validade|valid until|date of expiry|expiry|expira", re.I)
_CHAVE_RG = re.compile(r"\brg\b|identidade|registro geral", re.I)
_CHAVE_CNH = re.compile(r"registro(?!\s+geral)", re.I)
_DATA_NUM = re.compile(r"(?<!\d)(\d{2})/(\d{2})/(\d{4})(?!\d)")
_DATA_MES = re.compile(r"(?<!\d)(\d{1,2})\s+([A-Za-zÀ-ÿ]{3,9})(?:\s*/\s*[A-Za-zÀ-ÿ]{3,9})?\s+(\d{4})(?!\d)")
_MESES = {"jan": 1, "fev": 2, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "mai": 5, "may": 5, "jun": 6, "jul": 7, "ago": 8, "aug": 8,
          "set": 9, "sep": 9, "out": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12}
JANELA = 60


def _validades(ocr: str) -> tuple[str | None, bool]:
    """(validade mais próxima depois da palavra-chave, duvidosa?). Datas numéricas são dd/mm (padrão BR); dd e mm ambos
    até 12 e diferentes são ambíguos (dd/mm × mm/dd). Mais de uma data candidata também é duvidosa."""
    achadas: dict[int, tuple[str, bool]] = {}
    for k in _CHAVE_VALIDADE.finditer(ocr):
        trecho_ini = k.end()
        trecho = ocr[trecho_ini:trecho_ini + JANELA]
        for m in _DATA_NUM.finditer(trecho):
            try:
                d = dt.date(int(m[3]), int(m[2]), int(m[1]))
            except ValueError:
                continue
            ambigua = int(m[1]) <= 12 and int(m[2]) <= 12 and m[1] != m[2]
            achadas.setdefault(trecho_ini + m.start(), (d.isoformat(), ambigua))
        for m in _DATA_MES.finditer(trecho):
            mes = _MESES.get(_sem_acento(m[2])[:3])
            if not mes:
                continue
            try:
                d = dt.date(int(m[3]), mes, int(m[1]))
            except ValueError:
                continue
            achadas.setdefault(trecho_ini + m.start(), (d.isoformat(), False))
    if not achadas:
        return None, False
    valores = {v for v, _ in achadas.values()}
    primeira = achadas[min(achadas)]
    return primeira[0], primeira[1] or len(valores) > 1


def _perto(chave: re.Pattern, ocr: str, ini: int) -> bool:
    return any(0 <= ini - k.end() <= JANELA for k in chave.finditer(ocr))


def extrair(ocr: str) -> list[dict]:
    """Documentos achados no OCR por expressões fixas (sem modelo): {tipo, numero, emissao, validade, conferir}.
    Duvidoso (CPF sem DV, data ambígua, mais de um candidato do mesmo tipo) sai com conferir=True."""
    ocr = ocr or ""
    usados: list[tuple[int, int]] = []
    achados: list[tuple[str, str, bool]] = []

    def livre(m):
        return not any(m.start() < f and m.end() > i for i, f in usados)

    for m in _CNH.finditer(ocr):
        if _perto(_CHAVE_CNH, ocr, m.start()):
            usados.append(m.span())
            achados.append(("cnh", m[0], False))
    for m in _CPF.finditer(ocr):
        if livre(m):
            usados.append(m.span())
            achados.append(("cpf", m[0], not _cpf_valido(re.sub(r"\D", "", m[0]))))
    for m in _RG.finditer(ocr):
        if livre(m) and _perto(_CHAVE_RG, ocr, m.start()):
            usados.append(m.span())
            achados.append(("rg", m[0], False))
    for m in _PASSAPORTE.finditer(ocr):
        achados.append(("passaporte", m[0], False))
    validade, duvida = _validades(ocr)
    vistos: dict[tuple[str, str], dict] = {}
    for tipo, numero, conferir in achados:
        vistos.setdefault((tipo, normalizar_numero(numero)), {"tipo": tipo, "numero": numero, "emissao": None,
                                                              "validade": validade if tipo != "cpf" else None,
                                                              "conferir": conferir or (duvida and tipo != "cpf")})
    itens = list(vistos.values())
    for tipo in {i["tipo"] for i in itens}:
        mesmos = [i for i in itens if i["tipo"] == tipo]
        if len(mesmos) > 1:
            for i in mesmos:
                i["conferir"] = True
    return itens


def _chaves(nome, d: dict) -> set[str]:
    return {k for k in (normalizar_nome(nome or ""), normalizar_nome(d.get("nome_completo") or ""),
                        normalizar_nome(d.get("apelido") or "")) if len(k) >= 3}


def _achar(con, texto: str) -> str | None:
    alvo = f" {re.sub(r'[^0-9a-z]+', ' ', normalizar_nome(texto))} "
    casos = {}
    for r in con.execute("select id, nome, dados from pessoa where excluido_em is null"):
        ks = {k for k in _chaves(r["nome"], _dados(r["dados"])) if f" {k} " in alvo}
        if ks:
            casos[r["id"]] = ks
    # "Ana" casa dentro de "Ana Clara": fica só quem tem um nome que não está contido no nome de outro candidato.
    ficam = [p for p, ks in casos.items()
             if not all(any(k != o and f" {k} " in f" {o} " for q, os_ in casos.items() if q != p for o in os_) for k in ks)]
    return ficam[0] if len(ficam) == 1 else None


def _ligar(con, titulo: str, ocr: str) -> tuple[str | None, bool]:
    """(pessoa, ligada pelo título?)."""
    try:
        return resolver_pessoa(con, titulo or ""), True
    except ErroFamilia:
        pass
    pelo_titulo = _achar(con, titulo or "")
    if pelo_titulo:
        return pelo_titulo, True
    return _achar(con, ocr or ""), False


def ligar(con, titulo: str, ocr: str) -> str | None:
    """Pessoa do documento pelo nome no título (primeiro, via `resolver_pessoa` ou pelo nome dentro dele) ou no OCR.
    Sem pessoa única: None."""
    return _ligar(con, titulo, ocr)[0]


def _completar(con, prop, item: dict, paperless_id: int) -> bool:
    """Proposta aberta com o mesmo número: completa campo vazio; validade diferente marca conferir. True se mudou."""
    mudancas = {}
    if item["validade"]:
        if prop["validade"] is None:
            mudancas["validade"] = item["validade"]
            if item["conferir"] and not prop["conferir"]:
                mudancas["conferir"] = 1
        elif prop["validade"] != item["validade"] and not prop["conferir"]:
            mudancas["conferir"] = 1
    if prop["paperless_id"] is None:
        mudancas["paperless_id"] = paperless_id
    if not mudancas:
        return False
    with transacao(con, imediata=True):
        documentos.completar_proposta(con, prop["id"], **mudancas)
    return True


def _item_ocr(con, pid: str, item: dict, paperless_id: int, agora, r: dict) -> None:
    tipo, numero, alvo = item["tipo"], item["numero"], normalizar_numero(item["numero"])
    ativos = list(con.execute("select * from familia_documento where pessoa_id=? and tipo=? and pais='BR' and excluido_em is null"
                              " order by id", (pid, tipo)))
    abertas = list(con.execute("select * from familia_proposta where pessoa_id=? and tipo=? and pais='BR' and estado='pendente'"
                               " order by id", (pid, tipo)))
    igual = next((a for a in ativos if normalizar_numero(a["numero"]) == alvo), None)
    aberta = next((p for p in abertas if normalizar_numero(p["numero"]) == alvo), None)
    conferir = item["conferir"]
    if igual is not None:
        campos = {}
        if item["validade"] and igual["validade"] != item["validade"]:
            campos["validade"] = item["validade"]
            conferir = conferir or igual["validade"] is not None  # diverge do ativo
        if igual["paperless_id"] is None:
            campos["paperless_id"] = paperless_id
        if not campos:
            return
    elif aberta is None:
        # Número novo para quem já tem outro ativo (não mascarado) ou outra proposta aberta: diverge do yaml/ativo.
        if any(not documentos.mascarado(a["numero"]) for a in ativos) or abertas:
            conferir = True
        campos = {"paperless_id": paperless_id, "validade": item["validade"]}
    if aberta is not None:
        r["propostas_completadas"] += _completar(con, aberta, {**item, "conferir": conferir}, paperless_id)
        return
    try:
        documentos.propor(con, pid, tipo=tipo, numero=numero, origem=QUEM, conferir=conferir, agora=agora, **campos)
    except ErroFamilia:
        r["documentos_descartados"] += 1


def _carregar_ocr(con, paperless, agora) -> dict:
    r = dict.fromkeys(("paperless_lidos", "ocr_sem_pessoa", "ocr_sem_documento", "propostas", "substituem_mascarado",
                       "conferir", "propostas_completadas", "documentos_descartados", "termos_no_limite"), 0)
    desde = _max_proposta(con)
    vistos: dict[int, dict] = {}
    for termo in TERMOS:
        achados = paperless.docs(query=termo, page_size=100, limite=LIMITE_POR_TERMO)
        r["termos_no_limite"] += len(achados) >= LIMITE_POR_TERMO  # a busca pode ter cortado documentos: conta em vez de sumir calado
        for d in achados:
            vistos.setdefault(d["id"], d)
    for pid_doc, d in sorted(vistos.items()):
        r["paperless_lidos"] += 1
        ocr = d.get("content")
        if ocr is None:
            ocr = paperless.texto(pid_doc)
        itens = extrair(ocr)
        if not itens:
            r["ocr_sem_documento"] += 1
            continue
        pessoa, pelo_titulo = _ligar(con, d.get("title") or "", ocr)
        if pessoa is None:
            r["ocr_sem_pessoa"] += 1
            continue
        for item in itens:
            # Ligado só pelo corpo do OCR (o nome pode ser de outra pessoa citada no documento): conferir.
            _item_ocr(con, pessoa, {**item, "conferir": item["conferir"] or not pelo_titulo}, pid_doc, agora, r)
    _contar_novas(con, desde, r)
    return r


def carregar_ocr(con, paperless, agora: dt.datetime, aplicar: bool) -> dict:
    """Etapa 2 (complemento): propõe só documento que não existe ou campo vazio, com o `paperless_id`. Só contagens."""
    return _simular(_carregar_ocr, con, paperless, agora, aplicar=aplicar)


# ---- linha de comando --------------------------------------------------------------------------------------------

def _imprimir(titulo: str, r: dict) -> None:
    print(titulo)
    for k, v in r.items():
        print(f"  {k}: {v}")


def main(argv=None, paperless=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.carga_familia")
    ap.add_argument("--yaml", default=YAML_PADRAO)
    ap.add_argument("--sem-ocr", action="store_true")
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--socket", default=os.environ.get("GABI_FONTES_SOCKET"))
    ap.add_argument("--banco", default=os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db"))
    a = ap.parse_args(argv)
    import yaml
    caminho = Path(a.yaml).expanduser()
    if not caminho.is_file():
        print("ERRO: familia.yaml não encontrado", file=sys.stderr)
        return 2
    try:
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        print("ERRO: familia.yaml ilegível", file=sys.stderr)
        return 2
    if not isinstance(dados, dict):
        print("ERRO: familia.yaml sem o formato esperado", file=sys.stderr)
        return 2
    if not Path(a.banco).is_file():
        print("ERRO: banco não encontrado", file=sys.stderr)
        return 2
    con, alvo = conectar(Path(a.banco)), None
    try:
        if con.execute("select 1 from sqlite_master where name='familia_proposta'").fetchone() is None:
            print("ERRO: migração 0081 não aplicada neste banco", file=sys.stderr)
            return 2
        alvo = con if a.aplicar else _copia(con)
        agora = dt.datetime.now(dt.timezone.utc)
        print("modo: " + ("aplicado" if a.aplicar else "simulação (nada gravado; use --aplicar)"))
        try:
            _imprimir("familia.yaml:", carregar_yaml(alvo, dados, agora, aplicar=True))
        except Exception as e:  # noqa: BLE001 — só o tipo do erro; a mensagem pode trazer dado
            print(f"familia.yaml interrompido: {type(e).__name__}", file=sys.stderr)
            return 1
        if a.sem_ocr:
            return 0
        if paperless is None:
            if not a.socket:
                print("OCR pulado: GABI_FONTES_SOCKET não configurado", file=sys.stderr)
                return 0
            from gabi.fontes.ponte import Ponte
            paperless = Ponte(a.socket, "paperless")
        try:
            _imprimir("Paperless (OCR):", carregar_ocr(alvo, paperless, agora, aplicar=True))
        except Exception as e:  # noqa: BLE001 — só o tipo do erro; a mensagem pode trazer dado
            print(f"OCR interrompido: {type(e).__name__}", file=sys.stderr)
            return 1
        return 0
    finally:
        if alvo is not None and alvo is not con:
            alvo.close()
        con.close()


if __name__ == "__main__":
    sys.exit(main())
