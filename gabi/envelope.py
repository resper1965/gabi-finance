"""Envelope de toda resposta de leitura: `dados_ate` vem da última rodada CONFERIDA, não da última tentativa (R4/Review 4)."""
import datetime as dt
import json
import sqlite3

LIMITE_DESATUALIZADO = dt.timedelta(days=3)
# FONTE ÚNICA de verdade do frescor: {fonte (nome em rodada.fonte): limite | None}. Toda fonte passada a registrar_rodada() DEVE estar aqui
# (tests/test_envelope.py varre o código): quem adiciona uma fonte escolhe o limite.
#   limite  -> conta em dados_ate/desatualizado; estado "parada" se a última rodada válida for mais velha que o limite.
#   None    -> ignorada (não é dado servido: backup, exportação semanal, saldos com rodada própria, staging).
#   ausente -> listada (ultima/estado ok|erro) mas NUNCA conta em dados_ate/desatualizado.
# Só as fontes em COM_CONFERENCIA têm conceito de conferência: valem pela última rodada `conferida=1` (dinheiro/conferencia.marcar_conferida).
# As demais valem pela última rodada `status='ok'`, contra o limite da própria agenda (timers em deploy/).
FONTES = {
    "open-finance": LIMITE_DESATUALIZADO,
    "notas-nibo": dt.timedelta(hours=30),               # diária 06:40
    "agenda": dt.timedelta(hours=12),                   # idem (gabi-brain-agenda.timer); só conta com agenda_fonte liberada
    "correio": dt.timedelta(hours=12),                  # idem (gabi-brain-correio.timer); só conta com email_fonte liberada
    "open-finance-saldos": None, "backup": None, "exportacao": None, "importacao-staging": None,
    "documentos": None,  # leitura diária do Paperless só gera propostas; não é dado servido (OnFailure do timer avisa)
    "teams": None,  # timers instalados e desligados até o Ricardo ligar; fontes None são filtradas (ficam fora da lista) e nunca contam em dados_ate
}
COM_CONFERENCIA = ("open-finance",)
# Esperadas: devem aparecer mesmo sem nenhuma rodada (cliente sem token, timer que nunca disparou); sem rodada = nao_conferida = desatualizado.
ESPERADAS = ("notas-nibo",)
# Fontes cortadas pela ADR-023: as rodadas antigas ficam no banco (histórico), mas nunca entram na lista nem no dados_ate.
CORTADAS = frozenset({"trabalho", "comprovantes-paperless", "exames", "reembolso-saude", "escuta"})
BRT = dt.timezone(dt.timedelta(hours=-3))
LIMITE_BANCO = dt.timedelta(hours=24)  # idade máxima da última atualização que o PROVEDOR declarou para cada banco (`dinheiro.sync_banco`)
HORAS_RODADAS = (6, 14)  # espelha OnCalendar de deploy/gabi-brain-extratos.timer (tests/test_envelope.py confere)


def _utc(s: str) -> dt.datetime:
    d = dt.datetime.fromisoformat(s)
    return d.replace(tzinfo=dt.timezone.utc) if d.tzinfo is None else d.astimezone(dt.timezone.utc)


def _z(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def proxima_rodada(agora: dt.datetime) -> str:
    """Próxima rodada de extratos (UTC, ISO Z), pelos horários de Brasília do timer."""
    b = agora.astimezone(BRT)
    for dia in (0, 1):
        for h in HORAS_RODADAS:
            c = (b + dt.timedelta(days=dia)).replace(hour=h, minute=0, second=0, microsecond=0)
            if c > b:
                return _z(c.astimezone(dt.timezone.utc))
    raise AssertionError("inalcançável")


def _em_uso(con, tabela: str) -> bool:
    """Há linha liberada (estado 'sim') em `tabela`; a tabela pode faltar em bancos antigos."""
    try:
        return bool(con.execute(f"select 1 from {tabela} where estado='sim' limit 1").fetchone())
    except sqlite3.OperationalError as e:
        if "no such table" not in str(e):
            raise
        return False


def _em_espera(con) -> set[str]:
    """Fontes que o Ricardo pôs em espera (parâmetro `fontes.em_espera`, lista JSON; p.ex. Nibo aguardando chave): aparecem como
    `em_espera` e não contam em dados_ate/desatualizado. Valor ausente ou estranho = nenhuma."""
    r = con.execute("select valor from parametro where chave='fontes.em_espera'").fetchone()
    try:
        v = json.loads(r[0]) if r else []
    except (TypeError, ValueError):
        return set()
    return {x for x in v if isinstance(x, str)} if isinstance(v, list) else set()


def _agenda_em_uso(con) -> bool:
    """`agenda` só vale como fonte com alguma fonte de agenda liberada."""
    return _em_uso(con, "agenda_fonte")


def _correio_em_uso(con) -> bool:
    """`correio` só vale como fonte com alguma conta de e-mail liberada (`email_fonte` em estado 'sim')."""
    return _em_uso(con, "email_fonte")


def bancos_antigos(con, agora: dt.datetime) -> list[dict]:
    """Bancos que o provedor não atualiza há mais de 24 h, do mais antigo ao mais novo: [{banco, desde}]. Parâmetro ausente, corrompido ou com data inválida não conta.
    A rodada pode sair `conferida` com saldo velho; esta é a idade real do dado."""
    r = con.execute("select valor from parametro where chave='dinheiro.sync_banco'").fetchone()
    try:
        bancos = json.loads(r[0]) if r else {}
    except (ValueError, TypeError):
        return []
    saida = []
    for nome, lu in (bancos.items() if isinstance(bancos, dict) else []):
        try:
            quando = _utc(str(lu).replace("Z", "+00:00"))
        except ValueError:
            continue
        if agora - quando > LIMITE_BANCO:
            saida.append((quando, {"banco": nome, "desde": str(lu)}))
    return [x for _, x in sorted(saida, key=lambda t: (t[0], t[1]["banco"]))]


def envelope(con, dados, agora: dt.datetime | None = None, fontes: tuple[str, ...] | None = None) -> dict:
    """`fontes=None`: todas as fontes (comportamento padrão). Tupla: só essas fontes entram na lista e no cálculo; `()` = ferramenta sem
    dado que envelhece (nunca desatualizado, dados_ate None). `bancos_antigos` é frescor do open-finance: só vale com `None` ou com "open-finance" na tupla."""
    agora = agora or dt.datetime.now(dt.timezone.utc)
    if fontes is not None:
        fontes = tuple(fontes)
        if not fontes:
            return {"dados_ate": None, "desatualizado": False, "proxima_rodada": proxima_rodada(agora), "fontes": [], "dados": dados}
    filtro, fontes = fontes, None  # `fontes` abaixo é a lista de saída
    fontes, ultimas, falta, atrasada = [], [], False, False
    nomes = {r[0] for r in con.execute("select distinct fonte from rodada")}
    nomes |= set(ESPERADAS)
    nomes.add("agenda") if _agenda_em_uso(con) else nomes.discard("agenda")
    nomes.add("correio") if _correio_em_uso(con) else nomes.discard("correio")
    nomes = sorted(n for n in nomes if n not in CORTADAS and not (n in FONTES and FONTES[n] is None))
    if filtro is not None:
        nomes = [n for n in nomes if n in filtro]
    espera = _em_espera(con)
    for nome in nomes:
        if nome in espera:
            ok = con.execute("select max(fim) from rodada where fonte=? and status='ok'", (nome,)).fetchone()[0]
            fontes.append({"nome": nome, "estado": "em_espera", "ultima": _z(_utc(ok)) if ok else None})
            continue
        conta = FONTES.get(nome) is not None
        tent = con.execute("select status, conferida from rodada where fonte=? order by id desc limit 1", (nome,)).fetchone()
        if nome in COM_CONFERENCIA:
            conf = con.execute("select max(fim) from rodada where fonte=? and conferida=1", (nome,)).fetchone()[0]
            ultima = _utc(conf) if conf else None
            if tent["status"] == "erro":
                estado = "erro"
            elif not tent["conferida"]:
                estado = "nao_conferida"
            elif ultima is None or agora - ultima > FONTES[nome]:
                estado = "parada"
            else:
                estado = "ok"
            # extrato com última tentativa em erro segue valendo pela última conferida até o limite (comportamento antigo, coberto por teste)
        else:
            ok = con.execute("select max(fim) from rodada where fonte=? and status='ok'", (nome,)).fetchone()[0]
            ultima = _utc(ok) if ok else None
            if tent is not None and tent["status"] == "erro":
                estado = "erro"
            elif ultima is None:
                estado = "nao_conferida"  # nunca rodou com sucesso (ou nunca rodou)
            elif conta and agora - ultima > FONTES[nome]:
                estado = "parada"
            else:
                estado = "ok"
            atrasada = atrasada or (conta and estado in ("erro", "parada"))
        if conta:
            if ultima is None:
                falta = True
            else:
                ultimas.append(ultima)
            atrasada = atrasada or (nome in COM_CONFERENCIA and estado == "parada")
        fontes.append({"nome": nome, "estado": estado, "ultima": _z(ultima) if ultima else None})
    dados_ate = None if (falta or not ultimas) else min(ultimas)  # a fonte mais velha manda
    antigos = bancos_antigos(con, agora) if filtro is None or "open-finance" in filtro else []
    saida = {"dados_ate": _z(dados_ate) if dados_ate else None,
             "desatualizado": dados_ate is None or atrasada or bool(antigos) or agora - dados_ate > LIMITE_DESATUALIZADO,
             "proxima_rodada": proxima_rodada(agora), "fontes": fontes, "dados": dados}
    if antigos:
        saida["bancos_antigos"] = antigos  # só aparece quando há banco parado: nomeia quem e desde quando
    return saida
