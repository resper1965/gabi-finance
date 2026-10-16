"""Medição do aceite dos exames: só leitura do cofre e do gabi.db; imprime SÓ contagens (nunca nome, marcador ou valor; ADR-014).
A meta de acerto não está no código: o Ricardo decide no aceite, com a lista real de PDFs.
Uso: python -m tools.medir_exames   (precisa de GABI_SAUDE_CHAVE_ARQUIVO e GABI_BANCO, como a api)"""
import os
import sys
from pathlib import Path

from gabi.db import conectar
from gabi.familia.ambiente import saude_do_ambiente
from gabi.familia.saude import abrir_saude


def medir(con, s) -> dict[str, int]:
    docs = {r["paperless_id"]: r for r in s.con.execute(
        "select paperless_id, (select pessoa_sugerida from proposta_exame p where p.paperless_id=d.paperless_id order by versao, id limit 1) as sugerida, "
        "(select origem from proposta_exame p where p.paperless_id=d.paperless_id order by versao desc, id desc limit 1) as origem, "
        "(select pessoa_id from exame e where e.paperless_id=d.paperless_id order by versao desc, id desc limit 1) as dono "
        "from (select distinct paperless_id from proposta_exame) d")}
    confirmados = [d for d in docs.values() if d["dono"]]
    r = {"documentos": con.execute("select count(*) from exame_doc").fetchone()[0], "extraidos": len(docs), "confirmados": len(confirmados),
         "sem_correcao": sum(1 for d in confirmados if d["sugerida"] == d["dono"]),
         "dono_trocado": sum(1 for d in confirmados if d["sugerida"] and d["sugerida"] != d["dono"]),
         "sem_sugestao": sum(1 for d in confirmados if not d["sugerida"]),
         "falhos": con.execute("select count(*) from exame_doc where estado='falhou'").fetchone()[0]}
    for origem in ("regras", "modelo"):
        r[f"origem_{origem}"] = sum(1 for d in docs.values() if d["origem"] == origem)
    return r


def main() -> int:
    banco = Path(os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db"))
    cfg = saude_do_ambiente(banco.parent)
    if cfg is None:
        print("ERRO: a chave do cofre de saúde não está configurada", file=sys.stderr)
        return 1
    con = conectar(banco)
    try:
        with abrir_saude(*cfg) as s:
            r = medir(con, s)
    finally:
        con.close()
    print("exames: " + " ".join(f"{k}={v}" for k, v in r.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
