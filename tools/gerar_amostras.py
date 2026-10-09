"""Gera painel/tests/amostras/*.json: respostas REAIS da API sobre o banco sintético (tools/demo.py).
As telas são testadas contra estes arquivos; tests/test_amostras_painel.py falha se a API mudar e os arquivos não.
Uso: .venv/bin/python -m tools.gerar_amostras"""
import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from gabi.api import criar_app
from tools.demo import AGORA, semear

DESTINO = Path(__file__).resolve().parent.parent / "painel" / "tests" / "amostras"
ROTAS = {
    "caixa-resumo": "/api/v1/caixa/resumo?periodo=mes", "caixa-semanas": "/api/v1/caixa/semanas", "contas-pagar": "/api/v1/contas-pagar",
    "lancamentos": "/api/v1/lancamentos?limite=100", "lancamentos-pendentes": "/api/v1/lancamentos?limite=100&pendente=para_quem",
    "destino": "/api/v1/destino?periodo=mes", "destino-fornecedor": "/api/v1/destino/agrupado?periodo=mes&por=fornecedor",
    "destino-pessoa": "/api/v1/destino/agrupado?periodo=mes&por=pessoa", "cartoes": "/api/v1/cartoes", "parcelas": "/api/v1/parcelas",
    "assinaturas": "/api/v1/assinaturas", "sugestoes": "/api/v1/sugestoes", "regras": "/api/v1/regras", "custo": "/api/v1/custo", "contagens": "/api/v1/contagens",
    "cadastros-contas": "/api/v1/cadastros/contas", "cadastros-pessoas": "/api/v1/cadastros/pessoas",
    "cadastros-categorias": "/api/v1/cadastros/categorias", "cadastros-empresas": "/api/v1/cadastros/empresas",
}


def gerar() -> dict[str, dict]:
    pasta = Path(tempfile.mkdtemp(prefix="gabi-amostras-"))
    semear(pasta / "a.db")
    cli = TestClient(criar_app(pasta / "a.db", permite_tcp_local=True, relogio=lambda: AGORA), client=("127.0.0.1", 50000))
    saida = {}
    for nome, url in ROTAS.items():
        r = cli.get(url, headers={"Tailscale-User-Login": "boss@x.com"})
        assert r.status_code == 200, (url, r.text)
        saida[nome] = r.json()
    return saida


if __name__ == "__main__":
    DESTINO.mkdir(parents=True, exist_ok=True)
    for f in DESTINO.glob("*.json"):
        f.unlink()
    for nome, corpo in gerar().items():
        (DESTINO / f"{nome}.json").write_text(json.dumps(corpo, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(ROTAS)} amostras em {DESTINO}")
