"""Criação e ciclo de vida das propostas de envio (evento de agenda, mensagem do Teams) que só saem depois do "Enviar" do dono no painel.
Consome: parametro (envios.escrita, envios.contas_agenda), agenda_fonte, agenda_evento (convites), teams_fonte, teams_conversa, contato_google e contato_google_email. Grava: envio_proposta (migração 0076).
Sem rede e sem envio: aqui só se valida, resolve nomes e grava o conteúdo canônico. Título, texto, nome e e-mail nunca vão para log nem para mensagem de erro: as falhas são códigos fixos (ErroEnvio.codigo)."""
import base64
import datetime as dt
import hashlib
import json
import re
import secrets
import unicodedata
from zoneinfo import ZoneInfo

from gabi.db import transacao

FUSO = "America/Sao_Paulo"
_SP = ZoneInfo(FUSO)
_UTC = dt.timezone.utc
_EMAIL = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")
_DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
MAX_TITULO, MIN_DURACAO, MAX_DURACAO, MAX_CONVIDADOS, MAX_TEXTO, MAX_DESCRICAO = 200, 5, 720, 30, 4000, 2000


class ErroEnvio(Exception):
    """Falha de proposta com código fixo (nunca texto de usuário); `candidatos` só nos casos ambíguos."""

    def __init__(self, codigo: str, mensagem: str = "", candidatos: list[dict] | None = None):
        super().__init__(codigo)
        self.codigo, self.mensagem, self.candidatos = codigo, mensagem or codigo, candidatos


def _parametro(con, chave: str, padrao):
    r = con.execute("select valor from parametro where chave=?", (chave,)).fetchone()
    if r is None:
        return padrao
    try:
        return json.loads(r[0])
    except (ValueError, TypeError):
        return padrao


def escrita_ligada(con) -> bool:
    """Só o valor JSON "ligado" liga; ausente ou qualquer outra coisa = desligado."""
    return _parametro(con, "envios.escrita", None) == "ligado"


def contas_agenda(con) -> list[str]:
    v = _parametro(con, "envios.contas_agenda", [])
    if not isinstance(v, list):
        return []
    return list(dict.fromkeys(x.strip().lower() for x in v if isinstance(x, str) and x.strip()))


def provedor_da_conta(con, conta: str) -> str | None:
    r = con.execute("select provedor from agenda_fonte where lower(conta)=? and calendario_id='primary'", (conta.strip().lower(),)).fetchone()
    return r[0] if r else None


def contas_teams(con) -> list[str]:
    return [r[0].lower() for r in con.execute("select conta from teams_fonte where estado='sim' order by conta")]


def normalizar_nome(s: str) -> str:
    """Casefold sem acento, espaços colapsados."""
    sem = "".join(c for c in unicodedata.normalize("NFD", s or "") if not unicodedata.combining(c))
    return " ".join(sem.casefold().split())


def _invalida():
    return ErroEnvio("requisicao_invalida")


def resolver_convidados(con, itens: list[str]) -> list[str]:
    """E-mail vira minúsculo; nome casa por igualdade do nome inteiro (sem caixa e acento) com contato_google, de qualquer conta.
    Nome com 0 ou mais de 1 e-mail: convidado_ambiguo com os candidatos. Sem duplicar, na ordem dada."""
    saida: list[str] = []
    for item in itens:
        if not isinstance(item, str) or not item.strip():
            raise ErroEnvio("convidado_invalido")
        if "@" in item:
            email = item.strip().lower()
            if not _EMAIL.match(email):
                raise ErroEnvio("convidado_invalido")
            achados = [email]
        else:
            alvo = normalizar_nome(item)
            achados, cands = [], {}
            for r in con.execute("select g.nome, e.email from contato_google g join contato_google_email e on e.conta=g.conta and e.telefone=g.telefone where g.nome is not null"):
                if normalizar_nome(r["nome"]) == alvo and r["email"].strip():
                    cands.setdefault(r["email"].strip().lower(), r["nome"])
            achados = list(cands)
            if len(achados) != 1:
                raise ErroEnvio("convidado_ambiguo", candidatos=[{"nome": n, "email": e} for e, n in cands.items()])
        if achados[0] not in saida:
            saida.append(achados[0])
    return saida


def _conta_teams(con, conta: str) -> str:
    c = (conta or "").strip().lower()
    if c not in contas_teams(con):
        raise ErroEnvio("conta_nao_permitida")
    return c


def resolver_chat(con, conta: str, nome: str) -> dict:
    """Chat do Teams da conta pelo `de_nome` (sem caixa e acento); 0 ou mais de 1 dá destino_ambiguo.
    `de_nome` é quem por último escreveu ao Ricardo (ou o mencionou), então o chat pode ser de grupo: o `tipo` vai junto para o dono ver."""
    alvo = normalizar_nome(nome)
    achados = [r for r in con.execute("select chat_id, tipo, de_nome from teams_conversa where lower(conta)=? and de_nome is not null order by chat_id", (conta.strip().lower(),))
               if alvo and normalizar_nome(r["de_nome"]) == alvo]
    if len(achados) != 1:
        raise ErroEnvio("destino_ambiguo", candidatos=[{"nome": r["de_nome"], "tipo": r["tipo"]} for r in achados])
    return {"chat_id": achados[0]["chat_id"], "destino_nome": achados[0]["de_nome"], "tipo": achados[0]["tipo"]}


def _utc(t: dt.datetime) -> str:
    return t.astimezone(_UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonico(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _gravar(con, agora: dt.datetime, tipo: str, conta: str, obj: dict, vence: dt.datetime, antes=None) -> dict:
    """`antes(con)` roda na mesma transação, antes do insert (checagem de duplicata sem corrida)."""
    conteudo = _canonico(obj)
    chave = base64.b32hexencode(secrets.token_bytes(16)).decode().lower().rstrip("=")
    criada, vence_em = _utc(agora), _utc(vence)
    with transacao(con, imediata=True):
        if antes is not None:
            antes(con)
        cur = con.execute("insert into envio_proposta(tipo, conta, conteudo, hash, chave, criada_em, vence_em) values (?,?,?,?,?,?,?)",
                          (tipo, conta, conteudo, hashlib.sha256(conteudo.encode()).hexdigest(), chave, criada, vence_em))
    return {"id": cur.lastrowid, "estado": "pendente", "vence_em": vence_em}


def _texto(texto) -> str:
    if not isinstance(texto, str) or not (1 <= len(texto) <= MAX_TEXTO) or not texto.strip():
        raise _invalida()
    return texto


def _inicio(inicio: str) -> dt.datetime:
    try:
        t = dt.datetime.fromisoformat(inicio.strip())
    except (ValueError, AttributeError):
        raise _invalida()
    return t.replace(tzinfo=_SP) if t.tzinfo is None else t


def criar_evento(con, agora: dt.datetime, *, conta, titulo, inicio, duracao_min, convidados, descricao="", online=True) -> dict:
    if not isinstance(titulo, str) or not (1 <= len(titulo) <= MAX_TITULO) or not titulo.strip():
        raise _invalida()
    if isinstance(duracao_min, bool) or not isinstance(duracao_min, int) or not (MIN_DURACAO <= duracao_min <= MAX_DURACAO):
        raise _invalida()
    if not isinstance(convidados, list) or not (1 <= len(convidados) <= MAX_CONVIDADOS):
        raise _invalida()
    if not isinstance(descricao, str) or len(descricao) > MAX_DESCRICAO or not isinstance(online, bool):
        raise _invalida()
    c = (conta or "").strip().lower()
    prov = provedor_da_conta(con, c) if c in contas_agenda(con) else None
    if prov is None:
        raise ErroEnvio("conta_nao_permitida")
    ini = _inicio(inicio)
    if ini <= agora:
        raise ErroEnvio("inicio_passado")
    emails = resolver_convidados(con, convidados)
    fim = ini + dt.timedelta(minutes=duracao_min)
    obj = {"conta": c, "provedor": prov, "titulo": titulo, "inicio_utc": _utc(ini), "fim_utc": _utc(fim), "fuso": FUSO,
           "convidados": emails, "descricao": descricao, "online": online}
    r = _gravar(con, agora, "evento", c, obj, min(agora + dt.timedelta(hours=24), ini))
    li, lf = ini.astimezone(_SP), fim.astimezone(_SP)
    n = len(emails)
    r["resumo"] = (f"Evento '{titulo}' {_DIAS[li.weekday()]} {li:%d/%m %H:%M}–{lf:%H:%M} ({c.split('@')[-1].split('.')[0]}), "
                   f"{n} convidado{'s' if n != 1 else ''}")
    return r


def criar_teams_chat(con, agora: dt.datetime, *, conta, chat_com, texto) -> dict:
    texto = _texto(texto)
    c = _conta_teams(con, conta)
    alvo = resolver_chat(con, c, chat_com)
    r = _gravar(con, agora, "teams_chat", c, {"conta": c, **alvo, "texto": texto}, agora + dt.timedelta(hours=24))
    r["resumo"] = f"Teams: chat com {alvo['destino_nome']}" + (" (grupo)" if alvo["tipo"] == "grupo" else "")
    return r


def criar_teams_canal(con, agora: dt.datetime, *, conta, equipe_id, canal_id, equipe_nome, canal_nome, texto) -> dict:
    texto = _texto(texto)
    c = _conta_teams(con, conta)
    if not all(isinstance(x, str) and x.strip() for x in (equipe_id, canal_id, equipe_nome, canal_nome)):
        raise _invalida()
    obj = {"conta": c, "equipe_id": equipe_id, "canal_id": canal_id, "equipe_nome": equipe_nome, "canal_nome": canal_nome, "texto": texto}
    r = _gravar(con, agora, "teams_canal", c, obj, agora + dt.timedelta(hours=24))
    r["resumo"] = f"Teams: canal {canal_nome} da equipe {equipe_nome}"
    return r


RESPOSTAS_CONVITE = ("aceitar", "talvez", "recusar")


def _hora(d: dt.datetime) -> str:
    return f"{d.hour}h" if d.minute == 0 else f"{d.hour}h{d.minute:02d}"


def _sem_duplicata(evento_id: int, serie_id: str | None, agora: dt.datetime):
    """Uma proposta aberta por convite: casa pela série (responder uma ocorrência responde a série toda) ou, avulso, pelo evento."""
    def checar(con):
        _vencer(con, agora)  # pendente vencida não bloqueia nova proposta
        campo, valor = ("$.serie_id", serie_id) if serie_id else ("$.evento_id", evento_id)
        if con.execute("select 1 from envio_proposta where tipo='convite_resposta' and estado in ('pendente','enviando') "
                       "and json_extract(conteudo, ?)=?", (campo, valor)).fetchone():
            raise ErroEnvio("proposta_duplicada")
    return checar


def criar_convite_resposta(con, agora: dt.datetime, *, conta, evento_id, resposta) -> dict:
    """Proposta de responder a um convite recebido (aceitar/talvez/recusar). Só convite pendente (needsAction), com hora, futuro e da conta;
    no máximo uma proposta aberta (pendente/enviando) por convite (série inteira, quando for série). Do organizador guarda só o nome, nunca e-mail."""
    if resposta not in RESPOSTAS_CONVITE or isinstance(evento_id, bool) or not isinstance(evento_id, int):
        raise _invalida()
    c = (conta or "").strip().lower()
    prov = provedor_da_conta(con, c) if c in contas_agenda(con) else None
    if prov is None:
        raise ErroEnvio("conta_nao_permitida")
    ev = con.execute("select e.id, e.externo_id, e.inicio_utc, e.fim_utc, e.dia_inteiro, e.titulo, e.resposta, e.organizador_nome, e.serie_id "
                     "from agenda_evento e join agenda_fonte f on f.id=e.fonte_id where e.id=? and lower(f.conta)=? and f.estado='sim'",
                     (evento_id, c)).fetchone()
    if ev is None:
        raise _invalida()
    ini, fim = dt.datetime.fromisoformat(ev["inicio_utc"].replace("Z", "+00:00")), dt.datetime.fromisoformat(ev["fim_utc"].replace("Z", "+00:00"))
    if ini <= agora:
        raise ErroEnvio("inicio_passado")
    if ev["dia_inteiro"] or ev["resposta"] != "needsAction":
        raise ErroEnvio("convite_nao_pendente")
    from gabi.agenda import convites  # convites importa este módulo
    conflita = next((x["conflita_com"] for x in convites.pendentes(con, agora) if x["evento_id"] == ev["id"]), [])
    titulo = ev["titulo"] or "(sem título)"
    obj = {"conta": c, "provedor": prov, "evento_id": ev["id"], "externo_id": ev["externo_id"], "serie_id": ev["serie_id"], "titulo": titulo,
           "inicio_utc": _utc(ini), "fim_utc": _utc(fim), "organizador_nome": ev["organizador_nome"], "resposta": resposta, "conflita_com": conflita}
    r = _gravar(con, agora, "convite_resposta", c, obj, min(agora + dt.timedelta(hours=24), ini), antes=_sem_duplicata(ev["id"], ev["serie_id"], agora))
    li, lf = ini.astimezone(_SP), fim.astimezone(_SP)
    r["resumo"] = f"Responder '{titulo}' {_DIAS[li.weekday()]} {_hora(li)}–{_hora(lf)}: {resposta}"
    return r


# ---- ciclo de vida: listar, vencer, recusar, reservar, concluir ----

_COLUNAS = "id, tipo, conta, conteudo, hash, estado, motivo, criada_em, vence_em, decidida_em, enviada_em"


def auditar(con, quem: str, agora: dt.datetime, texto: str) -> None:
    """Registra em `decisao` (origem 'envios'). O texto só leva id, tipo, conta e estado; a transação é a do chamador."""
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?,'envios')", (_utc(agora), quem, texto))


def _texto_auditoria(l, estado: str) -> str:
    return f"Envio {l['id']} ({l['tipo']}, {l['conta']}): {estado}"


def _vencer(con, agora: dt.datetime) -> None:
    """Pendentes com vence_em <= agora viram vencida (dentro da transação do chamador)."""
    con.execute("update envio_proposta set estado='vencida' where estado='pendente' and vence_em<=?", (_utc(agora),))


def listar(con, agora: dt.datetime, estado: str = "pendente") -> list[dict]:
    """Marca as vencidas e lista. estado="decididas": as 20 mais recentes não pendentes, por decidida_em desc."""
    with transacao(con, imediata=True):
        _vencer(con, agora)
        if estado == "decididas":
            linhas = con.execute(f"select {_COLUNAS} from envio_proposta where estado!='pendente' order by decidida_em desc, id desc limit 20").fetchall()
        else:
            linhas = con.execute(f"select {_COLUNAS} from envio_proposta where estado=? order by id", (estado,)).fetchall()
    return [{**{k: l[k] for k in l.keys()}, "conteudo": json.loads(l["conteudo"])} for l in linhas]


def recusar(con, id: int, quem: str, agora: dt.datetime) -> None:
    with transacao(con, imediata=True):
        l = con.execute("select id, tipo, conta, estado from envio_proposta where id=?", (id,)).fetchone()
        if l is None:
            erro = "nao_encontrado"
        elif con.execute("update envio_proposta set estado='recusada', decidida_em=?, decidida_por=? where id=? and estado='pendente'",
                         (_utc(agora), quem, id)).rowcount == 0:
            erro = "conflito"
        else:
            erro = None
            auditar(con, quem, agora, _texto_auditoria(l, "recusada"))
    if erro:
        raise ErroEnvio(erro)


def _convite_obsoleto(con, l) -> bool:
    """O convite da proposta ainda é o que o dono viu? Linha sumida, fonte desligada, já respondido (no Outlook ou antes) ou horário diferente = obsoleto.
    Qualquer coisa ilegível também é obsoleto (falha fechada)."""
    try:
        c = json.loads(l["conteudo"])
        ev = con.execute("select e.resposta, e.inicio_utc, e.fim_utc from agenda_evento e join agenda_fonte f on f.id=e.fonte_id "
                         "where e.id=? and lower(f.conta)=? and f.estado='sim'", (c["evento_id"], l["conta"])).fetchone()
        if ev is None or ev["resposta"] != "needsAction":
            return True
        mesmo = [dt.datetime.fromisoformat(a.replace("Z", "+00:00")) == dt.datetime.fromisoformat(b.replace("Z", "+00:00"))
                 for a, b in ((ev["inicio_utc"], c["inicio_utc"]), (ev["fim_utc"], c["fim_utc"]))]
        return not all(mesmo)
    except Exception:  # noqa: BLE001 - falha fechada: na dúvida, não responde
        return True


def reservar(con, id: int, hash: str, quem: str, agora: dt.datetime) -> dict:
    """Transição atômica pendente → enviando, com as checagens na ordem do spec. Vencida, conta_nao_permitida e convite_obsoleto (convite_resposta cujo
    convite mudou na agenda local) gravam o estado e só depois levantam."""
    with transacao(con, imediata=True):
        l = con.execute("select * from envio_proposta where id=?", (id,)).fetchone()
        erro = None
        if l is None:
            erro = "nao_encontrado"
        elif l["estado"] == "pendente" and l["vence_em"] <= _utc(agora):
            con.execute("update envio_proposta set estado='vencida' where id=? and estado='pendente'", (id,))
            erro = "vencida"
        elif l["estado"] != "pendente":
            erro = "conflito"
        elif l["hash"] != hash:
            erro = "hash_diferente"
        elif not escrita_ligada(con):
            erro = "envios_desligados"
        else:
            permitida = (l["conta"] in contas_agenda(con) and provedor_da_conta(con, l["conta"]) is not None) if l["tipo"] in ("evento", "convite_resposta") \
                else l["conta"] in contas_teams(con)
            if not permitida:
                con.execute("update envio_proposta set estado='falhou', motivo='conta_nao_permitida', decidida_em=?, decidida_por=? where id=? and estado='pendente'",
                            (_utc(agora), quem, id))
                auditar(con, quem, agora, _texto_auditoria(l, "falhou"))
                erro = "conta_nao_permitida"
            elif l["tipo"] == "convite_resposta" and _convite_obsoleto(con, l):
                # o Graph não acusa remarcação (mesmo id) nem resposta repetida: confere a agenda local ANTES de qualquer chamada; nada sai
                con.execute("update envio_proposta set estado='falhou', motivo='convite_obsoleto', decidida_em=?, decidida_por=? where id=? and estado='pendente'",
                            (_utc(agora), quem, id))
                auditar(con, quem, agora, _texto_auditoria(l, "falhou"))
                erro = "convite_obsoleto"
            elif con.execute("update envio_proposta set estado='enviando', decidida_em=?, decidida_por=? where id=? and estado='pendente'",
                             (_utc(agora), quem, id)).rowcount == 0:
                erro = "conflito"
            else:
                auditar(con, quem, agora, _texto_auditoria(l, "enviando"))
                return dict(con.execute("select * from envio_proposta where id=?", (id,)).fetchone())
    raise ErroEnvio(erro)


def concluir(con, id: int, estado: str, *, motivo: str | None = None, externo_id: str | None = None, agora: dt.datetime) -> None:
    """Fecha uma proposta que estava enviando: enviada, falhou ou incerto. `motivo` é código fixo, nunca texto do provedor."""
    if estado not in ("enviada", "falhou", "incerto"):
        raise _invalida()
    with transacao(con, imediata=True):
        l = con.execute("select id, tipo, conta from envio_proposta where id=?", (id,)).fetchone()
        if l is None:
            erro = "nao_encontrado"
        elif con.execute("update envio_proposta set estado=?, motivo=?, externo_id=?, enviada_em=? where id=? and estado='enviando'",
                         (estado, motivo, externo_id, _utc(agora) if estado == "enviada" else None, id)).rowcount == 0:
            erro = "conflito"
        else:
            erro = None
            auditar(con, "sistema", agora, _texto_auditoria(l, estado))
    if erro:
        raise ErroEnvio(erro)
