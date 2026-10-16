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
    "assinaturas": "/api/v1/assinaturas", "sugestoes": "/api/v1/sugestoes", "regras": "/api/v1/regras", "custo": "/api/v1/custo", "qualidade": "/api/v1/gabi/qualidade", "contagens": "/api/v1/contagens", "rodadas": "/api/v1/rodadas", "cobrar-reembolsos": "/api/v1/cobrar/reembolsos", "cobrar-comprovantes": "/api/v1/cobrar/comprovantes", "cobrar-pedidos": "/api/v1/cobrar/pedidos", "cobrar-cobrancas": "/api/v1/cobrar/cobrancas", "cadastros-nibo": "/api/v1/cadastros/nibo", "cadastros-liberacoes": "/api/v1/cadastros/liberacoes",
    "hoje": "/api/v1/hoje", "frentes": "/api/v1/frentes", "frente-1": "/api/v1/frentes/1", "agenda": "/api/v1/agenda", "mensagens": "/api/v1/mensagens", "contatos": "/api/v1/contatos",
    "setup": "/api/v1/setup", "tarefas": "/api/v1/tarefas", "entregas": "/api/v1/entregas", "caixas-email": "/api/v1/caixas-email", "avisos": "/api/v1/avisos", "caixa-projecao": "/api/v1/caixa/projecao?dias=30", "cobrar-previsao": "/api/v1/cobrar/previsao", "cobrar-notas": "/api/v1/cobrar/notas", "cobrar-recebimentos": "/api/v1/cobrar/recebimentos",
    "cadastros-contas": "/api/v1/cadastros/contas", "cadastros-pessoas": "/api/v1/cadastros/pessoas",
    "cadastros-categorias": "/api/v1/cadastros/categorias", "cadastros-empresas": "/api/v1/cadastros/empresas",
    "familia-pessoas": "/api/v1/familia/pessoas", "familia-exames": "/api/v1/familia/exames/p-hel",
    "familia-serie": "/api/v1/familia/exames/p-hel/serie?marcador=Colesterol%20total", "familia-resumo": "/api/v1/familia/exames/p-hel/resumo", "familia-laudos": "/api/v1/familia/laudos",
    "familia-mensagens": "/api/v1/familia/mensagens", "reembolso-dossies": "/api/v1/reembolso-saude/dossies", "reembolso-semana": "/api/v1/reembolso-saude/semana",
}


def _cofre_demo(caminho: Path) -> tuple[Path, bytes]:
    """Saúde sintética (nenhum dado real): 2 exames da Helena e 1 laudo esperando confirmação."""
    import datetime as dt
    from gabi.familia.exames import extrair_marcadores, propor_exames
    from gabi.familia.extrair import Laudo
    from gabi.familia.saude import abrir_saude, registrar_exame
    from gabi.familia.exames import guardar_mensagem
    from gabi.reembolso_saude import cofre as reembolso
    chave = bytes(range(32))
    with abrir_saude(caminho, chave) as s:
        guardar_mensagem(s, "p-hel", "2026-10-14T13:00:00+00:00", "Helena: febre baixa desde a tarde (mensagem sintética)")
        for i, tipo in ((21, "nf"), (22, "comprovante")):
            reembolso.gravar_doc(s, {"id": i, "estado": "a_pedir", "documento": tipo, "caso": "consulta", "data": dt.date(2026, 10, 3), "adicionado": dt.date(2026, 10, 4),
                                     "campos": {"paciente": "Helena (sintética)", "prestador": "Dra. Prestadora (sintética)", "valor": "300.00"}})
        registrar_exame(s, "p-hel", "Colesterol total", "190", "mg/dL", dt.date(2026, 1, 10), ("0", "200"), 11, "boss@x.com")
        registrar_exame(s, "p-hel", "Colesterol total", "215", "mg/dL", dt.date(2026, 7, 10), ("0", "200"), 12, "boss@x.com")
        registrar_exame(s, "p-hel", "Glicose em jejum", "92", "mg/dL", dt.date(2026, 7, 10), ("70", "99"), 12, "boss@x.com")
        texto = "Data da coleta: 05/10/2026\nHemoglobina 13,5 g/dL\nGlicose: 88 mg/dL (Ref.: 70 - 99)\n"
        propor_exames(s, 55, Laudo(None, None, "2026-10-05", extrair_marcadores(texto), "regras"), "p-lia")
    return caminho, chave


def gerar() -> dict[str, dict]:
    pasta = Path(tempfile.mkdtemp(prefix="gabi-amostras-"))
    semear(pasta / "a.db")
    app = criar_app(pasta / "a.db", permite_tcp_local=True, relogio=lambda: AGORA)
    app.state.saude = _cofre_demo(pasta / "saude.enc")
    cli = TestClient(app, client=("127.0.0.1", 50000))
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
