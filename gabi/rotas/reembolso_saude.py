"""Rota /api/v1/reembolso-saude: dossiês de reembolso do plano de saúde COM os nomes (paciente e prestador), lidos do cofre cifrado (ADR-014).
Só boss com grau total em saúde; o acesso entra no log `leitura` do cofre. Valor, CPF/CNPJ e conselho NÃO saem daqui. As ferramentas MCP não têm a chave e
falam só do número do dossiê; esta é a forma de saber quem é cada um. Consome: reembolso_saude.{cofre,dossies,requisitos}, identidade."""
import threading

from fastapi import APIRouter, Depends, Request

from gabi.envelope import envelope
from gabi.familia.saude import _log, abrir_saude
from gabi.identidade import Identidade, exigir_informacao
from gabi.reembolso_saude import cofre, dossies, requisitos
from gabi.rotas.dinheiro import _agora, _con, erro

router = APIRouter(prefix="/api/v1/reembolso-saude")
_TRAVA = threading.Lock()  # o cofre é regravado inteiro: um escritor por vez neste processo


@router.get("/dossies")
def listar(request: Request, ident: Identidade = Depends(exigir_informacao("saúde", "total"))):
    """Dossiês (número, paciente, prestador, mês, estado, o que falta e os documentos com tipo e estado); o acesso fica no log de saúde."""
    cfg = getattr(request.app.state, "saude", None)
    if not cfg:
        raise erro(503, "fonte_indisponivel", "o arquivo de saúde não está configurado (falta a chave)")
    con = _con(request)
    try:
        req = requisitos.carregar(con)
        hoje = _agora(request).date()
        with _TRAVA, abrir_saude(*cfg) as s:
            _log(s, ident.login, None, "reembolso:dossies")
            docs, nomes = cofre.docs(s), {d["id"]: d for d in cofre.dossies_todos(s)}
        faltam = {x["docs"][0]: x["faltam"] for x in dossies.resumo([d for d in docs if d["estado"] == "a_pedir"], hoje, req)}
        itens = []
        for did, dos in sorted(nomes.items()):
            ds = [d for d in docs if d["dossie_id"] == did]
            if not ds or all(d["estado"] == "autorizacao" for d in ds):
                continue
            falta = next((faltam[d["id"]] for d in ds if d["id"] in faltam), [])
            itens.append({"dossie": did, "paciente": dos["paciente"], "prestador": dos["prestador"], "mes": dos["mes"],
                          "estado": next(e for e in ("a_pedir", "sem_nf", "sem_aprovacao", "a_conferir", "pedido", "recebido") if any(d["estado"] == e for d in ds)),
                          "faltam": [requisitos.rotulo(req, i) for i in falta],
                          "documentos": [{"id": d["id"], "documento": d["documento"], "caso": d["caso"], "estado": d["estado"], "data": d["data"].isoformat()} for d in ds]})
        return envelope(con, {"dossies": itens}, agora=_agora(request))
    finally:
        con.close()
