"""Confere o que o Hermes prometeu gravar: acha respostas com "anotado", "registrei", "salvei" etc. sem chamada
bem-sucedida a ferramenta de escrita do brain no mesmo turno (ADR-028).
Uso: python -m tools.auditar_promessas [--desde YYYY-MM-DD] [--state-db ~/.hermes/state.db]. Somente leitura (?mode=ro).
Imprime uma linha por caso (data, sessão, 80 primeiros caracteres) e a contagem; sai 0. Sem timer: o assistente roda."""
import argparse
import datetime as dt
import re
import sqlite3
from pathlib import Path

ESCRITAS = ("familia_atualizar_contato", "familia_registrar_pessoa", "familia_registrar_pet", "familia_propor_documento",
            "decisao_responder", "classificar_lancamento", "regras_sugerir", "propor_evento", "propor_teams")
FERRAMENTAS_DE_ESCRITA = {"mcp__gabi_brain__" + n for n in ESCRITAS}
PROMESSA = re.compile(r"\b(anotad|anotei|registr|salv|guard|atualiz)\w*", re.I)
PADRAO_STATE_DB = Path.home() / ".hermes" / "state.db"


def promessas_sem_escrita(state_db: Path, desde: dt.datetime) -> list[dict]:
    con = sqlite3.connect(f"file:{state_db}?mode=ro", uri=True)
    try:
        msgs = con.execute(
            "select m.session_id, m.role, m.content, m.tool_name, m.timestamp from messages m "
            "join sessions s on s.id = m.session_id where s.source in ('telegram','whatsapp') "
            "order by m.session_id, m.timestamp, m.id").fetchall()
    finally:
        con.close()
    casos: list[dict] = []
    sessao, escreveu = None, False  # escreveu: escrita ok desde a última mensagem do usuário
    for sid, role, content, tool, ts in msgs:
        if sid != sessao:
            sessao, escreveu = sid, False
        if role == "user":
            escreveu = False
        elif role == "tool":
            if tool in FERRAMENTAS_DE_ESCRITA and '"erro"' not in (content or ""):
                escreveu = True
        elif role == "assistant" and content and PROMESSA.search(content):
            if not escreveu and ts >= desde.timestamp():
                casos.append({"quando": dt.datetime.fromtimestamp(ts), "sessao": sid,
                              "trecho": content.replace("\r", " ").replace("\n", " ")[:80]})
    return casos


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Respostas do Hermes que prometeram gravar sem escrita no brain.")
    ap.add_argument("--desde", help="YYYY-MM-DD (padrão: 7 dias atrás)")
    ap.add_argument("--state-db", type=Path, default=PADRAO_STATE_DB)
    a = ap.parse_args(argv)
    desde = dt.datetime.strptime(a.desde, "%Y-%m-%d") if a.desde else dt.datetime.now() - dt.timedelta(days=7)
    casos = promessas_sem_escrita(a.state_db, desde)
    for c in casos:
        print(f"{c['quando']:%d/%m %H:%M} {c['sessao']} {c['trecho']}")
    print(f"{len(casos)} casos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
