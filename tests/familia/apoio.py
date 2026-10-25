"""Fixtures de documento e proposta da família direto nas tabelas da 0081 (no lugar dos inserts em pessoa_documento/pessoa_proposta)."""
import json

_TS = "2026-10-01T00:00:00Z"


def doc_pessoa(con, pessoa_id, tipo, numero, *, pais="BR", emissor=None, emissao=None, validade=None, paperless_id=None,
               origem="legado", criado_em=_TS, atualizado_em=_TS, excluido_em=None) -> int:
    i = con.execute("insert into documento(titular_tipo, titular_id, tipo, pais, emissor, paperless_id, origem, criado_em, atualizado_em,"
                    " excluido_em) values ('pessoa',?,?,?,?,?,?,?,?,?)",
                    (pessoa_id, tipo, pais, emissor, paperless_id, origem, criado_em, atualizado_em, excluido_em)).lastrowid
    con.execute("insert into documento_numero(documento_id, nome, valor) values (?, 'numero', ?)", (i, numero))
    for t, v in (("emissao", emissao), ("validade", validade)):
        if v is not None:
            con.execute("insert into documento_data(documento_id, tipo, data) values (?,?,?)", (i, t, v))
    return i


def prop_pessoa(con, pessoa_id, tipo, numero, *, documento_id=None, pais="BR", validade=None, origem="hermes", estado="pendente") -> int:
    doc = {"titular_tipo": "pessoa", "titular_id": pessoa_id, "tipo": tipo, "pais": pais, "emissor": None,
           "numeros": [{"nome": "numero", "valor": numero}], "datas": [{"tipo": "validade", "data": validade}] if validade else []}
    return con.execute("insert into documento_proposta(doc, documento_id, origem, estado) values (?,?,?,?)",
                       (json.dumps(doc), documento_id, origem, estado)).lastrowid
