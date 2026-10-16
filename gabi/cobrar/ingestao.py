"""Ingestão de comprovantes Pix do Paperless: lê o texto (OCR) dos documentos, grava `comprovante` e PROPÕE vínculos (R1: nunca confirma).
Idempotente por `paperless_id`; só acrescenta a etiqueta `gabi:comprovante` (R10). O Paperless chega pela ponte (GABI_FONTES_SOCKET): sem token aqui (R5).
Uso: python -m gabi.cobrar.ingestao. Consome: cobrar.extrator, cobrar.comprovantes, rodada, fontes.ambiente."""
import argparse
import datetime as dt
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from gabi.cobrar import extrator
from gabi.cobrar.comprovantes import propor_vinculos, registrar_comprovante
from gabi.db import conectar, migrar
from gabi.fontes.ambiente import fontes_do_ambiente
from gabi.fontes.paperless import ErroPaperless
from gabi.rodada import registrar_rodada
from gabi.hoje import hoje_brt

ETIQUETA = "gabi:comprovante"


@dataclass(frozen=True)
class ResumoIngestao:
    lidos: int
    novos: int
    sem_valor: int
    sem_etiqueta: int = 0


def ingerir(con, paperless, hoje: dt.date) -> ResumoIngestao:
    ja = {r[0] for r in con.execute("select paperless_id from comprovante")}
    lidos = novos = sem_valor = sem_etiqueta = 0
    for d in paperless.docs():
        if d["id"] in ja:
            continue
        texto = d.get("content") or ""
        if extrator.tipo_documento(texto, hoje) != "comprovante_pix":
            continue
        lidos += 1
        dados = extrator.ler_comprovante_pix(texto)
        if not dados or not dados.get("valor"):
            sem_valor += 1
            continue
        data = dados.get("data") or (d.get("created") or "")[:10]
        if not data:
            sem_valor += 1
            continue
        doc_cnpj = re.sub(r"\D", "", dados.get("cpf_cnpj") or "")
        cnpj = doc_cnpj if len(doc_cnpj) == 14 else None
        cid = registrar_comprovante(con, paperless_id=d["id"], tipo="comprovante_pix", valor_centavos=round(dados["valor"] * 100), data=data, cnpj=cnpj)
        propor_vinculos(con, cid)
        novos += 1
        try:
            paperless.etiquetar(d["id"], [ETIQUETA])
        except ErroPaperless:
            sem_etiqueta += 1  # o comprovante já está gravado; a etiqueta é só conveniência
    return ResumoIngestao(lidos, novos, sem_valor, sem_etiqueta)


def main(banco: Path, paperless=None) -> int:
    paperless = paperless or fontes_do_ambiente()["paperless"]()
    if paperless is None:
        print("ERRO: Paperless não configurado no serviço de fontes")
        return 1
    con = conectar(banco)
    migrar(con, Path(__file__).resolve().parent.parent.parent / "migrations")
    try:
        with registrar_rodada(con, "comprovantes-paperless") as r:
            resumo = ingerir(con, paperless, hoje_brt())
            r.lidos, r.novos = resumo.lidos, resumo.novos
            if resumo.sem_valor or resumo.sem_etiqueta:
                r.aviso = f"{resumo.sem_valor} comprovante(s) sem valor legível; {resumo.sem_etiqueta} sem etiqueta"
    except ErroPaperless as e:
        print(f"ERRO Paperless: {e}")
        return 1
    print(f"comprovantes: lidos={resumo.lidos} novos={resumo.novos} sem_valor={resumo.sem_valor}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", default=os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db"))
    sys.exit(main(Path(ap.parse_args().banco)))
