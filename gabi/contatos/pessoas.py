"""Qual `pessoa` tem um número de WhatsApp: uma regra só, usada ao trazer contatos como pessoa (veio de escuta/remetentes.py; ADR-023)."""
import hashlib

from gabi.cobrar.cadastro import dados
from gabi.contatos.contatos import nome_do_numero
from gabi.contatos.telefone import normalizar_telefone

PAPEIS = ("familia", "prestador", "cobranca")  # papéis antigos da escuta: pessoa que já os tem vem primeiro


def _aprovada(d: dict) -> bool:
    return d.get("escuta_aprovada") is True and d.get("papel_escuta") in PAPEIS


def _casa(d: dict, numero: str) -> bool:
    canais = d.get("canais")
    if not isinstance(canais, list):
        return False
    return any(isinstance(c, str) and c.startswith("whatsapp:") and (c == f"whatsapp:{numero}" or normalizar_telefone(c[len("whatsapp:"):]) == numero)
               for c in canais)  # id cru (LID) casa pelo canal exato


def _pessoas_do_numero(con, numero: str) -> list:
    """Pessoas ativas com esse número em canais (qualquer formato), a já aprovada primeiro, depois por id."""
    achadas = [p for p in con.execute("select id, nome, dados from pessoa where excluido_em is null order by id") if _casa(dados(p), numero)]
    return sorted(achadas, key=lambda p: not _aprovada(dados(p)))


def garantir_pessoa(con, numero: str, nome: str | None) -> tuple[str, dict, str]:
    """Única regra de qual `pessoa` tem este número (aprovar e trazer-dos-contatos caem na MESMA linha). Dentro de uma transação do chamador.
    Reaproveita a que já tem o número (a aprovada primeiro); senão usa o id `wa-`+sha1[:10], reativando a excluída ou criando.
    Devolve (id, dados, estado) com estado 'existente' | 'reativada' | 'criada'; nunca mexe em escuta_aprovada/papel_escuta."""
    achadas = _pessoas_do_numero(con, numero)
    if achadas:
        return achadas[0]["id"], dados(achadas[0]), "existente"
    pid = "wa-" + hashlib.sha1(numero.encode()).hexdigest()[:10]
    antiga = con.execute("select dados from pessoa where id=?", (pid,)).fetchone()
    if antiga is not None:  # a pessoa deste número foi excluída: reativa em vez de colidir na chave
        d, estado = dados(antiga), "reativada"
        con.execute("update pessoa set excluido_em=null where id=?", (pid,))
    else:
        d, estado = {}, "criada"
        con.execute("insert into pessoa(id, nome, dados, origem) values (?,?,?, 'escuta')", (pid, nome or nome_do_numero(con, numero) or numero, "{}"))
    canais = d.get("canais") if isinstance(d.get("canais"), list) else []
    if not _casa({"canais": canais}, numero):
        d["canais"] = canais + [f"whatsapp:{numero}"]
    return pid, d, estado
