"""Ponte Unix entre a API/MCP (sem rede) e o serviço `gabi-brain-fontes` (com rede, dono dos tokens do Paperless e do Nibo).
Uma requisição por conexão: JSON de uma linha {"fonte", "metodo", "args", "kwargs"} -> {"ok": valor} | {"erro": {"tipo", "msg"}}.
`bytes` viaja como {"__b64__": ...}. Só métodos da lista branca; `preparar_usuario` (token admin) nunca atravessa a ponte.
R5: nenhum token ou cabeçalho trafega aqui; o servidor devolve só o tipo e a mensagem do erro. Consome: fontes.paperless, fontes.nibo_escrita."""
import base64
import datetime as dt
import json
import os
import socket
import socketserver
from pathlib import Path

from gabi.fontes.google_agenda import ResultadoEventos
from gabi.fontes.google_contatos import ErroGoogleContatos
from gabi.fontes.google_email import ResultadoEmail
from gabi.fontes.google_oauth import ErroGoogleOAuth
from gabi.fontes.graph_ness import ErroGraphNess
from gabi.fontes.nibo import ErroNibo
from gabi.fontes.openrouter import ErroOpenRouter
from gabi.fontes.paperless import ErroPaperless

MAX_BYTES = 64 * 1024 * 1024
ESPERA_PEDIDO = 30  # segundos para o pedido chegar inteiro; cliente mudo é desconectado
PERMITIDOS = {
    "paperless": frozenset({"docs", "baixar", "texto", "documento"}),  # ADR-023: só a busca, o download e o OCR do MCP; nada escreve no Paperless
    "openrouter": frozenset({"completar", "completar_pdf"}),
    "google_contatos": frozenset({"listar"}),
    "google_agenda": frozenset({"listar_calendarios", "listar_eventos", "evento_criar"}),  # ADR-024: criar só com proposta aprovada
    "graph_ness": frozenset({"contas", "contatos", "listar_calendarios", "listar_eventos",
                             "listar_novos", "lixeira", "restaurar", "enviados_recentes", "respondeu_a", "mensagem", "teams_chats", "teams_mensagens",
                             "contato_criar", "contato_corrigir", "contato_renomear", "contato_apagar_telefone", "contato_apagar", "contato_adicionar_email",
                             # ADR-024: criar evento e escrever no Teams só com proposta aprovada (graph_ness_envios)
                             "evento_criar", "teams_equipes", "teams_canais", "teams_chat_enviar", "teams_canal_enviar"}),
    "google_email": frozenset({"listar_novos", "lixeira", "restaurar", "enviados_recentes", "respondeu_a", "mensagem"}),  # Onda 2: `mensagem` só lê o corpo
    "nibo": frozenset({"nfse", "agendamentos_a_receber", "obter_arquivo"}),  # ADR-023: só o que notas_importar lê; o lote (escrita) saiu
}
ERROS = {"paperless": ErroPaperless, "nibo": ErroNibo, "openrouter": ErroOpenRouter, "google_contatos": ErroGoogleContatos,
        "google_agenda": ErroGoogleOAuth, "google_email": ErroGoogleOAuth, "graph_ness": ErroGraphNess}


def _codificar(v):
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()  # o outro lado (métodos do Nibo) aceita o texto ISO
    if isinstance(v, (bytes, bytearray)):
        return {"__b64__": base64.b64encode(bytes(v)).decode()}
    if isinstance(v, dict):
        return {k: _codificar(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_codificar(x) for x in v]
    return v


def _decodificar(v):
    if isinstance(v, dict):
        if set(v) == {"__b64__"}:
            return base64.b64decode(v["__b64__"])
        return {k: _decodificar(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_decodificar(x) for x in v]
    return v


def _ler_tudo(c) -> bytes:
    partes, total = [], 0
    while True:
        p = c.recv(1 << 20)
        if not p:
            return b"".join(partes)
        total += len(p)
        if total > MAX_BYTES:
            raise ValueError("requisição grande demais")
        partes.append(p)


def _atender(fontes: dict, bruto: bytes) -> dict:
    """fontes: {"paperless": objeto|None, "nibo": objeto|None}. Nunca levanta: erro vira {"erro": ...}."""
    try:
        req = json.loads(bruto)
        fonte, metodo = req["fonte"], req["metodo"]
        if metodo == "estado":
            return {"ok": {n: o is not None for n, o in fontes.items()}}
        if fonte not in PERMITIDOS or metodo not in PERMITIDOS[fonte]:
            return {"erro": {"tipo": "metodo_proibido", "msg": f"{fonte}.{metodo} não é permitido"}}
        objeto = fontes.get(fonte)
        if objeto is None:
            return {"erro": {"tipo": "nao_configurada", "msg": f"{fonte} não está configurado no serviço de fontes"}}
        r = getattr(objeto, metodo)(*_decodificar(req.get("args", [])), **_decodificar(req.get("kwargs", {})))
        if hasattr(r, "__next__"):
            r = list(r)
        return {"ok": _codificar(r)}
    except tuple(ERROS.values()) as e:
        tipo = next(c.__name__ for c in ERROS.values() if isinstance(e, c))  # subclasses (TagInvalida) cruzam como a base
        return {"erro": {"tipo": tipo, "msg": str(e)}}
    except Exception as e:  # nunca vaza traço (pode conter URL/cabeçalho)
        return {"erro": {"tipo": "interno", "msg": type(e).__name__}}


class Servidor(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def __init__(self, caminho, fontes: dict):
        self.fontes = fontes
        Path(caminho).unlink(missing_ok=True)
        super().__init__(str(caminho), _Manipulador)
        os.chmod(caminho, 0o660)


class _Manipulador(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(ESPERA_PEDIDO)
        try:
            bruto = _ler_tudo(self.request)
        except TimeoutError:  # cliente mudo: fecha sem responder
            return
        except ValueError as e:
            resp = {"erro": {"tipo": "interno", "msg": str(e)}}
        else:
            self.request.settimeout(None)
            resp = _atender(self.server.fontes, bruto)
        self.request.sendall(json.dumps(resp).encode())


class Ponte:
    """Cliente: objeto com os mesmos métodos do Paperless/NiboEscrita, mas executados no serviço de fontes."""

    def __init__(self, caminho, fonte: str):
        self._caminho, self._fonte = str(caminho), fonte

    def _chamar(self, metodo, args=(), kwargs=None):
        erro = ERROS[self._fonte]
        corpo = json.dumps({"fonte": self._fonte, "metodo": metodo, "args": _codificar(list(args)), "kwargs": _codificar(kwargs or {})}).encode()
        try:
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(130)
                s.connect(self._caminho)
                s.sendall(corpo)
                s.shutdown(socket.SHUT_WR)
                resp = json.loads(_ler_tudo(s))
        except (OSError, ValueError):
            raise erro("serviço de fontes indisponível") from None
        if "erro" in resp:
            t, msg = resp["erro"]["tipo"], resp["erro"]["msg"]
            raise erro(msg if t in (erro.__name__, "nao_configurada") else f"{t}: {msg}")
        return _decodificar(resp["ok"])

    def configurada(self) -> bool:
        try:
            return bool(self._chamar("estado").get(self._fonte))
        except tuple(ERROS.values()):
            return False

    def __getattr__(self, nome):
        if nome.startswith("_") or nome not in PERMITIDOS[self._fonte]:
            raise AttributeError(nome)
        return lambda *a, **k: self._chamar(nome, a, k)


class PonteModelo:
    """ModeloCliente (gabi.dinheiro.modelo) que chama o OpenRouter no serviço de fontes; sem chave a fonte não está configurada e a ponte levanta ErroOpenRouter."""

    def __init__(self, caminho):
        self._ponte = Ponte(caminho, "openrouter")

    def completar(self, prompt: str, *, forte: bool) -> tuple[str, float]:
        r = self._ponte._chamar("completar", (prompt,), {"forte": forte})
        if (not isinstance(r, (list, tuple)) or len(r) != 2 or not isinstance(r[0], str)
                or isinstance(r[1], bool) or not isinstance(r[1], (int, float))):
            raise ErroOpenRouter("resposta inválida do serviço de fontes")
        return r[0], float(r[1])


    def completar_pdf(self, pdf: bytes, prompt: str, *, forte: bool = False, max_bytes: int | None = None, max_paginas: int | None = None) -> tuple[str, float]:
        """PDF digitalizado lido por visão no serviço de fontes (R5: a chave e a rede ficam lá). Os tetos só podem baixar os do serviço."""
        kw = {"forte": forte, **({"max_bytes": max_bytes} if max_bytes else {}), **({"max_paginas": max_paginas} if max_paginas else {})}
        r = self._ponte._chamar("completar_pdf", (bytes(pdf), prompt), kw)
        if (not isinstance(r, (list, tuple)) or len(r) != 2 or not isinstance(r[0], str)
                or isinstance(r[1], bool) or not isinstance(r[1], (int, float))):
            raise ErroOpenRouter("resposta inválida do serviço de fontes")
        return r[0], float(r[1])


class PonteContatos:
    """Contatos do Google lidos no serviço de fontes (único com rede e segredos). `listar(conta) -> [{nome, telefone[, emails]}]`; sem credenciais a fonte não está configurada."""

    def __init__(self, caminho):
        self._ponte = Ponte(caminho, "google_contatos")

    def configurada(self) -> bool:
        return self._ponte.configurada()

    def listar(self, conta: str) -> list[dict]:
        r = self._ponte._chamar("listar", (conta,))
        if not isinstance(r, list) or not all(isinstance(x, dict) for x in r):
            raise ErroGoogleContatos("resposta inválida do serviço de fontes")
        return r


class PonteAgenda:
    """Agenda do Google lida no serviço de fontes (único com rede e segredos), leitura + criar evento aprovado."""

    def __init__(self, caminho):
        self._ponte = Ponte(caminho, "google_agenda")

    def configurada(self) -> bool:
        return self._ponte.configurada()

    def listar_calendarios(self, conta: str) -> list[dict]:
        r = self._ponte._chamar("listar_calendarios", (conta,))
        if not isinstance(r, list) or not all(isinstance(x, dict) for x in r):
            raise ErroGoogleOAuth("resposta inválida do serviço de fontes")
        return r

    def evento_criar(self, conta: str, chave: str, evento: dict) -> dict:
        r = self._ponte._chamar("evento_criar", (conta, chave, evento))
        if not isinstance(r, dict) or not isinstance(r.get("externo_id"), str) or not isinstance(r.get("ja_existia"), bool):
            raise ErroGoogleOAuth("resposta inválida do serviço de fontes")
        return r

    def listar_eventos(self, conta: str, calendario_id: str, sync_token: str | None, janela: dict) -> ResultadoEventos:
        r = self._ponte._chamar("listar_eventos", (conta, calendario_id, sync_token, janela))
        if (not isinstance(r, dict) or not isinstance(r.get("eventos"), list) or not isinstance(r.get("cancelados"), list)
                or not isinstance(r.get("recarga_completa"), bool) or not (r.get("novo_sync_token") is None or isinstance(r.get("novo_sync_token"), str))):
            raise ErroGoogleOAuth("resposta inválida do serviço de fontes")
        return ResultadoEventos(r["eventos"], r["cancelados"], r.get("novo_sync_token"), r["recarga_completa"])


class PonteGraph:
    """Graph da ness no serviço de fontes (único com rede e segredos): leitura, escrita de contatos e os envios aprovados (evento e Teams). Lista fixa de métodos."""

    def __init__(self, caminho):
        self._ponte = Ponte(caminho, "graph_ness")

    def configurada(self) -> bool:
        return self._ponte.configurada()

    def contas(self) -> list[str]:
        r = self._ponte._chamar("contas")
        if not isinstance(r, list) or not all(isinstance(x, str) for x in r):
            raise ErroGraphNess("resposta inválida do serviço de fontes")
        return r

    def contato_criar(self, conta: str, nome: str, telefone: str) -> dict:
        r = self._ponte._chamar("contato_criar", (conta, nome, telefone))
        if not isinstance(r, dict) or not isinstance(r.get("id"), str):
            raise ErroGraphNess("resposta inválida do serviço de fontes")
        return r

    def contato_corrigir(self, conta: str, graph_id: str, antes: dict, depois: dict) -> dict:
        r = self._ponte._chamar("contato_corrigir", (conta, graph_id, antes, depois))
        if not isinstance(r, dict) or r.get("resultado") not in ("ok", "alterado"):
            raise ErroGraphNess("resposta inválida do serviço de fontes")
        return r

    def _resultado(self, metodo: str, *args) -> dict:
        r = self._ponte._chamar(metodo, args)
        if not isinstance(r, dict) or r.get("resultado") not in ("ok", "alterado"):
            raise ErroGraphNess("resposta inválida do serviço de fontes")
        return r

    def contato_renomear(self, conta: str, graph_id: str, nome_antes: str, nome_depois: str) -> dict:
        return self._resultado("contato_renomear", conta, graph_id, nome_antes, nome_depois)

    def contato_apagar_telefone(self, conta: str, graph_id: str, campo: str, telefone_antes: str) -> dict:
        return self._resultado("contato_apagar_telefone", conta, graph_id, campo, telefone_antes)

    def contato_apagar(self, conta: str, graph_id: str, nome_antes: str, telefone_antes: str) -> dict:
        return self._resultado("contato_apagar", conta, graph_id, nome_antes, telefone_antes)

    def contato_adicionar_email(self, conta: str, graph_id: str, nome_antes: str, telefone_antes: str, emails: list) -> dict:
        return self._resultado("contato_adicionar_email", conta, graph_id, nome_antes, telefone_antes, emails)

    def contatos(self, conta: str) -> list[dict]:
        r = self._ponte._chamar("contatos", (conta,))
        if not isinstance(r, list) or not all(isinstance(x, dict) for x in r):
            raise ErroGraphNess("resposta inválida do serviço de fontes")
        return r

    def listar_calendarios(self, conta: str) -> list[dict]:
        r = self._ponte._chamar("listar_calendarios", (conta,))
        if not isinstance(r, list) or not all(isinstance(x, dict) for x in r):
            raise ErroGraphNess("resposta inválida do serviço de fontes")
        return r

    def listar_eventos(self, conta: str, calendario_id: str, sync_token: str | None, janela: dict) -> ResultadoEventos:
        r = self._ponte._chamar("listar_eventos", (conta, calendario_id, sync_token, janela))
        if (not isinstance(r, dict) or not isinstance(r.get("eventos"), list) or not isinstance(r.get("cancelados"), list)
                or not isinstance(r.get("recarga_completa"), bool) or not (r.get("novo_sync_token") is None or isinstance(r.get("novo_sync_token"), str))):
            raise ErroGraphNess("resposta inválida do serviço de fontes")
        return ResultadoEventos(r["eventos"], r["cancelados"], r.get("novo_sync_token"), r["recarga_completa"])

    def teams_chats(self, conta: str) -> list[dict]:
        r = self._ponte._chamar("teams_chats", (conta,))
        if (not isinstance(r, list) or not all(
                isinstance(x, dict) and set(x) == {"chat_id", "tipo", "ultima_em"} and isinstance(x["chat_id"], str)
                and x["tipo"] in ("um_a_um", "grupo") and (x["ultima_em"] is None or isinstance(x["ultima_em"], str)) for x in r)):
            raise ErroGraphNess("resposta inválida do serviço de fontes")
        return r

    def _externo(self, metodo: str, *args) -> dict:
        r = self._ponte._chamar(metodo, args)
        if not isinstance(r, dict) or not isinstance(r.get("externo_id"), str) or not r["externo_id"]:
            raise ErroGraphNess("resposta inválida do serviço de fontes")
        return r

    def _id_nome(self, metodo: str, *args) -> list[dict]:
        r = self._ponte._chamar(metodo, args)
        if not isinstance(r, list) or not all(isinstance(x, dict) and set(x) == {"id", "nome"} and isinstance(x["id"], str)
                                               and isinstance(x["nome"], str) for x in r):
            raise ErroGraphNess("resposta inválida do serviço de fontes")
        return r

    def evento_criar(self, conta: str, chave: str, evento: dict) -> dict:
        return self._externo("evento_criar", conta, chave, evento)

    def teams_equipes(self, conta: str) -> list[dict]:
        return self._id_nome("teams_equipes", conta)

    def teams_canais(self, conta: str, equipe_id: str) -> list[dict]:
        return self._id_nome("teams_canais", conta, equipe_id)

    def teams_chat_enviar(self, conta: str, chat_id: str, texto: str) -> dict:
        return self._externo("teams_chat_enviar", conta, chat_id, texto)

    def teams_canal_enviar(self, conta: str, equipe_id: str, canal_id: str, texto: str) -> dict:
        return self._externo("teams_canal_enviar", conta, equipe_id, canal_id, texto)

    def teams_mensagens(self, conta: str, chat_id: str, desde: str) -> list[dict]:
        """Só metadados (sem texto da mensagem) atravessam a ponte."""
        r = self._ponte._chamar("teams_mensagens", (conta, chat_id, desde))
        if (not isinstance(r, list) or not all(
                isinstance(x, dict) and set(x) == {"id", "quando", "de_nome", "de_eu", "mencoes_eu"} and isinstance(x["id"], str)
                and isinstance(x["quando"], str) and isinstance(x["de_nome"], str) and isinstance(x["de_eu"], bool)
                and isinstance(x["mencoes_eu"], bool) for x in r)):
            raise ErroGraphNess("resposta inválida do serviço de fontes")
        return r


def _resultado_por_id(r, erro: type[Exception] = ErroGoogleOAuth) -> dict:
    if not isinstance(r, dict) or not all(isinstance(k, str) and v in ("ok", "erro") for k, v in r.items()):
        raise erro("resposta inválida do serviço de fontes")
    return r


class PonteEmail:
    """Correio (Gmail ou Graph da ness) lido e movido para a lixeira no serviço de fontes (único com rede e segredos). Lista fixa de métodos; sem
    enviar nem apagar. `fonte`/`erro` escolhem o lado: `google_email` (padrão) ou `graph_ness` com `ErroGraphNess`."""

    def __init__(self, caminho, fonte: str = "google_email", erro: type[Exception] = ErroGoogleOAuth):
        self._ponte, self._erro = Ponte(caminho, fonte), erro

    def configurada(self) -> bool:
        return self._ponte.configurada()

    def listar_novos(self, conta: str, history_id: str | None, janela_dias: int) -> ResultadoEmail:
        r = self._ponte._chamar("listar_novos", (conta, history_id, janela_dias))
        if (not isinstance(r, dict) or not isinstance(r.get("mensagens"), list) or not all(isinstance(m, dict) for m in r["mensagens"])
                or not isinstance(r.get("recarga_completa"), bool) or not (r.get("novo_history_id") is None or isinstance(r.get("novo_history_id"), str))):
            raise self._erro("resposta inválida do serviço de fontes")
        return ResultadoEmail(r["mensagens"], r.get("novo_history_id"), r["recarga_completa"])

    def lixeira(self, conta: str, ids: list[str]) -> dict:
        return _resultado_por_id(self._ponte._chamar("lixeira", (conta, list(ids))), self._erro)

    def restaurar(self, conta: str, ids: list[str]) -> dict:
        return _resultado_por_id(self._ponte._chamar("restaurar", (conta, list(ids))), self._erro)

    def enviados_recentes(self, conta: str, dias: int) -> list[str]:
        r = self._ponte._chamar("enviados_recentes", (conta, dias))
        if not isinstance(r, list) or not all(isinstance(x, str) for x in r):
            raise self._erro("resposta inválida do serviço de fontes")
        return r

    def respondeu_a(self, conta: str, enderecos: list[str]) -> dict:
        r = self._ponte._chamar("respondeu_a", (conta, list(enderecos)))
        if not isinstance(r, dict) or not all(isinstance(k, str) and isinstance(v, bool) for k, v in r.items()):
            raise self._erro("resposta inválida do serviço de fontes")
        return r

    def mensagem(self, conta: str, externo_id: str) -> dict:
        """Corpo em texto (Onda 2, só leitura): {"corpo": str, "cortado": bool}."""
        r = self._ponte._chamar("mensagem", (conta, externo_id))
        if not isinstance(r, dict) or not isinstance(r.get("corpo"), str) or not isinstance(r.get("cortado"), bool):
            raise self._erro("resposta inválida do serviço de fontes")
        return {"corpo": r["corpo"], "cortado": r["cortado"]}

