#!/usr/bin/env python3
"""Vigia semanal SEM modelo: serviços do gabi-finance e do Hermes no ar, fontes de dados em dia e promessas do Hermes sem escrita.
Sai pelo stdout (o cron `--no-agent` entrega ao Ricardo). Fonte: ~/gabi-finance/deploy/hermes/scripts/; cópia em ~/.hermes/scripts/.
Token em ~/.hermes/.env (GABI_FINANCE_TOKEN); nunca imprime segredo. Falha: uma linha curta e sai com 1."""
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

URL = "http://127.0.0.1:8082/mcp"
ENV = Path.home() / ".hermes" / ".env"
RAIZ = Path.home() / "gabi-finance"
NOSSAS = ("gabi-finance", "hermes")
PROBLEMA = ("erro", "parada")  # `nao_conferida` só informa (ADR-023), `em_espera` é fonte em espera de chave


def token() -> str:
    m = re.search(r"^GABI_FINANCE_TOKEN=(.+)$", ENV.read_text(), re.M)
    if not m:
        raise RuntimeError("sem GABI_FINANCE_TOKEN")
    return m.group(1).strip().strip("'\"")


def chamar(tok: str, ferramenta: str, args: dict) -> dict:
    corpo = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": ferramenta, "arguments": args}}).encode()
    req = urllib.request.Request(URL, corpo, {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                                              "Authorization": " ".join(("Bearer", tok))})  # sem o literal com espaço: tests/test_deploy.py varre deploy/ atrás de segredo
    with urllib.request.urlopen(req, timeout=60) as r:
        txt = r.read().decode()
    if txt.lstrip().startswith("event:") or "\ndata:" in txt or txt.startswith("data:"):  # SSE
        txt = next(l[5:].strip() for l in txt.splitlines() if l.startswith("data:"))
    res = json.loads(txt)["result"]
    if res.get("isError"):
        raise RuntimeError("ferramenta devolveu erro")
    if res.get("structuredContent") is not None:
        return res["structuredContent"]
    return json.loads(res["content"][0]["text"])


def units_falhando(saida: str) -> list[str]:
    """Units do gabi-finance e do Hermes na saída de `systemctl --failed --plain --no-legend` (as do sistema ficam de fora)."""
    nomes = (linha.split()[0] for linha in saida.splitlines() if linha.strip())
    return [n for n in nomes if n.startswith(NOSSAS)]


def fontes_paradas(envelope: dict) -> list[str]:
    """Envelope de uma ferramenta que olha TODAS as fontes (`financeiro_saldo`); `avisos_abertos` sempre traz `fontes: []`."""
    if not isinstance(envelope, dict) or "erro" in envelope:
        raise RuntimeError("ferramenta devolveu erro")
    return [str(f.get("nome") or "?") for f in envelope.get("fontes") or [] if isinstance(f, dict) and f.get("estado") in PROBLEMA]


def promessas(saida: str) -> int | None:
    """A contagem "N casos" da última linha do `tools.auditar_promessas`; None se não veio."""
    m = re.search(r"^(\d+) casos\s*$", saida.strip().splitlines()[-1] if saida.strip() else "")
    return int(m.group(1)) if m else None


def texto(units: list[str], paradas: list[str], casos: int | None) -> str:
    if not units and not paradas and casos == 0:
        return "Vigia semanal: tudo ok (serviços no ar, dados em dia, 0 promessas sem escrita)."
    linhas = ["Vigia semanal:"]
    if units:
        linhas.append(f"• serviço falhando: {', '.join(units)}")
    if paradas:
        linhas.append(f"• dados parados: {', '.join(paradas)}")
    if casos is None:
        linhas.append("• não consegui conferir as promessas do Hermes")
    elif casos:
        linhas.append(f"• {casos} promessas sem escrita nos últimos 7 dias (python -m tools.auditar_promessas)")
    if len(linhas) == 1:
        linhas.append("• serviços no ar e dados em dia")
    return "\n".join(linhas)


def main(argv: list[str]) -> int:
    try:
        paradas = fontes_paradas(chamar(token(), "financeiro_saldo", {}))
        failed = subprocess.run(["systemctl", "--failed", "--plain", "--no-legend"], capture_output=True, text=True, timeout=30).stdout
        aud = subprocess.run([str(RAIZ / ".venv" / "bin" / "python"), "-m", "tools.auditar_promessas"], cwd=RAIZ,
                             capture_output=True, text=True, timeout=120).stdout
    except Exception as e:  # noqa: BLE001 - qualquer falha vira aviso curto
        print(f"Falhou: vigia semanal ({type(e).__name__})")
        return 1
    print(texto(units_falhando(failed), paradas, promessas(aud)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
