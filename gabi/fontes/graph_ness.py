"""Microsoft Graph da ness (resper@ness.com.br): LEITURA de contatos, agenda e e-mail; as únicas escritas são MOVER mensagem de e-mail entre a Caixa de
Entrada e os Itens Excluídos (a lixeira; o Exchange a esvazia sozinho) e criar/corrigir contato, delegado a `graph_ness_contatos` (ADR-020). Criar evento e escrever no Teams (token delegado, ADR-024) com proposta
aprovada vivem em `graph_ness_envios`; aqui só os métodos que delegam. Neste arquivo não existe método de enviar, responder, encaminhar, apagar de vez nem de
escrever em agenda: o POST aqui é só o do token e o `/move` com destino fixo (um teste varre o código). Só o serviço `gabi-brain-fontes` tem rede e segredos (R5);
o resto do brain chega aqui pela ponte (`PonteGraph`). Autenticação do app por client credentials com secret (M365_TENANT_ID, M365_CLIENT_ID,
M365_CLIENT_SECRET no ambiente do serviço). O app tem permissão no tenant inteiro: a conta lida vem sempre de `M365_CONTAS` (padrão só
resper@ness.com.br), nunca de entrada livre. Segredo, token e corpo de resposta nunca entram em erro, log ou repr. Docs: docs/fontes/graph-ness.md."""
import datetime as dt
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from typing import Callable

from gabi.fontes._http import com_retry
from gabi.fontes.google_agenda import ResultadoEventos
from gabi.fontes.google_contatos import MAX_EMAILS, _EMAIL
from gabi.fontes.google_email import (MAX_CARGA_MSGS, MAX_ENDERECOS, MAX_ENDERECOS_CONSULTA, MAX_ENVIADOS_MSGS, MAX_IDS_POR_CHAMADA, TAM_ASSUNTO,
                                      TAM_TRECHO, ResultadoEmail, _endereco, _lista, cortar_corpo, html_para_texto, limpar_texto)

BASE = "https://graph.microsoft.com/v1.0"
HOST = "https://graph.microsoft.com/"
LOGIN = "https://login.microsoftonline.com"
MAX_PAGINAS = 200
FOLGA_S = 300
CONTAS_PADRAO = ["resper@ness.com.br"]
_CALENDARIO = re.compile(r"^[A-Za-z0-9=_.-]{1,300}$")  # "primary" ou id do Graph (base64 com "="): nunca "/" nem espaço
_ID_MSG = re.compile(r"^[A-Za-z0-9_=-]{8,400}$")  # id imutável de mensagem (base64url): nunca "/" nem espaço
_IMUTAVEL = 'IdType="ImmutableId"'  # o id não muda quando a mensagem vai e volta dos Itens Excluídos (restaurar usa o mesmo id)
_DESTINOS = {"trash": "deleteditems", "untrash": "inbox"}  # as únicas escritas: destino fixo, nunca vindo de fora
_VENENO = (400, 404, 410, 413, 422)  # 4xx que é do id (401/403/429/5xx continuam parando a leitura)
_ID_CONTATO = re.compile(r"^[A-Za-z0-9_=-]{8,400}$")  # id de contato do Graph (base64url): nunca "/" nem espaço
_CHAT_ID = re.compile(r"^[0-9A-Za-z:@._-]{1,200}$")  # id de chat do Teams ("19:...@thread.v2"): nunca "/" nem espaço
_TIPOS_CHAT = {"oneOnOne": "um_a_um", "group": "grupo", "meeting": "grupo"}
_CAMPOS_TEAMS = "id,createdDateTime,from,messageType,mentions,deletedDateTime"  # sem body, subject nem attachments
MAX_PAGINAS_TEAMS = 5  # 5 x 50 mensagens por leitura de chat (do mais novo para o mais antigo)
_CAMPOS_MSG = "id,conversationId,from,subject,receivedDateTime,bodyPreview,isDraft,internetMessageHeaders"


class ErroGraphNess(Exception):
    """Erro tipado da fonte: só texto curto, sem segredo e sem corpo de resposta."""


class _ErroStatus(ErroGraphNess):
    """Erro de status HTTP do Graph (a mensagem é a mesma de ErroGraphNess); `status` deixa o 410 do delta ser tratado sem olhar texto."""

    def __init__(self, mensagem: str, status: int):
        super().__init__(mensagem)
        self.status = status


class _SemRedirecionamento(urllib.request.HTTPRedirectHandler):
    """O urllib copiaria o cabeçalho Authorization para o destino de um 3xx, qualquer que fosse o host: aqui o redirecionamento nunca é seguido."""

    def redirect_request(self, *a, **k):
        return None


_ABRIR = urllib.request.build_opener(_SemRedirecionamento).open


def _http_real(metodo, url, corpo=None, cabecalhos=None):
    """(status, json). O corpo de um erro NUNCA é lido (pode ecoar segredo ou texto de evento). A falha só é registrada no `except`; o erro
    tipado sai depois do bloco (sem __context__)."""
    req = urllib.request.Request(url, data=corpo, method=metodo, headers=cabecalhos or {})
    falha = None
    try:
        with _ABRIR(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        codigo = e.code
        try:
            e.close()
        except Exception:  # noqa: BLE001
            pass
        return codigo, {}
    except (OSError, ValueError) as e:
        falha = type(e).__name__
    raise ErroGraphNess(f"Graph indisponível: {falha}")


def _chamar(http, metodo, url, corpo, cab):
    """Erro de rede do http injetado vira o erro tipado, fora do `except` (sem causa nem contexto)."""
    falha = None
    try:
        return http(metodo, url, corpo, cab)
    except ErroGraphNess:
        raise
    except Exception as e:  # noqa: BLE001
        falha = type(e).__name__
    raise ErroGraphNess(f"Graph indisponível: {falha}")


class TokenApp:
    """token() -> access token do app. Guarda em memória até FOLGA_S antes de expirar."""

    def __init__(self, tenant: str, client_id: str, secret: str, http=_http_real, agora=time.time):
        self._tenant, self._id, self._secret, self._http, self._agora = tenant, client_id, secret, http, agora
        self._cache: tuple[str, float] | None = None

    def __repr__(self):
        return "TokenApp(<oculto>)"

    def __call__(self) -> str:
        if self._cache and self._agora() < self._cache[1]:
            return self._cache[0]
        corpo = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": self._id, "client_secret": self._secret,
                                        "scope": "https://graph.microsoft.com/.default"}).encode()
        url = f"{LOGIN}/{urllib.parse.quote(self._tenant, safe='')}/oauth2/v2.0/token"
        status, resp = _chamar(self._http, "POST", url, corpo, {"Content-Type": "application/x-www-form-urlencoded"})
        if status >= 400:
            raise ErroGraphNess(f"troca de token -> {status}")
        acc = resp.get("access_token") if isinstance(resp, dict) else None
        exp = resp.get("expires_in") if isinstance(resp, dict) else None
        if not isinstance(acc, str) or not acc or isinstance(exp, bool) or not isinstance(exp, (int, float)):
            raise ErroGraphNess("resposta inválida na troca de token")
        self._cache = (acc, self._agora() + exp - FOLGA_S)
        return acc

    def invalidar(self) -> None:
        self._cache = None


class GraphNess:
    """Objeto da ponte (JSON puro). Lê por GET; só escreve o move de e-mail e, delegado a `graph_ness_contatos`, criar/corrigir contato (ADR-020); evento e Teams
    aprovados (ADR-024) delegam a `graph_ness_envios`. Sem o token provider nada sai."""

    def __init__(self, token: Callable[[], str], contas: list[str], http=_http_real, agora=time.time, token_teams: Callable[[], str] | None = None):
        self._token, self._contas, self._http, self._agora = token, [c.lower() for c in contas], http, agora
        self._token_teams = token_teams  # TokenDelegado (Teams); None sem GRAPH_NESS_TEAMS_REFRESH: os envios do Teams dão `teams_sem_login`
        self._meu_ids: dict[str, str] = {}  # conta -> id AAD (Teams: de_eu / mencoes_eu)

    def __repr__(self):
        return "GraphNess(<oculto>)"

    def contas(self) -> list[str]:
        return list(self._contas)

    def _conta(self, conta) -> str:
        if not isinstance(conta, str) or conta.lower() not in self._contas:
            raise ErroGraphNess("conta não permitida")
        return conta.lower()

    def _get(self, url: str, extra: dict | None = None) -> dict:
        """GET autenticado; só para o host do Graph (o link pode vir do banco ou da resposta). Um 401 invalida o token e repete UMA vez."""
        if not isinstance(url, str) or not url.startswith(HOST):
            raise ErroGraphNess("link inválido")
        caminho = urllib.parse.urlsplit(url).path
        for tentativa in (1, 2):
            cab = {"Authorization": f"Bearer {self._token()}", **(extra or {})}
            status, resp = com_retry(lambda: _chamar(self._http, "GET", url, None, cab))
            if status == 401 and tentativa == 1 and hasattr(self._token, "invalidar"):
                self._token.invalidar()
                continue
            break
        if status >= 300:  # 3xx não é seguido (ver _SemRedirecionamento) e não é resposta
            raise _ErroStatus(f"GET {caminho} -> {status}", status)
        if not isinstance(resp, dict):
            raise ErroGraphNess("resposta inválida do Graph")
        return resp


    def listar_calendarios(self, conta: str) -> list[dict]:
        """[{id, nome, principal}] dos calendários da conta."""
        conta = self._conta(conta)
        saida = []
        for pagina in self._paginas(f"{BASE}/users/{urllib.parse.quote(conta, safe='')}/calendars"):
            for c in pagina.get("value") or []:
                if isinstance(c, dict) and isinstance(c.get("id"), str) and c["id"]:
                    saida.append({"id": c["id"], "nome": c["name"] if isinstance(c.get("name"), str) else None,
                                  "principal": c.get("isDefaultCalendar") is True})
        return saida

    def _delta(self, url: str, extra: dict | None = None) -> tuple[list[dict], str]:
        """Todas as páginas do delta -> (itens, deltaLink). Sem deltaLink no fim a resposta é inválida."""
        itens, delta = [], None
        for pagina in self._paginas(url, extra or {"Prefer": 'outlook.timezone="UTC", odata.maxpagesize=200'}):
            itens += [i for i in pagina.get("value") or [] if isinstance(i, dict)]
            delta = pagina.get("@odata.deltaLink")
        if not isinstance(delta, str) or not delta:
            raise ErroGraphNess("resposta inválida do Graph")
        return itens, delta

    def listar_eventos(self, conta: str, calendario_id: str, sync_token: str | None, janela: dict) -> dict:
        """Eventos (instâncias) do calendário na `janela` ({"de","ate"} ISO UTC); com `sync_token` (o deltaLink anterior) vem só o que mudou.
        410 numa carga incremental → recarga completa (`recarga_completa=True`). Devolve JSON puro (`asdict(ResultadoEventos)`)."""
        conta = self._conta(conta)
        if calendario_id != "primary" and not (isinstance(calendario_id, str) and _CALENDARIO.match(calendario_id)):
            raise ErroGraphNess("calendário inválido")
        if not isinstance(janela, dict) or not janela.get("de") or not janela.get("ate"):
            raise ErroGraphNess("janela inválida")
        if sync_token is not None and not (isinstance(sync_token, str) and sync_token.startswith(HOST)):
            raise ErroGraphNess("token de sincronização inválido")
        base = f"{BASE}/users/{urllib.parse.quote(conta, safe='')}"
        if calendario_id != "primary":
            base += f"/calendars/{urllib.parse.quote(calendario_id, safe='')}"
        completa = f"{base}/calendarView/delta?" + urllib.parse.urlencode({"startDateTime": janela["de"], "endDateTime": janela["ate"]})
        recarga = False
        try:
            itens, delta = self._delta(sync_token or completa)
        except _ErroStatus as e:
            if not (sync_token and e.status == 410):
                raise
            recarga = True
            itens, delta = self._delta(completa)
        res = ResultadoEventos(novo_sync_token=delta, recarga_completa=recarga)
        for item in itens:
            if not isinstance(item.get("id"), str) or not item["id"]:
                continue
            if "@removed" in item or item.get("isCancelled") is True or _recusado_por_mim(item):
                res.cancelados.append(item["id"])  # recusado some do Outlook: some daqui (e apaga a linha já gravada)
            else:
                res.eventos.append(_evento(item))
        return asdict(res)

    def _paginas(self, url: str, extra: dict | None = None):
        """Cada página (dict) seguindo `@odata.nextLink`; link repetido ou mais de MAX_PAGINAS páginas é erro."""
        vistos = set()
        for _ in range(MAX_PAGINAS):
            resp = self._get(url, extra)
            yield resp
            url = resp.get("@odata.nextLink")
            if not url:
                return
            if url in vistos:
                break
            vistos.add(url)
        raise ErroGraphNess("paginação sem fim")

    def contatos(self, conta: str) -> list[dict]:
        """[{nome, telefone, campo[, graph_id][, emails]}] como os contatos do Google: um item por telefone (celular, casa, trabalho), cada um com os e-mails do contato;
        contato só com e-mail vira um item com `telefone: None`. Só nome, telefone e e-mail são lidos."""
        conta = self._conta(conta)
        campos = "id,displayName,mobilePhone,homePhones,businessPhones,emailAddresses"
        url = f"{BASE}/users/{urllib.parse.quote(conta, safe='')}/contacts?$select={campos}&$top=100"
        saida = []
        for pagina in self._paginas(url):
            for p in pagina.get("value") or []:
                if not isinstance(p, dict):
                    continue
                nome = p.get("displayName")
                nome = nome if isinstance(nome, str) and nome.strip() else None
                emails = _emails(p.get("emailAddresses"))
                gid = p.get("id")
                gid = gid if isinstance(gid, str) and _ID_CONTATO.match(gid) else None
                telefones = [(t, campo) for campo, lista in (("mobile", [p.get("mobilePhone")]), ("home", p.get("homePhones") or []),
                                                             ("business", p.get("businessPhones") or []))
                             for t in lista if isinstance(t, str) and t.strip()]
                for t, campo in telefones:
                    item = {"nome": nome, "telefone": t, "campo": campo}
                    if gid:
                        item["graph_id"] = gid
                    if emails:
                        item["emails"] = list(emails)
                    saida.append(item)
                if emails and not telefones:
                    saida.append({"nome": nome, "telefone": None, "emails": emails})
        return saida

    # ---------------- e-mail ----------------
    def _desde(self, dias: int) -> str:
        return (dt.datetime.fromtimestamp(self._agora(), dt.timezone.utc) - dt.timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _caixa(self, conta: str) -> str:
        return f"{BASE}/users/{urllib.parse.quote(self._conta(conta), safe='')}"

    def mensagem(self, conta: str, externo_id: str) -> dict:
        """Corpo em texto da mensagem (só GET; `Prefer: outlook.body-content-type="text"`; HTML que vier mesmo assim é convertido). Corta em MAX_CORPO."""
        if not isinstance(externo_id, str) or not _ID_MSG.match(externo_id):
            raise ErroGraphNess("id de mensagem inválido")
        try:
            resp = self._get(f"{self._caixa(conta)}/messages/{urllib.parse.quote(externo_id, safe='')}?$select=body",
                             {"Prefer": f'{_IMUTAVEL}, outlook.body-content-type="text"'})
        except _ErroStatus as e:
            if e.status == 404:
                raise ErroGraphNess("mensagem não encontrada") from None
            raise
        corpo = resp.get("body")
        if not isinstance(corpo, dict) or not isinstance(corpo.get("content"), str):
            raise ErroGraphNess("resposta inválida do Graph")
        texto = corpo["content"]
        return cortar_corpo(html_para_texto(texto) if str(corpo.get("contentType")).lower() == "html" else limpar_texto(texto))

    def listar_novos(self, conta: str, history_id: str | None, janela_dias: int) -> dict:
        """Mensagens novas na Caixa de Entrada. Sem `history_id`: carga pela janela. Com ele (o deltaLink anterior): só o que mudou; 410 (delta expirado)
        ou mais de MAX_CARGA_MSGS de uma vez → recarga da janela (`recarga_completa=True`). Rascunho e mensagem fora da entrada nunca entram.
        Devolve JSON puro (`asdict(ResultadoEmail)`); o campo `novo_history_id` leva o deltaLink."""
        base = self._caixa(conta)
        if not isinstance(janela_dias, int) or isinstance(janela_dias, bool) or not 1 <= janela_dias <= 365:
            raise ErroGraphNess("janela inválida")
        if history_id is not None and not (isinstance(history_id, str) and history_id.startswith(HOST)):
            raise ErroGraphNess("token de sincronização inválido")
        pref = {"Prefer": f'{_IMUTAVEL}, odata.maxpagesize=100'}
        completa = (f"{base}/mailFolders/inbox/messages/delta?$select=receivedDateTime&$filter="
                    + urllib.parse.quote(f"receivedDateTime ge {self._desde(janela_dias)}", safe=""))

        def carga() -> tuple[list[str], str]:
            itens, delta = self._delta(completa, pref)
            recentes = {i["id"]: i.get("receivedDateTime") or "" for i in itens if "@removed" not in i and isinstance(i.get("id"), str)}
            return [k for k, _ in sorted(recentes.items(), key=lambda p: p[1], reverse=True)][:MAX_CARGA_MSGS], delta

        recarga = False
        if history_id is None:
            ids, delta = carga()
        else:
            try:
                itens, delta = self._delta(history_id, pref)
                ids = list(dict.fromkeys(i["id"] for i in itens if "@removed" not in i and isinstance(i.get("id"), str)))
            except _ErroStatus as e:
                if e.status != 410:
                    raise
                recarga, (ids, delta) = True, carga()
            if len(ids) > MAX_CARGA_MSGS:  # chegou muita coisa de uma vez: lê só as mais recentes da janela (cabe no tempo da ponte) e avisa que recarregou
                recarga, (ids, delta) = True, carga()
        msgs = []
        for i in ids:
            if not _ID_MSG.match(i):
                continue
            try:
                resp = self._get(f"{base}/messages/{urllib.parse.quote(i, safe='')}?$select={_CAMPOS_MSG}", {"Prefer": _IMUTAVEL})
            except _ErroStatus as e:
                if e.status in _VENENO:
                    continue  # apagada entre a listagem e a leitura, ou 4xx persistente só naquele id: pula, não trava a conta
                raise
            m = _mensagem(resp)
            if m:
                msgs.append(m)
        return asdict(ResultadoEmail(msgs, delta, recarga))

    def contato_criar(self, conta: str, nome: str, telefone: str) -> dict:
        """Cria um contato (só nome e celular). A escrita vive em `graph_ness_contatos` (import aqui evita o ciclo)."""
        from gabi.fontes import graph_ness_contatos
        return graph_ness_contatos.criar(self, conta, nome, telefone)

    def contato_corrigir(self, conta: str, graph_id: str, antes: dict, depois: dict) -> dict:
        """Corrige nome e celular se o contato ainda estiver como `antes`; senão {"resultado": "alterado"} sem escrever."""
        from gabi.fontes import graph_ness_contatos
        return graph_ness_contatos.corrigir(self, conta, graph_id, antes, depois)

    def contato_renomear(self, conta: str, graph_id: str, nome_antes: str, nome_depois: str) -> dict:
        """Troca só o nome se o contato ainda estiver como `nome_antes`; senão {"resultado": "alterado"} sem escrever."""
        from gabi.fontes import graph_ness_contatos
        return graph_ness_contatos.renomear(self, conta, graph_id, nome_antes, nome_depois)

    def contato_apagar_telefone(self, conta: str, graph_id: str, campo: str, telefone_antes: str) -> dict:
        """Limpa um telefone do contato se ele ainda for `telefone_antes`; os outros números ficam."""
        from gabi.fontes import graph_ness_contatos
        return graph_ness_contatos.apagar_telefone(self, conta, graph_id, campo, telefone_antes)

    def contato_apagar(self, conta: str, graph_id: str, nome_antes: str, telefone_antes: str) -> dict:
        """Remove o contato se ainda estiver como `nome_antes`, sem e-mail e com um único telefone, `telefone_antes`."""
        from gabi.fontes import graph_ness_contatos
        return graph_ness_contatos.apagar(self, conta, graph_id, nome_antes, telefone_antes)

    def contato_adicionar_email(self, conta: str, graph_id: str, nome_antes: str, telefone_antes: str, emails: list) -> dict:
        """Acrescenta e-mails se o contato ainda estiver como `nome_antes`/`telefone_antes` e sem e-mail; senão {"resultado": "alterado"}."""
        from gabi.fontes import graph_ness_contatos
        return graph_ness_contatos.adicionar_email(self, conta, graph_id, nome_antes, telefone_antes, emails)

    # ---------------- envios aprovados (ADR-024): a escrita vive em `graph_ness_envios` ----------------
    def evento_criar(self, conta: str, chave: str, evento: dict) -> dict:
        """Cria o evento (token de app) com `transactionId` = chave; devolve {"externo_id"}."""
        from gabi.fontes import graph_ness_envios
        return graph_ness_envios.evento_criar(self, conta, chave, evento)

    def teams_equipes(self, conta: str) -> list[dict]:
        """[{id, nome}] das equipes da conta (token delegado)."""
        from gabi.fontes import graph_ness_envios
        return graph_ness_envios.teams_equipes(self, conta)

    def teams_canais(self, conta: str, equipe_id: str) -> list[dict]:
        """[{id, nome}] dos canais da equipe (token delegado)."""
        from gabi.fontes import graph_ness_envios
        return graph_ness_envios.teams_canais(self, conta, equipe_id)

    def teams_chat_enviar(self, conta: str, chat_id: str, texto: str) -> dict:
        """Escreve em chat que já existe (token delegado); devolve {"externo_id"}."""
        from gabi.fontes import graph_ness_envios
        return graph_ness_envios.teams_chat_enviar(self, conta, chat_id, texto)

    def teams_canal_enviar(self, conta: str, equipe_id: str, canal_id: str, texto: str) -> dict:
        """Posta em canal de equipe (token delegado); devolve {"externo_id"}."""
        from gabi.fontes import graph_ness_envios
        return graph_ness_envios.teams_canal_enviar(self, conta, equipe_id, canal_id, texto)

    def _enviar_mover(self, url: str, destino: str) -> int:
        """Único POST além do token: mover a mensagem para `destino` (de `_DESTINOS`). Um 401 invalida o token e repete UMA vez."""
        corpo = json.dumps({"destinationId": destino}).encode()
        for tentativa in (1, 2):
            cab = {"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json", "Prefer": _IMUTAVEL}
            status, _ = _chamar(self._http, "POST", url, corpo, cab)
            if status == 401 and tentativa == 1 and hasattr(self._token, "invalidar"):
                self._token.invalidar()
                continue
            return status
        return 401

    def _mover(self, conta: str, ids, acao: str) -> dict[str, str]:
        if acao not in _DESTINOS:  # as únicas escritas que o cliente faz; qualquer outra ação é recusada antes de chamar o Graph
            raise ErroGraphNess("ação não permitida")
        base = self._caixa(conta)
        if not isinstance(ids, (list, tuple)) or len(ids) > MAX_IDS_POR_CHAMADA:
            raise ErroGraphNess(f"no máximo {MAX_IDS_POR_CHAMADA} ids por chamada")
        for i in ids:
            if not isinstance(i, str) or not _ID_MSG.match(i):
                raise ErroGraphNess("id de mensagem inválido")
        resultado = {}
        for i in ids:
            try:
                status = self._enviar_mover(f"{base}/messages/{urllib.parse.quote(i, safe='')}/move", _DESTINOS[acao])
                resultado[i] = "ok" if status < 300 else "erro"
            except ErroGraphNess:
                resultado[i] = "erro"  # falha de um id não aborta o lote
        return resultado

    def lixeira(self, conta: str, ids) -> dict:
        """Move para os Itens Excluídos (o Exchange os esvazia sozinho). Por id: `ok` ou `erro`; a falha de um não aborta os outros."""
        return self._mover(conta, ids, "trash")

    def restaurar(self, conta: str, ids) -> dict:
        """Devolve à Caixa de Entrada (id imutável: é o mesmo id de antes de ir para os Itens Excluídos)."""
        return self._mover(conta, ids, "untrash")

    def enviados_recentes(self, conta: str, dias: int) -> list[str]:
        """Endereços de To/Cc dos e-mails que o dono enviou (os MAX_ENVIADOS_MSGS mais recentes na janela), minúsculos e sem repetir."""
        base = self._caixa(conta)
        if not isinstance(dias, int) or isinstance(dias, bool) or not 1 <= dias <= 3650:
            raise ErroGraphNess("janela inválida")
        q = urllib.parse.quote(f"sentDateTime ge {self._desde(dias)}", safe="")
        url = f"{base}/mailFolders/sentitems/messages?$select=toRecipients,ccRecipients&$top=100&$orderby=sentDateTime%20desc&$filter={q}"
        vistos: dict[str, None] = {}
        lidas = 0
        for pagina in self._paginas(url):
            for m in pagina.get("value") or []:
                if not isinstance(m, dict):
                    continue
                lidas += 1
                for campo in ("toRecipients", "ccRecipients"):
                    for r in m.get(campo) or []:
                        a = _endereco((r.get("emailAddress") or {}).get("address") if isinstance(r, dict) and isinstance(r.get("emailAddress"), dict) else None)
                        if a:
                            vistos.setdefault(a)
            if lidas >= MAX_ENVIADOS_MSGS:
                break
        return list(vistos)[:MAX_ENDERECOS]

    def respondeu_a(self, conta: str, enderecos) -> dict:
        """O dono já escreveu (To ou Cc) para cada endereço? Consulta exata nos Enviados, sem o limite da lista dos enviados recentes. Erro do Graph é erro
        tipado: quem chama trata como "não confirmado" (na dúvida o e-mail fica na caixa), nunca como "não respondeu"."""
        base = self._caixa(conta)
        if not isinstance(enderecos, (list, tuple)) or not 1 <= len(enderecos) <= MAX_ENDERECOS_CONSULTA:
            raise ErroGraphNess(f"de 1 a {MAX_ENDERECOS_CONSULTA} endereços por chamada")
        normais = []
        for e in enderecos:
            a = _endereco(e) if isinstance(e, str) and e.strip().lower() == _endereco(e) else ""
            if not a:
                raise ErroGraphNess("endereço inválido")
            normais.append(a)
        saida = {}
        for a in normais:
            achou = False
            literal = a.replace("'", "''")  # _ENDERECO aceita apóstrofo no nome (o'neil@x.com): em OData ele se escapa dobrando
            for campo in ("toRecipients", "ccRecipients"):
                q = urllib.parse.quote(f"{campo}/any(r:r/emailAddress/address eq '{literal}')", safe="")
                resp = self._get(f"{base}/mailFolders/sentitems/messages?$select=id&$top=1&$filter={q}")
                achou = achou or bool(resp.get("value"))
            saida[a] = achou
        return saida

    # ---------------- teams (só metadado: o texto nunca é pedido) ----------------
    def teams_chats(self, conta: str) -> list[dict]:
        """[{chat_id, tipo ("um_a_um"|"grupo"), ultima_em}] dos chats da conta; `ultima_em` vem do `lastMessagePreview` (só a data; o corpo não é lido).
        De passagem aprende o id AAD da própria conta (membro cujo e-mail é a conta): nenhum membro/nome sai daqui."""
        conta = self._conta(conta)
        url = f"{self._caixa(conta)}/chats?$expand=lastMessagePreview,members&$top=50"
        saida = []
        for pagina in self._paginas(url):
            for c in pagina.get("value") or []:
                if not isinstance(c, dict):
                    continue
                self._aprender_id(conta, c)
                if not isinstance(c.get("id"), str) or not _CHAT_ID.match(c["id"]) or c.get("chatType") not in _TIPOS_CHAT:
                    continue
                previa = c.get("lastMessagePreview")
                ultima = _utc(previa.get("createdDateTime")) if isinstance(previa, dict) else None
                saida.append({"chat_id": c["id"], "tipo": _TIPOS_CHAT[c["chatType"]], "ultima_em": ultima.isoformat() if ultima else None})
        return saida

    def _aprender_id(self, conta: str, chat) -> None:
        if conta in self._meu_ids or not isinstance(chat, dict) or not isinstance(chat.get("members"), list):
            return
        for m in chat["members"]:
            if (isinstance(m, dict) and isinstance(m.get("email"), str) and m["email"].lower() == conta.lower()
                    and isinstance(m.get("userId"), str) and m["userId"]):
                self._meu_ids[conta] = m["userId"].lower()
                return

    def _meu_id(self, conta: str) -> str:
        """Id AAD da conta, sem `User.Read.All` (`/users/{conta}` dá 403): vem dos membros dos chats. Sem achar, erro SEM status (encerra a conta)."""
        if conta not in self._meu_ids:
            resp = self._get(f"{self._caixa(conta)}/chats?$top=20&$expand=members")
            for c in resp.get("value") or []:
                self._aprender_id(conta, c)
        if conta not in self._meu_ids:
            raise ErroGraphNess("não foi possível identificar a conta")
        return self._meu_ids[conta]

    def teams_mensagens(self, conta: str, chat_id: str, desde: str | None) -> list[dict]:
        """[{id, quando, de_nome, de_eu, mencoes_eu}] das mensagens de pessoas do chat com `quando > desde`, em ordem crescente. Sistema, apagadas e bots
        (ou sem `from.user`) ficam de fora. Só metadado: o `$select` não inclui `body`, e o texto nunca é lido nem devolvido."""
        conta = self._conta(conta)
        if not isinstance(chat_id, str) or not _CHAT_ID.match(chat_id):
            raise ErroGraphNess("chat inválido")
        limite = None
        if desde is not None:
            limite = _utc(desde)
            if limite is None:
                raise ErroGraphNess("data inválida")
        meu = self._meu_id(conta)
        url = (f"{self._caixa(conta)}/chats/{urllib.parse.quote(chat_id, safe='')}/messages?$select={_CAMPOS_TEAMS}"
               "&$orderby=createdDateTime%20desc&$top=50")
        saida = []
        for n, pagina in enumerate(self._paginas(url), 1):
            antigas = False
            for item in pagina.get("value") or []:
                msg = _mensagem_teams(item, meu)
                if msg is None:
                    continue
                if limite is not None and dt.datetime.fromisoformat(msg["quando"]) <= limite:
                    antigas = True  # a ordem é do mais novo para o mais antigo: daqui para trás já foi visto
                    continue
                saida.append(msg)
            if antigas or n >= MAX_PAGINAS_TEAMS:
                break
        return sorted(saida, key=lambda x: x["quando"])


def _utc(texto) -> dt.datetime | None:
    """ISO do Graph -> datetime UTC (sem fração de segundo para comparar igual); None se não for data."""
    try:
        d = dt.datetime.fromisoformat(texto.replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).astimezone(dt.timezone.utc).replace(microsecond=0)
    except (AttributeError, TypeError, ValueError):
        return None


def _mensagem_teams(m, meu_id: str) -> dict | None:
    """None para o que não é mensagem de pessoa: sistema (`messageType != "message"`), apagada, bot/dispositivo ou malformada. Só metadado."""
    if not isinstance(m, dict) or m.get("messageType") != "message" or m.get("deletedDateTime") or not isinstance(m.get("id"), str):
        return None
    de = m.get("from")
    usuario = de.get("user") if isinstance(de, dict) else None
    quando = _utc(m.get("createdDateTime"))
    if not isinstance(usuario, dict) or not isinstance(usuario.get("id"), str) or quando is None:
        return None
    nome = usuario.get("displayName")
    mencoes = m.get("mentions")
    eu = any(isinstance(x, dict) and isinstance(x.get("mentioned"), dict) and isinstance(x["mentioned"].get("user"), dict)
             and isinstance(x["mentioned"]["user"].get("id"), str) and x["mentioned"]["user"]["id"].lower() == meu_id
             for x in (mencoes if isinstance(mencoes, list) else []))
    return {"id": m["id"], "quando": quando.isoformat(), "de_nome": nome if isinstance(nome, str) else "", "de_eu": usuario["id"].lower() == meu_id,
            "mencoes_eu": eu}


def _mensagem(m: dict) -> dict | None:
    """None se é rascunho ou vem malformada. Só cabeçalhos úteis e o trecho curto (`bodyPreview`); o corpo nunca é lido."""
    if not isinstance(m, dict) or not isinstance(m.get("id"), str) or not _ID_MSG.match(m["id"]) or m.get("isDraft") is True:
        return None
    try:
        recebida = dt.datetime.fromisoformat(m["receivedDateTime"].replace("Z", "+00:00"))
        recebida = (recebida if recebida.tzinfo else recebida.replace(tzinfo=dt.timezone.utc)).astimezone(dt.timezone.utc)
    except (KeyError, AttributeError, TypeError, ValueError):
        return None
    de = m.get("from")
    de = de.get("emailAddress") if isinstance(de, dict) else None
    cab = {}
    for h in m.get("internetMessageHeaders") or []:
        if isinstance(h, dict) and isinstance(h.get("name"), str) and isinstance(h.get("value"), str):
            cab.setdefault(h["name"].lower(), h["value"])
    assunto, previa, conversa = m.get("subject"), m.get("bodyPreview"), m.get("conversationId")
    return {"externo_id": m["id"], "thread_id": conversa if isinstance(conversa, str) and conversa else m["id"],
            "remetente": _endereco(de.get("address") if isinstance(de, dict) else None),
            "assunto": assunto[:TAM_ASSUNTO] if isinstance(assunto, str) else "",
            "recebida_em": recebida.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "trecho": " ".join(previa.split())[:TAM_TRECHO] if isinstance(previa, str) else "", "lista": _lista(cab)}


def _hora(campo, dia_inteiro: bool):
    """`start`/`end` do Graph (UTC, `Prefer: outlook.timezone="UTC"`) -> formato do Google que `tempo.de_google` entende; None se inválido."""
    texto = campo.get("dateTime") if isinstance(campo, dict) else None
    if not isinstance(texto, str) or len(texto) < 19:
        return None
    return {"date": texto[:10]} if dia_inteiro else {"dateTime": texto[:19] + "Z"}


_RESPOSTA = {"notResponded": "needsAction", "none": "needsAction", "accepted": "accepted", "tentativelyAccepted": "tentative", "declined": "declined"}


def _resposta(item: dict) -> str | None:
    """Minha resposta ao convite; None se eu sou o organizador ou o Graph não disse."""
    if item.get("isOrganizer") is True:
        return None
    r = item.get("responseStatus")
    return _RESPOSTA.get(r.get("response")) if isinstance(r, dict) and isinstance(r.get("response"), str) else None


def _organizador_nome(item: dict) -> str | None:
    """Só o nome do organizador; o endereço (e os dos demais participantes) nunca é guardado."""
    o = item.get("organizer")
    e = o.get("emailAddress") if isinstance(o, dict) else None
    nome = e.get("name") if isinstance(e, dict) else None
    return nome if isinstance(nome, str) and nome else None


def _evento(item: dict) -> dict:
    dia = item.get("isAllDay") is True
    participantes = item.get("attendees")
    juntar = (item.get("onlineMeeting") or {}).get("joinUrl") if isinstance(item.get("onlineMeeting"), dict) else None
    texto = lambda v: v if isinstance(v, str) else None  # noqa: E731
    return {"externo_id": item["id"], "inicio": _hora(item.get("start"), dia), "fim": _hora(item.get("end"), dia),
            "titulo": texto(item.get("subject")),
            "link_reuniao": juntar if isinstance(juntar, str) and juntar.startswith("https://") else None,
            "participantes_qtd": len(participantes) if isinstance(participantes, list) else 0,
            "status": "confirmed", "etag": texto(item.get("@odata.etag")), "atualizado_origem": texto(item.get("lastModifiedDateTime")),
            "privado": item.get("sensitivity") in ("private", "confidential"),
            "ical_uid": texto(item.get("iCalUId")) or None, "livre": item.get("showAs") == "free",
            "resposta": _resposta(item), "organizador_nome": _organizador_nome(item), "serie_id": texto(item.get("seriesMasterId")) or None}


def _recusado_por_mim(item: dict) -> bool:
    r = item.get("responseStatus")
    return isinstance(r, dict) and r.get("response") == "declined"


def _emails(lista) -> list[str]:
    """Endereços válidos em minúsculas, sem repetir, no máximo MAX_EMAILS."""
    achados = []
    for e in lista or []:
        v = e.get("address") if isinstance(e, dict) else None
        if isinstance(v, str) and _EMAIL.match(v.strip()):
            achados.append(v.strip().lower())
    return list(dict.fromkeys(achados))[:MAX_EMAILS]


def graph_ness_do_ambiente(env) -> GraphNess | None:
    """None ("não configurada") sem tenant, client id e secret no ambiente do serviço. Com GRAPH_NESS_TEAMS_REFRESH, monta o token delegado do
    Teams para a primeira conta de M365_CONTAS; sem ele o resto funciona e os envios do Teams dão `teams_sem_login`."""
    t, i, s = env.get("M365_TENANT_ID"), env.get("M365_CLIENT_ID"), env.get("M365_CLIENT_SECRET")
    if not (t and i and s):
        return None
    contas = [c.strip() for c in (env.get("M365_CONTAS") or "").split(",") if c.strip()] or list(CONTAS_PADRAO)
    refresh = (env.get("GRAPH_NESS_TEAMS_REFRESH") or "").strip()
    delegado = None
    if refresh:
        from gabi.fontes.graph_ness_envios import TokenDelegado
        delegado = TokenDelegado(t, i, refresh, contas[0])
    return GraphNess(TokenApp(t, i, s), contas, token_teams=delegado)
