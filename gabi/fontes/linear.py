"""Cliente Linear SOMENTE LEITURA (T4.3): entregas abertas (issues ainda não concluídas nem canceladas) para Tarefas › Entregas.
R2/R5: nenhum método de escrita e nenhuma mutation; o token vem de um callable (chave pessoal da Linear, no arquivo de ambiente)."""
from typing import Callable

from gabi.fontes._http import http_real

URL = "https://api.linear.app/graphql"
CONSULTA = """query Entregas($depois: String) {
  issues(first: 100, after: $depois, filter: {state: {type: {nin: ["completed", "canceled"]}}}) {
    nodes { id identifier title dueDate updatedAt state { name type } project { name } assignee { name } }
    pageInfo { hasNextPage endCursor }
  }
}"""


class ErroLinear(Exception):
    pass


class Linear:
    def __init__(self, token: Callable[[], str], *, http=None):
        self._token, self._http = token, http or http_real

    def _consultar(self, variaveis: dict) -> dict:
        status, resp = self._http("POST", URL, {"query": CONSULTA, "variables": variaveis}, {"Authorization": self._token()})
        if status >= 400:
            raise ErroLinear(f"POST /graphql -> {status}")
        if isinstance(resp, dict) and resp.get("errors"):
            raise ErroLinear(f"graphql: {resp['errors'][0].get('message', '?')}")
        return resp["data"]["issues"]

    def entregas_abertas(self) -> list[dict]:
        saida, depois = [], None
        while True:
            pag = self._consultar({"depois": depois})
            saida += [{"externo_id": n["id"], "identificador": n["identifier"], "titulo": n["title"], "projeto": (n.get("project") or {}).get("name"),
                       "responsavel": (n.get("assignee") or {}).get("name"), "prazo": n.get("dueDate"), "estado": n["state"]["name"],
                       "atualizado_em": n.get("updatedAt")} for n in pag["nodes"]]
            if not pag["pageInfo"]["hasNextPage"]:
                return saida
            depois = pag["pageInfo"]["endCursor"]
