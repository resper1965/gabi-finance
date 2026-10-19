"""Cadastro das fontes de agenda (`agenda_fonte`) e dos parâmetros `agenda.*`, editáveis no painel sem código (spec 2026-10-11-agenda-design, §3.7).
Só decide QUAIS contas/calendários o timer lê; a leitura em si é `gabi.agenda.sincronizar`. Nenhum segredo aqui: o refresh token vive só no serviço de fontes."""
import json
import sqlite3
from typing import Callable

from gabi.agenda import consulta, tempo
from gabi.fontes.google_oauth import ErroGoogleOAuth, conta_valida

PROVEDORES = ("google", "graph")
AUTENTICACOES = ("oauth", "delegacao")
ESTADOS = ("sim", "nao", "a_decidir")
PADROES = {"privados": "mostrar", "fuso": consulta.FUSO_PADRAO, "janela_passado_dias": 7, "janela_futuro_dias": 90}
CHAVES = {k: f"agenda.{k}" for k in PADROES}


class ErroFonte(ValueError):
    """Pedido inválido (400) ou inexistente (404), com a mensagem em pt-BR para o painel."""

    def __init__(self, mensagem: str, nao_encontrado: bool = False, conflito: bool = False):
        super().__init__(mensagem)
        self.nao_encontrado, self.conflito = nao_encontrado, conflito


def listar(con) -> list[dict]:
    return [dict(r) for r in con.execute(
        "select f.id, f.conta, f.provedor, f.calendario_id, f.nome, f.estado, f.auth, f.sincronizada_em, f.ultimo_erro,"
        " (select count(*) from agenda_evento e where e.fonte_id=f.id) as eventos from agenda_fonte f order by f.conta, f.id")]


def _existe(con, fonte_id: int) -> sqlite3.Row:
    r = con.execute("select * from agenda_fonte where id=?", (fonte_id,)).fetchone()
    if r is None:
        raise ErroFonte("fonte de agenda não existe", nao_encontrado=True)
    return r


def criar(con, conta, provedor, auth="oauth") -> int:
    """Nova conta (calendário principal), sempre `a_decidir`: nada é lido até o Ricardo liberar."""
    try:
        conta = conta_valida(conta).lower()
    except ErroGoogleOAuth:
        raise ErroFonte("conta deve ser um e-mail válido") from None
    if provedor not in PROVEDORES:
        raise ErroFonte(f"provedor deve ser um de {list(PROVEDORES)}")
    if auth not in AUTENTICACOES:
        raise ErroFonte(f"auth deve ser um de {list(AUTENTICACOES)}")
    try:
        return con.execute("insert into agenda_fonte(conta, provedor, calendario_id, auth) values (?,?, 'primary', ?)", (conta, provedor, auth)).lastrowid
    except sqlite3.IntegrityError:
        raise ErroFonte("essa conta já está cadastrada", conflito=True) from None


def definir_estado(con, fonte_id: int, estado) -> None:
    if estado not in ESTADOS:
        raise ErroFonte(f"estado deve ser um de {list(ESTADOS)}")
    _existe(con, fonte_id)
    # fonte que sai de "lendo" não carrega o erro antigo (o painel mostraria "Último erro" de algo que ninguém mais lê)
    con.execute("update agenda_fonte set estado=?, ultimo_erro=case when ?='sim' then ultimo_erro else null end where id=?", (estado, estado, fonte_id))


def descobrir_calendarios(con, fonte_id: int, listar_calendarios: Callable[[str], list[dict]]) -> list[dict]:
    """Uma `agenda_fonte` por calendário que a conta enxerga, `a_decidir` (o que já existe mantém o estado). O principal é o `primary` da própria conta."""
    f = _existe(con, fonte_id)
    saida = []
    for c in listar_calendarios(f["conta"]):
        cal = "primary" if c.get("principal") else c["id"]
        ja = con.execute("select id from agenda_fonte where conta=? and calendario_id=?", (f["conta"], cal)).fetchone()
        if ja:
            con.execute("update agenda_fonte set nome=? where id=?", (c.get("nome"), ja["id"]))
            fid = ja["id"]
        else:
            fid = con.execute("insert into agenda_fonte(conta, provedor, calendario_id, nome, auth) values (?,?,?,?,?)",
                              (f["conta"], f["provedor"], cal, c.get("nome"), f["auth"])).lastrowid
        r = con.execute("select id, calendario_id, nome, estado from agenda_fonte where id=?", (fid,)).fetchone()
        saida.append({**dict(r), "nova": ja is None})
    return saida


# ---------------- parâmetros ----------------
def _inteiro(v, nome: str, minimo: int, maximo: int) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not minimo <= v <= maximo:
        raise ErroFonte(f"{nome} deve ser um inteiro de {minimo} a {maximo}")
    return v


def validar_parametros(corpo: dict) -> dict:
    if not corpo:
        raise ErroFonte("envie ao menos um parâmetro")
    extra = set(corpo) - set(PADROES)
    if extra:
        raise ErroFonte(f"parâmetros desconhecidos: {sorted(extra)}")
    for k, v in corpo.items():
        if k == "privados" and v not in consulta.POLITICAS:
            raise ErroFonte(f"privados deve ser um de {list(consulta.POLITICAS)}")
        elif k == "fuso":
            try:
                if not isinstance(v, str):
                    raise ValueError
                tempo._zona(v)
            except ValueError:
                raise ErroFonte("fuso inválido (ex.: America/Sao_Paulo)") from None
        elif k == "janela_passado_dias":
            _inteiro(v, k, 0, 60)
        elif k == "janela_futuro_dias":
            _inteiro(v, k, 7, 365)
    return corpo


def parametros(con) -> dict:
    saida = {}
    for k, chave in CHAVES.items():
        r = con.execute("select valor from parametro where chave=?", (chave,)).fetchone()
        try:
            saida[k] = json.loads(r[0]) if r else PADROES[k]
        except (ValueError, TypeError):
            saida[k] = PADROES[k]
    return saida


def gravar_parametros(con, novos: dict) -> None:
    for k, v in novos.items():
        con.execute("insert into parametro(chave, valor) values (?,?) on conflict(chave) do update set valor=excluded.valor",
                    (CHAVES[k], json.dumps(v, ensure_ascii=False)))
