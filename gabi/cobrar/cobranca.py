"""E-mail de cobrança dos reembolsos: só RASCUNHO guardado e mostrado no painel (ADR-006); o envio está desabilitado (R2).
O destinatário é cadastro da empresa (`empresa.dados.email_cobranca`). Consome: cobrar.reembolso, cobrar.comprovantes (db)."""
import datetime as dt
import json
from dataclasses import dataclass

from gabi.cobrar.reembolso import ItemReembolso, itens_a_reembolsar
from gabi.cobrar import cadastro
from gabi.db import transacao
from gabi.cobrar.util import brl as _brl


class NaoPermitido(Exception):
    """A API responde 403 `nao_permitido`."""


@dataclass(frozen=True)
class Cobranca:
    id: int
    empresa_id: str
    para: str
    assunto: str
    corpo: str
    itens: list[ItemReembolso]
    anexos: list[int]                 # paperless_id dos comprovantes confirmados
    aviso_sem_comprovante: list[int]  # lançamentos sem comprovante confirmado


def montar(con, empresa_id: str, itens: list[int] | None, *, hoje: dt.date | None = None) -> Cobranca:
    """Monta a cobrança (ou atualiza o rascunho aberto da empresa) com os itens em aberto; `itens` escolhe um subconjunto de lançamentos. Tudo ou nada."""
    with transacao(con):
        return _montar(con, empresa_id, itens, hoje)


def _montar(con, empresa_id: str, itens: list[int] | None, hoje: dt.date | None) -> Cobranca:
    hoje = hoje or dt.date.today()
    emp = con.execute("select nome, dados from empresa where id=? and excluido_em is null", (empresa_id,)).fetchone()
    if emp is None:
        raise LookupError(f"empresa {empresa_id} não existe")
    if cadastro.relacao(con, empresa_id) == "pj_titular":
        raise ValueError("a Bekaa vai pelo lote do Nibo, não por e-mail de cobrança")
    para = (json.loads(emp["dados"] or "{}")).get("email_cobranca")
    if not para:
        raise ValueError(f"cadastre o e-mail de cobrança da {emp['nome']} (empresa.dados.email_cobranca)")
    lista = [i for i in itens_a_reembolsar(con, empresa_id) if itens is None or i.lancamento_id in itens]
    if not lista:
        raise ValueError("nenhum item em aberto para cobrar")
    total = sum(i.em_aberto_centavos for i in lista)
    ids = [i.lancamento_id for i in lista]
    anexos, sem = [], []
    for lid in ids:
        v = con.execute("select c.paperless_id from comprovante_vinculo v join comprovante c on c.id=v.comprovante_id "
                        "where v.lancamento_id=? and v.estado='confirmado' order by v.id limit 1", (lid,)).fetchone()
        (anexos.append(v["paperless_id"]) if v else sem.append(lid))
    linhas = [f"{dt.date.fromisoformat(i.data[:10]):%d/%m}  {i.descricao or '(sem descrição)'}  {_brl(i.em_aberto_centavos)}" for i in lista]
    assunto = f"Reembolso de despesas — {emp['nome']} — {hoje:%m/%Y}"
    corpo = (f"Olá,\n\nsegue a relação de despesas pagas por mim em nome da {emp['nome']}, para reembolso:\n\n" + "\n".join(linhas)
             + f"\n\nTotal: {_brl(total)}\n\nObrigado.")
    # rascunho aberto = o mais recente da empresa cujos itens ainda não viraram reembolso (cobrança formal)
    aberto = con.execute("select id from cobranca where empresa_id=? and not exists (select 1 from reembolso_item ri where ri.lancamento_id in "
                         "(select lancamento_id from cobranca_item where cobranca_id=cobranca.id)) order by id desc limit 1", (empresa_id,)).fetchone()
    agora = dt.datetime.now(dt.timezone.utc).isoformat()
    if aberto:
        cid = aberto["id"]
        con.execute("update cobranca set para=?, assunto=?, corpo=?, criado_em=? where id=?", (para, assunto, corpo, agora, cid))
        con.execute("delete from cobranca_item where cobranca_id=?", (cid,))
    else:
        cid = con.execute("insert into cobranca(empresa_id, para, assunto, corpo, criado_em) values (?,?,?,?,?)", (empresa_id, para, assunto, corpo, agora)).lastrowid
    for lid in ids:
        con.execute("insert into cobranca_item(cobranca_id, lancamento_id) values (?,?)", (cid, lid))
    return Cobranca(cid, empresa_id, para, assunto, corpo, lista, anexos, sem)


def texto_confirmacao(c: Cobranca) -> str:
    """Gerado no servidor; só será usado se o envio for habilitado por ADR assinado pelo Ricardo."""
    return f"Enviar para {c.para}, {len(c.itens)} itens, {_brl(sum(i.em_aberto_centavos for i in c.itens))}, {len(c.anexos)} anexos"


def enviar(con, cobranca_id: int) -> None:
    raise NaoPermitido("o app só guarda o rascunho da cobrança; o envio está desabilitado (ADR-006)")
