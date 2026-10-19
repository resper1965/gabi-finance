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
