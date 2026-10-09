"""Histórico das NFS-e emitidas (fonte: Nibo, só leitura). Grava metadados em `nota_fiscal` e guarda PDF/XML em pasta própria.

Idempotente por id da nota: reexecutar não duplica nem baixa de novo o que já está em disco. O que o Nibo diz sobre pagamento
(`nibo_pago`) NÃO é prova de recebimento (o Nibo está defasado); o recebimento real vem do extrato. Consome: db, fontes.nibo (via ponte)."""
import datetime as dt
import json
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from gabi.db import transacao

STATUS = {3: "autorizada", -4: "cancelada", -1: "negada"}
RETENCOES = ("iss", "ir", "pis", "cofins", "csll", "inss")


@dataclass
class ResumoNotas:
    lidas: int = 0
    novas: int = 0
    alteradas: int = 0
    arquivos: int = 0
    falhas: list[str] = field(default_factory=list)


def _centavos(v) -> int:
    return int((Decimal(str(v or 0)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _dia(v) -> str | None:
    return str(v)[:10] if v else None


def normalizar(n: dict, credito: dict | None) -> dict:
    """Uma nota do Nibo (+ o agendamento a receber dela, se houver) -> linha de `nota_fiscal` (sem os campos de arquivo)."""
    codigo = (n.get("status") or {}).get("code")
    if codigo not in STATUS:
        raise ValueError(f"status de NFS-e desconhecido: {codigo!r}")
    cli, agend, serv = n.get("customer") or {}, n.get("schedule") or {}, n.get("service") or {}
    credito = credito or {}
    return {
        "id": n["id"], "numero": str(n.get("number") or "") or None, "rps_numero": str(n.get("rpsNumber") or "") or None,
        "rps_serie": str(n.get("rpsSeries") or "") or None, "codigo_verificacao": n.get("verificationCode"),
        "emitente_cnpj": n.get("serviceProviderDocumentNumber"), "emissao": _dia(n.get("authorizeDate") or n.get("createDate")),
        "status": STATUS[codigo], "valor_bruto_centavos": _centavos(n.get("value")), "deducoes_centavos": _centavos(n.get("deductions")),
        "descontos_centavos": _centavos(n.get("discounts")), "tomador_nome": cli.get("name") or (n.get("stakeholder") or {}).get("name"),
        "tomador_doc": re.sub(r"\D", "", str(cli.get("cpfCnpj") or "")) or None, "tomador_email": cli.get("email"),
        "descricao": serv.get("description"), "retencoes": json.dumps({k: serv.get(k) for k in RETENCOES}, ensure_ascii=False),
        "agendamento_id": agend.get("id"), "vencimento": _dia(credito.get("dueDate") or agend.get("dueDate")),
        "valor_liquido_centavos": _centavos(credito.get("value", agend.get("value"))) if (credito or agend) else None,
        "nibo_pago": 1 if credito.get("isPaid") else 0, "nibo_pago_centavos": _centavos(credito.get("paidValue")),
        "pdf_id": n.get("pdfFileId"), "xml_id": n.get("xmlFileId"), "nibo_atualizado_em": n.get("updateDate"),
    }


def _nome_arquivo(l: dict, ext: str) -> str:
    numero = re.sub(r"\D", "", l["numero"] or "") or "sem-numero"
    ano = (l["emissao"] or "0000")[:4] if re.fullmatch(r"\d{4}", (l["emissao"] or "")[:4]) else "0000"
    return f"{ano}/NFSe-{numero.zfill(6)}-{re.sub(r'[^0-9a-f]', '', l['id'].lower())[:8]}.{ext}"


def _guardar(pasta: Path, relativo: str, conteudo: bytes) -> None:
    destino = (pasta / relativo).resolve()
    if not destino.is_relative_to(pasta.resolve()):
        raise ValueError("caminho fora da pasta de notas")
    destino.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parcial = destino.with_name(destino.name + ".parcial")
    parcial.write_bytes(conteudo)
    parcial.rename(destino)


COLUNAS = ["id", "numero", "rps_numero", "rps_serie", "codigo_verificacao", "emitente_cnpj", "emissao", "status", "valor_bruto_centavos",
           "deducoes_centavos", "descontos_centavos", "tomador_nome", "tomador_doc", "tomador_email", "descricao", "retencoes", "agendamento_id",
           "vencimento", "valor_liquido_centavos", "nibo_pago", "nibo_pago_centavos", "pdf_id", "xml_id", "nibo_atualizado_em"]


def importar(con, notas, creditos: dict, obter, pasta, agora: dt.datetime) -> ResumoNotas:
    """`creditos`: {scheduleId: agendamento a receber}. `obter(url) -> bytes` baixa PDF/XML. Falha de um arquivo não aborta: vai em `falhas` e a próxima rodada completa."""
    pasta, r = Path(pasta), ResumoNotas()
    for n in notas:
        r.lidas += 1
        l = normalizar(n, creditos.get((n.get("schedule") or {}).get("id")))
        atual = con.execute("select * from nota_fiscal where id=?", (l["id"],)).fetchone()
        with transacao(con):
            if atual is None:
                con.execute(f"insert into nota_fiscal({','.join(COLUNAS)}, importado_em, atualizado_em) values ({','.join('?' * len(COLUNAS))}, ?, ?)",
                            [*(l[c] for c in COLUNAS), agora.isoformat(), agora.isoformat()])
                r.novas += 1
            elif any(atual[c] != l[c] for c in COLUNAS):
                con.execute(f"update nota_fiscal set {', '.join(c + '=?' for c in COLUNAS[1:])}, atualizado_em=? where id=?",
                            [*(l[c] for c in COLUNAS[1:]), agora.isoformat(), l["id"]])
                r.alteradas += 1
        if l["status"] == "negada":
            continue
        for ext, campo, url in (("pdf", "pdf_arquivo", n.get("pdfFileUrl")), ("xml", "xml_arquivo", n.get("xmlFileUrl"))):
            if not url or con.execute(f"select {campo} from nota_fiscal where id=?", (l["id"],)).fetchone()[0]:
                continue
            rel = _nome_arquivo(l, ext)
            try:
                _guardar(pasta, rel, obter(url))
            except Exception as e:  # um arquivo ruim não derruba as outras 200 notas
                r.falhas.append(f"nota {l['numero'] or l['id']} ({ext}): {type(e).__name__}: {str(e)[:80]}")  # mensagens do cliente nunca levam o token (R5)
                continue
            con.execute(f"update nota_fiscal set {campo}=? where id=?", (rel, l["id"]))
            r.arquivos += 1
    return r
