"""Contatos com algo em aberto (Mensagens › Contatos): uma consulta só, SEM rede, SÓ leitura. Nada é enviado (R2); a Gabi não responde por ele (R1).
Fontes (só o que o brain já guarda): e-mail importante/emergencial sem resposta (`email_msg` + `email_respondido`, contas liberadas), reunião nos próximos
7 dias com participante conhecido (`evento` das caixas liberadas; a agenda nova guarda só a contagem de participantes, ADR-017), pedido de pagamento
aberto (`pedido`) e WhatsApp que a escuta registrou como pedido (`escuta_msg`: SÓ contagem e data, o texto nunca é lido, ADR-016).
Assunto, remetente e título são dado de terceiros (R14): saem como texto, nunca como instrução."""
import datetime as dt
import hashlib
import json
from email.utils import parseaddr

from gabi.agenda import consulta as agenda
from gabi.cobrar.cadastro import dados
from gabi.correio.consulta import dias_em_aberto
from gabi.correio.regras import endereco
from gabi.contatos.telefone import normalizar_telefone
from gabi.contatos.contatos import nome_do_numero

JANELA_AGENDA_DIAS = 7
RETIDA_DIAS_PADRAO = 14
LIMITE = 100
ABAS = {"email": ("msgs", "prioridades"), "agenda": ("agenda", None), "pedido": ("caixa", "pedidos"), "whatsapp": ("cadastros", "escuta")}


def _utc(t: dt.datetime | None) -> dt.datetime:
    t = t or dt.datetime.now(dt.timezone.utc)
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def _ler(iso) -> dt.datetime | None:
    try:
        t = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return _utc(t).astimezone(dt.timezone.utc)


def _dias(desde: dt.datetime | None, agora: dt.datetime) -> int | None:
    return None if desde is None else max(0, (agora - desde).days)


def mascarar_numero(numero: str) -> str:
    """'+5511987654321' -> '+55 *******4321': só o DDI e os 4 últimos dígitos."""
    d = "".join(c for c in numero if c.isdigit())
    return f"+{d[:2]} {'*' * max(len(d) - 6, 3)}{d[-4:]}" if len(d) >= 8 else "número oculto"


class _Pessoas:
    """Índice e-mail/telefone -> pessoa ativa (pela `pessoa.dados`: `emails` e `canais` 'email:' / 'whatsapp:')."""

    def __init__(self, con):
        self.por_email: dict[str, tuple[str, str]] = {}
        self.por_numero: dict[str, tuple[str, str]] = {}
        self.enderecos: dict[str, set[str]] = {}  # pessoa_id -> endereços (minúsculos)
        for p in con.execute("select id, nome, dados from pessoa where excluido_em is null order by id"):
            d, quem = dados(p), (p["id"], p["nome"])
            enderecos = [x for x in (d.get("emails") or []) if isinstance(x, str)]
            for c in d.get("canais") or []:
                if not isinstance(c, str):
                    continue
                if c.startswith("email:"):
                    enderecos.append(c[6:])
                elif c.startswith("whatsapp:"):
                    n = normalizar_telefone(c[9:]) or c[9:]
                    if n:
                        self.por_numero.setdefault(n, quem)
            for e in enderecos:
                if (a := endereco(e)):
                    self.por_email.setdefault(a, quem)
                    self.enderecos.setdefault(p["id"], set()).add(a)


class _Contatos:
    def __init__(self):
        self.itens: dict[str, dict] = {}

    def abrir(self, chave: str, nome: str, tipo: str, rotulo: str, ordem: int, desde: dt.datetime | None, agora: dt.datetime, *,
              qtd: int = 1, quando: dt.datetime | None = None, detalhe: str | None = None, pessoa_id: str | None = None) -> None:
        c = self.itens.setdefault(chave, {"chave": chave, "pessoa_id": pessoa_id, "nome": nome, "abertos": []})
        area, aba = ABAS[tipo]
        c["abertos"].append({"tipo": tipo, "rotulo": rotulo, "qtd": qtd, "ordem": ordem, "desde": desde.isoformat() if desde else None,
                             "dias": _dias(desde, agora), "quando": quando.isoformat() if quando else None, "detalhe": detalhe,
                             "rota": {"area": area, "aba": aba}})


def _nome_email(remetente: str, pessoas: _Pessoas, a: str) -> tuple[str, str, str | None]:
    """(chave, nome, pessoa_id): a pessoa cadastrada, senão o nome do cabeçalho, senão o próprio endereço."""
    if a in pessoas.por_email:
        pid, nome = pessoas.por_email[a]
        return f"p:{pid}", nome, pid
    return f"e:{a}", (parseaddr(remetente or "")[0].strip() or a), None


def _emails(con, agora, pessoas, ac: _Contatos) -> None:
    corte = (agora - dt.timedelta(days=dias_em_aberto(con))).isoformat()
    por: dict[str, dict] = {}
    # o que o dono dispensou (migração 0051) não está em aberto; sem a coluna (banco antigo) a condição some
    dispensada = " and m.dispensada_em is null" if any(c[1] == "dispensada_em" for c in con.execute("pragma table_info(email_msg)")) else ""
    # contas liberadas (estado 'sim'); fora lixeira e lixo; lista de distribuição não é gente esperando resposta
    for m in con.execute(
            "select m.fonte_id, m.remetente, m.recebida_em, m.classe from email_msg m join email_fonte f on f.id=m.fonte_id "
            "where f.estado='sim' and m.estado in ('classificada','alertada') and m.classe in ('emergencial','importante') and m.lista=0 and m.recebida_em>=?" + dispensada + " "
            "order by m.recebida_em", (corte,)):
        a = endereco(m["remetente"])
        if a is None or con.execute("select 1 from email_respondido where fonte_id=? and endereco=?", (m["fonte_id"], a)).fetchone():
            continue  # sem endereço válido não há como ligar a uma pessoa; já respondido não está em aberto
        chave, nome, pid = _nome_email(m["remetente"], pessoas, a)
        r = por.setdefault(chave, {"nome": nome, "pid": pid, "emerg": 0, "qtd": 0, "desde": None})
        r["qtd"] += 1
        r["emerg"] += m["classe"] == "emergencial"
        t = _ler(m["recebida_em"])
        if t and (r["desde"] is None or t < r["desde"]):
            r["desde"] = t
    for chave, r in por.items():
        emerg = r["emerg"] > 0
        rotulo = ("E-mail emergencial sem resposta" if emerg else "E-mail importante sem resposta") + (f" ({r['qtd']})" if r["qtd"] > 1 else "")
        ac.abrir(chave, r["nome"], "email", rotulo, 0 if emerg else 2, r["desde"], agora, qtd=r["qtd"], pessoa_id=r["pid"])


def _titulo(con, titulo: str | None, painel: bool) -> str | None:
    """A tabela `evento` não marca compromisso privado: com a política `agenda.privados` diferente de 'mostrar' o título é mascarado (conservador)."""
    pol = agenda.politica_privados(con)
    return agenda.MASCARA if pol == "ocultar" or (pol == "so_painel" and not painel) else titulo


def _agenda(con, agora, pessoas, ac: _Contatos, painel: bool) -> None:
    donos = {r[0].lower() for r in con.execute("select endereco from caixa_email union select conta from email_fonte union select conta from agenda_fonte") if r[0]}
    limite = agora + dt.timedelta(days=JANELA_AGENDA_DIAS)
    vistos: set = set()  # o mesmo compromisso nas duas caixas conta uma vez
    for e in con.execute("select e.inicio, e.titulo, e.participantes from evento e join caixa_email c on c.id=e.caixa_id where c.estado='sim' order by e.inicio, e.id"):
        ini = _ler(e["inicio"])
        if ini is None or ini < agora or ini > limite:
            continue  # reunião passada não conta
        try:
            lista = json.loads(e["participantes"] or "[]")
        except (TypeError, ValueError):
            continue
        dias = (ini.astimezone(_fuso(con)).date() - agora.astimezone(_fuso(con)).date()).days
        rotulo = "Reunião hoje" if dias == 0 else "Reunião amanhã" if dias == 1 else f"Reunião em {dias} dias"
        for p in {a for x in (lista if isinstance(lista, list) else []) if isinstance(x, str) and (a := endereco(x)) and a not in donos}:
            chave, nome, pid = _nome_email(p, pessoas, p)
            if (chave, ini, e["titulo"]) in vistos:
                continue
            vistos.add((chave, ini, e["titulo"]))
            ac.abrir(chave, nome, "agenda", rotulo, 1 if dias <= 1 else 3, None, agora, quando=ini, detalhe=_titulo(con, e["titulo"], painel), pessoa_id=pid)


def _fuso(con):
    from gabi.agenda import tempo
    return tempo._zona(agenda.fuso_da_agenda(con))


def _pedidos(con, agora, ac: _Contatos) -> None:
    for p in con.execute("select p.solicitante_pessoa_id as pid, s.nome, count(*) as n, min(p.criado_em) as desde from pedido p join pessoa s on s.id=p.solicitante_pessoa_id "
                         "where p.estado in ('pendente','info_pedida') and s.excluido_em is null group by p.solicitante_pessoa_id, s.nome"):
        n = p["n"]
        ac.abrir(f"p:{p['pid']}", p["nome"], "pedido", "Pedido aguardando você" + (f" ({n})" if n > 1 else ""), 2, _ler(p["desde"]), agora, qtd=n, pessoa_id=p["pid"])


def _whatsapp(con, agora, pessoas, ac: _Contatos) -> None:
    r = con.execute("select valor from parametro where chave='escuta.retida_dias'").fetchone()
    try:
        dias = json.loads(r[0]) if r else RETIDA_DIAS_PADRAO
    except (TypeError, ValueError):
        dias = RETIDA_DIAS_PADRAO
    dias = dias if isinstance(dias, int) and not isinstance(dias, bool) and dias > 0 else RETIDA_DIAS_PADRAO
    corte = (agora - dt.timedelta(days=dias)).isoformat()
    por: dict[str, dict] = {}
    # NUNCA seleciona `texto`: só número, data e contagem (ADR-016)
    for m in con.execute("select de, recebida_em from escuta_msg where tipo='pedido' and grupo=0 and estado in ('processada','retida') and recebida_em>=? order by recebida_em", (corte,)):
        n = m["de"]
        est = con.execute("select estado, nome from escuta_remetente where numero=?", (n,)).fetchone()
        if est and est["estado"] in ("ignorado", "bloqueado"):
            continue
        pessoa = pessoas.por_numero.get(n)
        t = _ler(m["recebida_em"])
        if pessoa and con.execute("select 1 from pedido where solicitante_pessoa_id=? and canal='escuta' and criado_em>=?", (pessoa[0], m["recebida_em"])).fetchone():
            continue  # já virou pedido (aparece como "pedido") ou já foi decidido
        if pessoa:
            chave, nome, pid = f"p:{pessoa[0]}", pessoa[1], pessoa[0]
        else:
            nome = (est["nome"] if est and est["nome"] else None) or nome_do_numero(con, n) or mascarar_numero(n)
            chave, pid = "w:" + hashlib.sha1(n.encode()).hexdigest()[:10], None  # chave opaca: o número inteiro não sai
        x = por.setdefault(chave, {"nome": nome, "pid": pid, "qtd": 0, "desde": None, "num": n})
        x["qtd"] += 1
        if t and (x["desde"] is None or t < x["desde"]):
            x["desde"] = t
    for chave, x in por.items():
        n = x["qtd"]
        det = mascarar_numero(x["num"]) if x["nome"] != mascarar_numero(x["num"]) else None
        ac.abrir(chave, x["nome"], "whatsapp", "Pediu algo no WhatsApp" + (f" ({n} mensagens)" if n > 1 else ""), 2, x["desde"], agora, qtd=n, detalhe=det, pessoa_id=x["pid"])


def _frentes_por_endereco(con) -> dict[str, set[str]]:
    """Endereço -> nomes das frentes onde um e-mail DESSE remetente foi confirmado (`item_frente` tipo email, estado confirmado, R1) em caixa
    liberada. É o único vínculo real entre frente e pessoa; `tarefa` e os demais itens não têm remetente, então não entram (nada é inventado)."""
    por: dict[str, set[str]] = {}
    for r in con.execute(
            "select f.nome, i.remetente from item_frente x join frente f on f.id=x.frente_id join item_email i on i.id=x.ref_id "
            "join caixa_email c on c.id=i.caixa_id where x.tipo='email' and x.estado='confirmado' and c.estado='sim'"):
        if (a := endereco(r["remetente"])):
            por.setdefault(a, set()).add(r["nome"])
    return por


def contatos_em_aberto(con, agora: dt.datetime | None = None, *, painel: bool = False) -> dict:
    """`{itens, total}`: contatos com algo em aberto, o mais urgente primeiro (ordem do pior item, depois o mais antigo, depois o nome).
    `painel=True` só na rota do painel (política `agenda.privados=so_painel`)."""
    agora = _utc(agora)
    pessoas, ac = _Pessoas(con), _Contatos()
    _emails(con, agora, pessoas, ac)
    _agenda(con, agora, pessoas, ac, painel)
    _pedidos(con, agora, ac)
    _whatsapp(con, agora, pessoas, ac)
    frentes = _frentes_por_endereco(con)
    itens = []
    for c in ac.itens.values():
        enderecos = pessoas.enderecos.get(c["pessoa_id"], set()) if c["pessoa_id"] else {c["chave"][2:]} if c["chave"].startswith("e:") else set()
        c["frentes"] = sorted({n for a in enderecos for n in frentes.get(a, ())}, key=str.casefold)
        c["abertos"].sort(key=lambda a: (a["ordem"], -(a["dias"] or 0)))
        c["urgencia"] = c["abertos"][0]["ordem"]
        c["dias"] = max((a["dias"] or 0) for a in c["abertos"])
        c["tipos"] = sorted({a["tipo"] for a in c["abertos"]})
        for a in c["abertos"]:
            a.pop("ordem")
        itens.append(c)
    itens.sort(key=lambda c: (c["urgencia"], -c["dias"], c["nome"].casefold(), c["chave"]))
    return {"total": len(itens), "itens": itens[:LIMITE]}
