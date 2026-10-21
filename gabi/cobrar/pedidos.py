"""Pedidos de pagamento vindos do canal: a Gabi REGISTRA (sem dizer que pagou); só o Ricardo decide, pelo painel (R1, R2).
Aprovar cria uma linha de compromisso do mês (entra na agenda) e um aviso para o canal. Consome: cadastros (pessoa.dados.canais e dados.pode_pedir)."""
import base64
import datetime as dt
import json
from dataclasses import dataclass
from typing import Callable

from gabi.avisos import VALE, consolidar_duplicados, triar
from gabi.cobrar import cadastro
from gabi.db import transacao
from gabi.dinheiro.valor import para_centavos
from gabi.cobrar.util import agora as _agora
from gabi.contatos.telefone import normalizar_telefone
from gabi.hoje import hoje_brt

CANAL_ESCUTA = "escuta"  # pedido lido pela escuta do WhatsApp: a Gabi nunca responde ao terceiro (R2)


class SemEscopo(Exception):
    """O remetente não está autorizado a pedir (a API responde 403 `sem_escopo`)."""


@dataclass(frozen=True)
class RegistroPedido:
    pedido_id: int
    estado: str
    texto_para_responder: str


def _mesmo_canal(canal, solicitante: str, numero: str | None) -> bool:
    """`whatsapp:` compara o telefone normalizado (canal digitado no Cadastros com espaço/hífen casa); os demais canais, exatos."""
    if not isinstance(canal, str):
        return False
    if canal == solicitante:
        return True
    return numero is not None and canal.startswith("whatsapp:") and normalizar_telefone(canal[len("whatsapp:"):]) == numero


def _pessoa_autorizada(con, solicitante: str):
    numero = normalizar_telefone(solicitante[len("whatsapp:"):]) if solicitante.startswith("whatsapp:") else None
    for p in con.execute("select id, nome, dados from pessoa where excluido_em is null"):
        d = cadastro.dados(p)  # permissão e canais ficam no cadastro da pessoa (dados.pode_pedir, dados.canais)
        if d.get("pode_pedir") is True and any(_mesmo_canal(c, solicitante, numero) for c in (d.get("canais") or [])):
            return p
    return None


def registrar(con, *, solicitante: str, canal: str, mensagem_original: str, descricao: str, valor: str | None, vencimento: str | None,
              anexo_base64: str | None, anexo_paperless_id: int | None, pix_chave: str | None, linha_digitavel: str | None,
              para_quem: str | None, enviar_ao_paperless: Callable[[bytes, str], int | str | None] | None = None) -> RegistroPedido:
    """Registra o pedido como `pendente`. O anexo vai ao Paperless (nunca ao banco). A resposta ao solicitante não diz que pagou."""
    pessoa = _pessoa_autorizada(con, solicitante)
    if pessoa is None:
        raise SemEscopo("remetente não autorizado a fazer pedidos")
    centavos = para_centavos(valor)  # valida tudo ANTES de subir o anexo ou gravar: pedido ruim não deixa rastro
    if centavos is None or centavos <= 0:
        raise ValueError("o pedido precisa de um valor maior que zero")
    if vencimento:
        try:
            dt.date.fromisoformat(vencimento)
        except ValueError:
            raise ValueError("vencimento deve ser AAAA-MM-DD") from None
    if para_quem and con.execute("select 1 from pessoa where id=?", (para_quem,)).fetchone() is None:
        raise ValueError(f"pessoa {para_quem!r} não existe")
    if anexo_base64:
        if enviar_ao_paperless is None:
            raise ValueError("para guardar o anexo é preciso o Paperless configurado")
        anexo_paperless_id = enviar_ao_paperless(base64.b64decode(anexo_base64), f"pedido-{pessoa['id']}.pdf")
    pid = con.execute(
        "insert into pedido(solicitante_pessoa_id, canal, mensagem_original, descricao, valor_centavos, vencimento, anexo_paperless_id, pix_chave, "
        "linha_digitavel, para_quem_id, criado_em, solicitante_ident) values (?,?,?,?,?,?,?,?,?,?,?,?)",
        (pessoa["id"], canal, mensagem_original, descricao, centavos, vencimento, anexo_paperless_id, pix_chave, linha_digitavel, para_quem, _agora(), solicitante)).lastrowid
    return RegistroPedido(pid, "pendente", f"Anotado, {pessoa['nome']}. O Ricardo vai ver.")


def estado(con, pedido_id: int) -> dict:
    r = con.execute("select * from pedido where id=?", (pedido_id,)).fetchone()
    if r is None:
        raise LookupError(f"pedido {pedido_id} não existe")
    return dict(r)


def _aviso(con, tipo: str, payload: dict) -> None:
    con.execute("insert into aviso(tipo, payload, criado_em) values (?,?,?)", (tipo, json.dumps(payload, ensure_ascii=False), _agora()))


def decidir(con, pedido_id: int, acao: str, por: str, conta_id: int | None = None, beneficiario_id: str | None = None, mensagem: str | None = None) -> None:
    """aprovar | recusar | pedir_info. Aprovar exige conta e beneficiário, cria o compromisso do mês e avisa o canal (exceto canal 'escuta'). Tudo ou nada."""
    with transacao(con):
        _decidir(con, pedido_id, acao, por, conta_id, beneficiario_id, mensagem)


def _decidir(con, pedido_id: int, acao: str, por: str, conta_id: int | None, beneficiario_id: str | None, mensagem: str | None) -> None:
    """aprovar | recusar | pedir_info. Aprovar exige conta e beneficiário, cria o compromisso do mês e avisa o canal."""
    p = estado(con, pedido_id)
    if p["estado"] not in ("pendente", "info_pedida"):  # info_pedida continua aberto até o Ricardo decidir
        raise ValueError(f"pedido {pedido_id} já está {p['estado']}")
    if acao not in ("aprovar", "recusar", "pedir_info"):
        raise ValueError("ação inválida")
    ident = p["solicitante_ident"]  # quem enviou, exatamente (a pessoa pode ter vários números no mesmo canal)
    if acao == "aprovar":
        if conta_id is None:
            raise ValueError("escolha a conta de onde sai o pagamento")
        if not beneficiario_id:
            raise ValueError("escolha o beneficiário")
        if con.execute("select 1 from pessoa where id=?", (beneficiario_id,)).fetchone() is None:
            raise ValueError("o beneficiário não existe")
        if p["valor_centavos"] is None:
            raise ValueError("o pedido não tem valor")
        conta = con.execute("select apelido from conta where id=?", (conta_id,)).fetchone()
        if conta is None:
            raise LookupError(f"conta {conta_id} não existe")
        dia = dt.date.fromisoformat(p["vencimento"]) if p["vencimento"] else hoje_brt() + dt.timedelta(days=7)
        forma = "pix" if p["pix_chave"] else ("boleto" if p["linha_digitavel"] else "")
        con.execute(
            "insert into compromisso_linha(id, nome, extrato, vencimento, valor_tipo, valor_padrao_centavos, forma, conta, documento, pix, valido_de, valido_ate, obs) "
            "values (?,?,?,?, 'fixo', ?,?,?,?,?,?,?,?)",
            (f"pedido:{pedido_id}", p["descricao"], p["descricao"], f"dia:{dia.day}", p["valor_centavos"], forma, conta["apelido"] or "",
             p["linha_digitavel"] or "", p["pix_chave"] or "", f"{dia:%Y-%m}", f"{dia:%Y-%m}", f"pedido {pedido_id} de {p['solicitante_pessoa_id']}"))
        con.execute("update pedido set para_quem_id=? where id=?", (beneficiario_id, pedido_id))
        mensagem = mensagem or f"Anotado: {p['descricao']} entrou na fila de contas do Ricardo."
        estado_novo = "aprovado"
    else:
        estado_novo = "recusado" if acao == "recusar" else "info_pedida"
        mensagem = mensagem or ("O Ricardo não vai seguir com esse pedido." if acao == "recusar" else "O Ricardo precisa de mais informação sobre esse pedido.")
    escuta = p["canal"] == CANAL_ESCUTA  # I11: só o registro no painel; nada vai ao solicitante
    con.execute("update pedido set estado=?, decidido_em=?, decidido_por=?, mensagem_ao_solicitante=? where id=?",
                (estado_novo, _agora(), por, None if escuta else mensagem, pedido_id))
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'cobrar')", (_agora(), por, f"pedido {pedido_id} {estado_novo}"))
    if not escuta:
        _aviso(con, f"pedido_{estado_novo}", {"pedido_id": pedido_id, "canal": p["canal"], "solicitante": ident, "mensagem": mensagem})


def avisos_pendentes(con, desde: dt.datetime | None) -> list[dict]:
    """Avisos que o canal ainda não entregou (do mais antigo ao mais novo); o que o envio direto ao Telegram já mandou (telegram_em) não volta."""
    consolidar_duplicados(con, dt.datetime.now(dt.timezone.utc))  # um aviso por conta: o mais recente
    q, args = "select * from aviso where entregue_em is null and telegram_em is null", []
    if desde:
        q += " and criado_em>=?"
        args.append(desde.astimezone(dt.timezone.utc).isoformat())
    saida = []
    for r in con.execute(q + " order by id", args):
        payload = json.loads(r["payload"])
        if r["tipo"].startswith("pedido_") and isinstance(payload, dict) and payload.get("canal") == CANAL_ESCUTA:
            continue  # I11: resposta a pedido da escuta nunca é entregue no canal
        estado, payload = triar(con, r["id"], r["tipo"], payload, dt.datetime.now(dt.timezone.utc))  # mesma revalidação do Telegram
        if estado != VALE:
            continue  # resolvido (fechado) ou incerto (fica aberto): nunca vai ao Hermes
        saida.append({"id": r["id"], "tipo": r["tipo"], "payload": payload, "criado_em": r["criado_em"]})
    return saida


def marcar_entregue(con, aviso_id: int) -> None:
    con.execute("update aviso set entregue_em=? where id=?", (_agora(), aviso_id))
