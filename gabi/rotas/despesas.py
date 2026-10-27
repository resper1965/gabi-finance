"""Despesas (/api/v1/despesas): criar fixa ou avulsa, mudar daqui em diante, mexer num mês, dispensar, encerrar e excluir.

Só chama `dinheiro.despesas` (as regras moram lá); `quem` = login, `origem` = 'painel'. Cada escrita já recalcula A Pagar.
`LookupError` → 404 `nao_encontrado`; `ValueError` → 400 `requisicao_invalida`. Dinheiro sai como string em reais.
Consome: dinheiro.despesas, envelope, identidade.
"""
from typing import Callable

from fastapi import APIRouter, Depends, Request

from gabi.dinheiro import despesas
from gabi.envelope import envelope
from gabi.hoje import BRT
from gabi.identidade import Identidade, exigir
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, erro

router = APIRouter(prefix="/api/v1", dependencies=[Depends(exigir("boss"))])
TIPOS = {"fixa", "avulsa"}
SITUACOES = {"ativa", "encerrada"}


def _so(corpo: dict, permitidos: set) -> None:
    extra = set(corpo) - permitidos
    if extra:
        raise erro(400, "requisicao_invalida", f"campos desconhecidos: {sorted(extra)}")


async def _corpo_opcional(request: Request) -> dict:
    """Corpo vazio vale como `{}` (encerrar e dispensar não precisam de corpo)."""
    c = await _json(request)
    return {} if c is None else _corpo(c)


def _texto_ou_nada(corpo: dict, campo: str):
    v = corpo.get(campo)
    if v is not None and not isinstance(v, str):
        raise erro(400, "requisicao_invalida", f"{campo} deve ser texto")
    return v


def _rodar(request: Request, faz: Callable) -> dict:
    """Roda a regra com a conexão e devolve o envelope; traduz os erros das regras para HTTP."""
    con = _con(request)
    try:
        try:
            dados = faz(con, _agora(request))
        except LookupError as e:
            raise erro(404, "nao_encontrado", str(e))
        except ValueError as e:
            raise erro(400, "requisicao_invalida", str(e))
        return envelope(con, dados, agora=_agora(request))
    finally:
        con.close()


@router.get("/despesas")
def listar(request: Request, tipo: str | None = None, situacao: str | None = None):
    """Despesas por série (versão vigente + histórico de versões), com o próximo vencimento. Filtros: tipo (fixa|avulsa), situacao (ativa|encerrada)."""
    if tipo is not None and tipo not in TIPOS:
        raise erro(400, "requisicao_invalida", f"tipo deve ser um de {sorted(TIPOS)}")
    if situacao is not None and situacao not in SITUACOES:
        raise erro(400, "requisicao_invalida", f"situacao deve ser uma de {sorted(SITUACOES)}")
    return _rodar(request, lambda con, agora: {"itens": despesas.listar(con, agora.astimezone(BRT).date(), tipo, situacao)})


@router.post("/despesas", status_code=201)
async def criar(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Cria despesa fixa (desde o mês em curso) ou avulsa (`data` AAAA-MM-DD obrigatória). Valor em `valor_padrao` (reais)."""
    corpo = _corpo(await _json(request))
    campos = {k: v for k, v in corpo.items() if k not in ("tipo", "data")}
    tipo, data = corpo.get("tipo"), corpo.get("data")
    if tipo not in TIPOS:
        raise erro(400, "requisicao_invalida", f"tipo deve ser um de {sorted(TIPOS)}")
    if tipo == "fixa" and data is not None:
        raise erro(400, "requisicao_invalida", "data só vale para despesa avulsa; a fixa usa vencimento (dia:N)")
    if tipo == "avulsa" and data is None:
        raise erro(400, "requisicao_invalida", "data é obrigatória na despesa avulsa")
    if tipo == "fixa":
        return _rodar(request, lambda con, agora: despesas.criar_fixa(con, agora, ident.login, "painel", campos))
    return _rodar(request, lambda con, agora: despesas.criar_avulsa(con, agora, ident.login, "painel", campos, data))


@router.patch("/despesas/{id_}")
async def mudar(id_: str, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Muda daqui em diante: do mês em curso se não foi pago, senão do próximo; `a_partir` (AAAA-MM) vence a regra."""
    corpo = _corpo(await _json(request))
    a_partir = _texto_ou_nada(corpo, "a_partir")
    campos = {k: v for k, v in corpo.items() if k != "a_partir"}
    return _rodar(request, lambda con, agora: despesas.mudar(con, agora, ident.login, "painel", id_, campos, a_partir))


@router.post("/despesas/{id_}/mes/{mes}")
async def mudar_mes(id_: str, mes: str, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Valor e/ou vencimento (AAAA-MM-DD) só deste mês."""
    corpo = _corpo(await _json(request))
    _so(corpo, {"valor", "vencimento"})
    valor, vencimento = _texto_ou_nada(corpo, "valor"), _texto_ou_nada(corpo, "vencimento")
    return _rodar(request, lambda con, agora: despesas.mudar_mes(con, agora, ident.login, "painel", id_, mes, valor, vencimento))


@router.post("/despesas/{id_}/mes/{mes}/dispensar")
def dispensar(id_: str, mes: str, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Este mês não tem a despesa: sai de A Pagar (mês pago é recusado)."""
    return _rodar(request, lambda con, agora: despesas.dispensar_mes(con, agora, ident.login, "painel", id_, mes))


@router.delete("/despesas/{id_}/mes/{mes}/dispensar")
def desfazer_dispensa(id_: str, mes: str, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Desfaz a dispensa do mês: a despesa volta para A Pagar."""
    return _rodar(request, lambda con, agora: despesas.desfazer_dispensa(con, agora, ident.login, "painel", id_, mes))


@router.post("/despesas/{id_}/encerrar")
async def encerrar(id_: str, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Encerra: `ultimo_mes` (AAAA-MM) ou o mês anterior ao primeiro não pago. O que não foi pago depois sai de A Pagar."""
    corpo = await _corpo_opcional(request)
    _so(corpo, {"ultimo_mes"})
    ultimo = _texto_ou_nada(corpo, "ultimo_mes")
    return _rodar(request, lambda con, agora: despesas.encerrar(con, agora, ident.login, "painel", id_, ultimo))


@router.delete("/despesas/{id_}")
def excluir(id_: str, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Cadastro errado: exclui se nunca teve pagamento; senão encerra e devolve `encerrada: true`."""
    return _rodar(request, lambda con, agora: despesas.excluir(con, agora, ident.login, "painel", id_))
