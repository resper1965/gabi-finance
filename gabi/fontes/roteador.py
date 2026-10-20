"""Roteia a leitura de contatos por conta: contas do Graph (ness) vão ao Graph, as demais ao Google. Sem rede: recebe os `listar` já prontos."""
from typing import Callable

from gabi.fontes.google_oauth import ErroGoogleOAuth


def roteador_contatos(google: Callable[[str], list[dict]] | None, graph: Callable[[str], list[dict]] | None,
                      contas_graph: list[str]) -> Callable[[str], list[dict]]:
    """Fonte ausente (não configurada no serviço) vira "conta não autorizada", o aviso esperado que não derruba as outras contas."""
    do_graph = {c.lower() for c in contas_graph}

    def listar(conta: str) -> list[dict]:
        fonte = graph if conta.lower() in do_graph else google
        if fonte is None:
            raise ErroGoogleOAuth(f"conta não autorizada: {conta}")
        return fonte(conta)
    return listar


def contatos_pela_ponte(caminho) -> Callable[[str], list[dict]] | None:
    """`listar(conta)` sobre a ponte do serviço de fontes (Google e Graph da ness); None se nenhuma das duas está configurada lá."""
    from gabi.fontes.ponte import PonteContatos, PonteGraph
    google, graph = PonteContatos(caminho), PonteGraph(caminho)
    g_ok, m_ok = google.configurada(), graph.configurada()
    if not (g_ok or m_ok):
        return None
    return roteador_contatos(google.listar if g_ok else None, graph.contatos if m_ok else None, graph.contas() if m_ok else [])


class RoteadorEmail:
    """Correio por conta: contas cadastradas com provedor `graph` vão ao Graph da ness, as demais ao Gmail. Mesmos métodos da `PonteEmail`.
    Lado não configurado no serviço de fontes vira "conta não autorizada" (erro tipado que não derruba as outras contas)."""

    def __init__(self, google, graph, contas_graph):
        self._google, self._graph, self._do_graph = google, graph, {c.lower() for c in contas_graph}

    def _de(self, conta: str):
        fonte = self._graph if conta.lower() in self._do_graph else self._google
        if fonte is None:
            raise ErroGoogleOAuth(f"conta não autorizada: {conta}")
        return fonte

    def listar_novos(self, conta, history_id, janela_dias):
        return self._de(conta).listar_novos(conta, history_id, janela_dias)

    def lixeira(self, conta, ids):
        return self._de(conta).lixeira(conta, ids)

    def restaurar(self, conta, ids):
        return self._de(conta).restaurar(conta, ids)

    def enviados_recentes(self, conta, dias):
        return self._de(conta).enviados_recentes(conta, dias)

    def respondeu_a(self, conta, enderecos):
        return self._de(conta).respondeu_a(conta, enderecos)


def email_pela_ponte(caminho, contas_graph) -> RoteadorEmail | None:
    """Roteador do correio sobre a ponte (Gmail e Graph da ness); None se nenhum dos dois está configurado no serviço de fontes."""
    from gabi.fontes.graph_ness import ErroGraphNess
    from gabi.fontes.ponte import PonteEmail
    google, graph = PonteEmail(caminho), PonteEmail(caminho, "graph_ness", ErroGraphNess)
    g_ok, m_ok = google.configurada(), graph.configurada()
    if not (g_ok or m_ok):
        return None
    return RoteadorEmail(google if g_ok else None, graph if m_ok else None, contas_graph)
