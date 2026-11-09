"""Preparo de reunião (ADR-037): para um evento de hoje ou de amanhã, junta o que o brain já sabe sobre o assunto. Só leitura, sem rede.
A agenda guarda só a quantidade de participantes, não quem são: o casamento é pelas palavras do título (`termos_usados` mostra quais, para o
Hermes e o Ricardo corrigirem). Título de compromisso privado mascarado pela política da agenda não vira busca.
Consome: agenda.consulta, atividades, projetos, cobrar.a_receber, correio (email_msg), mcp.ferramentas_ver.buscar_contatos."""
import datetime as dt
from zoneinfo import ZoneInfo

from gabi import atividades
from gabi.agenda import consulta
from gabi.cobrar.a_receber import a_receber_do_mes

BRT = ZoneInfo("America/Sao_Paulo")
GENERICAS = {"reuniao", "call", "alinhamento", "sync", "meeting", "weekly", "daily", "encontro", "conversa", "com", "para", "sobre", "online", "teams", "meet",
             "revisao", "follow", "followup", "check", "catch", "bate", "papo", "reuniao:"}
EMAIL_DIAS = 14
MAX_TERMOS = 4
MAX_POR_BLOCO = 5


def _termos(titulo: str) -> list[str]:
    if not titulo or titulo == consulta.MASCARA:
        return []
    vistos: dict[str, None] = {}
    for p in atividades._norm(titulo).replace("/", " ").replace("-", " ").replace(",", " ").split():
        p = p.strip(".:;()[]\"'")
        if len(p) >= 3 and p not in GENERICAS and not p.isdigit():
            vistos.setdefault(p)
    return list(vistos)[:MAX_TERMOS]


def _escolher(con, agora: dt.datetime, evento: str) -> dict | None:
    fuso = consulta.fuso_da_agenda(con)
    hoje = consulta.dia_local(agora, fuso)
    itens = consulta.agenda_intervalo(con, hoje.isoformat(), (hoje + dt.timedelta(days=1)).isoformat(), fuso)
    termo = str(evento or "").strip()
    if termo.isdigit():
        return next((i for i in itens if i["id"] == int(termo)), None)
    if termo:
        t = atividades._norm(termo)
        return next((i for i in itens if t in atividades._norm(i["titulo"])), None)
    agora_local = agora.astimezone(ZoneInfo(fuso)).isoformat(timespec="seconds")
    futuros = [i for i in itens if i["inicio_local"] and i["inicio_local"] >= agora_local[:19]]
    return futuros[0] if futuros else None


def preparar_reuniao(con, agora: dt.datetime, evento: str = "") -> dict:
    ev = _escolher(con, agora, evento)
    if ev is None:
        return {"evento": None, "termos_usados": [], "contatos": [], "atividades": [], "projetos": [], "a_receber": [], "emails": []}
    from gabi.mcp.ferramentas_ver import buscar_contatos  # import tardio: o MCP importa este módulo
    termos = _termos(ev["titulo"])
    contatos, ativs, projs, emails = {}, {}, {}, {}
    hoje = agora.astimezone(BRT).date()
    desde = (agora - dt.timedelta(days=EMAIL_DIAS)).isoformat()
    receber = []
    recebiveis = a_receber_do_mes(con, hoje) if termos else {"recorrentes": [], "notas": []}
    for t in termos:
        for c in buscar_contatos(con, t, 3).get("itens", []):
            contatos.setdefault(c.get("nome") or str(c), {"nome": c.get("nome"), "emails": c.get("emails", []), "telefones": c.get("telefones", [])})
        for a in atividades.abertas_por_texto(con, t):
            ativs.setdefault(a["id"], {"id": a["id"], "texto": a["texto"], "vence_em": a["vence_em"], "prazo": a["prazo"]})
        for p in con.execute("select id, nome, prazo from projeto where status='ativo'"):
            if t in atividades._norm(p["nome"]):
                projs.setdefault(p["id"], {"id": p["id"], "nome": p["nome"], "prazo": p["prazo"]})
        like = f"%{t}%"
        for m in con.execute("select m.id, m.remetente, m.assunto, m.recebida_em from email_msg m join email_fonte f on f.id=m.fonte_id "
                             "where f.estado='sim' and m.estado!='na_lixeira' and m.recebida_em>=? and (lower(m.remetente) like ? or lower(m.assunto) like ?) "
                             "order by m.recebida_em desc limit 20", (desde, like, like)):
            emails.setdefault(m["id"], {"mensagem_id": m["id"], "remetente": m["remetente"], "assunto": m["assunto"], "recebida_em": m["recebida_em"]})
    nomes_vistos = set()
    for i in recebiveis["recorrentes"] + recebiveis["notas"]:
        if i["situacao"] in ("recebido",) or i["pagador"] in nomes_vistos:
            continue
        if any(t in atividades._norm(i["pagador"]) for t in termos):
            nomes_vistos.add(i["pagador"])
            receber.append({"pagador": i["pagador"], "situacao": i["situacao"], "valor_centavos": i["esperado_centavos"], "dias_atraso": i.get("dias_atraso")})
    return {"evento": {k: ev[k] for k in ("id", "titulo", "inicio_local", "fim_local", "link_reuniao", "fonte")}, "termos_usados": termos,
            "contatos": list(contatos.values())[:MAX_POR_BLOCO], "atividades": list(ativs.values())[:MAX_POR_BLOCO],
            "projetos": list(projs.values())[:MAX_POR_BLOCO], "a_receber": receber[:MAX_POR_BLOCO], "emails": list(emails.values())[:MAX_POR_BLOCO]}
