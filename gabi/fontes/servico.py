"""Serviço gabi-brain-fontes: único processo com rede e tokens do Paperless e do Nibo (arquivo de ambiente, R5).
A API e o MCP (sem rede) falam com ele pelo socket Unix da ponte. Uso: python -m gabi.fontes.servico --socket CAMINHO."""
import argparse
import os

from gabi.fontes.ambiente import fontes_do_ambiente
from gabi.fontes.google_contatos import google_contatos_do_ambiente
from gabi.fontes.openrouter import MODELO_FORTE_PADRAO, Limites, MODELO_RAPIDO_PADRAO, OpenRouter
from gabi.fontes.ponte import Servidor


def openrouter_do_ambiente(env=None) -> OpenRouter | None:
    """None (fonte "não configurada", a ponte responde com ErroOpenRouter) sem OPENROUTER_API_KEY."""
    env = os.environ if env is None else env
    if not env.get("OPENROUTER_API_KEY"):
        return None
    return OpenRouter(env.get("OPENROUTER_API_KEY", ""), env.get("OPENROUTER_MODEL_FAST") or MODELO_RAPIDO_PADRAO,
                      env.get("OPENROUTER_MODEL_STRONG") or MODELO_FORTE_PADRAO, limites=Limites.do_ambiente(env))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", required=True)
    args = ap.parse_args(argv)
    os.environ.pop("GABI_FONTES_SOCKET", None)  # aqui as fontes são as reais
    fontes = {n: f() for n, f in fontes_do_ambiente().items()}
    fontes["openrouter"] = openrouter_do_ambiente()
    fontes["google_contatos"] = google_contatos_do_ambiente(os.environ)
    print("fontes configuradas:", {n: o is not None for n, o in fontes.items()}, "chave do modelo:", bool(os.environ.get("OPENROUTER_API_KEY")), flush=True)  # nunca os valores
    with Servidor(args.socket, fontes) as srv:
        srv.serve_forever()


if __name__ == "__main__":
    main()
