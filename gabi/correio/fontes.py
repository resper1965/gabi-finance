"""Cadastro das contas de e-mail (`email_fonte`) e dos parâmetros `email.*`, editáveis no painel sem código (spec 2026-10-11-email-design, §3.8).
Só decide QUAIS contas o timer lê e em quais ele pode mover para a lixeira (duas chaves separadas); a leitura em si é `gabi.correio.sincronizar`.
Nenhum segredo aqui: o refresh token vive só no serviço de fontes. Critérios e VIPs são dados do dono e nunca vão para log nem auditoria."""
import json
import sqlite3

from gabi.correio.regras import PALAVRA_MAX, PALAVRAS_PADRAO, endereco, regra_valida
from gabi.fontes.google_oauth import ErroGoogleOAuth, conta_valida

PROVEDORES = ("google", "graph")
ESTADOS = ("sim", "nao", "a_decidir")
PADROES = {"criterios_emergencia": "", "vips": [], "lixeira_confianca": 0.9, "janela_dias": 14, "retencao_dias": 30, "retencao_msg_dias": 180,
           "dias_em_aberto": 7, "max_alertas_dia": 5, "palavras_protegidas": list(PALAVRAS_PADRAO), "regras_lixo": [],
           "remetentes_sistema": []}
CHAVES = {k: f"email.{k}" for k in PADROES}
CRITERIOS_MAX = 2000
VIPS_MAX = 200
PALAVRAS_MAX = 200
REGRAS_MAX = 500


class ErroFonte(ValueError):
    """Pedido inválido (400), inexistente (404) ou em conflito (409), com a mensagem em pt-BR para o painel."""

    def __init__(self, mensagem: str, nao_encontrado: bool = False, conflito: bool = False):
        super().__init__(mensagem)
        self.nao_encontrado, self.conflito = nao_encontrado, conflito


def listar(con) -> list[dict]:
    return [dict(r) for r in con.execute(
        "select f.id, f.conta, f.provedor, f.estado, f.lixeira, f.sincronizada_em, f.ultimo_erro,"
        " (select count(*) from email_msg m where m.fonte_id=f.id) as mensagens,"
        " (select count(*) from email_msg m where m.fonte_id=f.id and m.estado='na_lixeira') as na_lixeira"
        " from email_fonte f order by f.conta, f.id")]


def _existe(con, fonte_id: int) -> sqlite3.Row:
    r = con.execute("select * from email_fonte where id=?", (fonte_id,)).fetchone()
    if r is None:
        raise ErroFonte("conta de e-mail não existe", nao_encontrado=True)
    return r


def criar(con, conta, provedor="google") -> int:
    """Nova conta, sempre `a_decidir` e sem lixeira: nada é lido nem movido até o dono liberar."""
    try:
        conta = conta_valida(conta).lower()
    except ErroGoogleOAuth:
        raise ErroFonte("conta deve ser um e-mail válido") from None
    if provedor not in PROVEDORES:
        raise ErroFonte(f"provedor deve ser um de {list(PROVEDORES)}")
    try:
        return con.execute("insert into email_fonte(conta, provedor) values (?,?)", (conta, provedor)).lastrowid
    except sqlite3.IntegrityError:
        raise ErroFonte("essa conta já está cadastrada", conflito=True) from None


def alterar(con, fonte_id: int, corpo: dict) -> dict:
    """`estado` (sim|nao|a_decidir) e/ou `lixeira` (0|1). A lixeira só liga com a leitura liberada; tirar a leitura desliga a lixeira junto."""
    atual = _existe(con, fonte_id)
    if not isinstance(corpo, dict) or not ({"estado", "lixeira"} & set(corpo)):
        raise ErroFonte("envie estado e/ou lixeira")
    estado = corpo.get("estado", atual["estado"])
    if estado not in ESTADOS:
        raise ErroFonte(f"estado deve ser um de {list(ESTADOS)}")
    lixeira = corpo.get("lixeira", atual["lixeira"])
    if isinstance(lixeira, bool) or lixeira not in (0, 1):
        raise ErroFonte("lixeira deve ser 0 ou 1")
    if "lixeira" in corpo and lixeira == 1 and estado != "sim":  # pedido explícito de ligar; tirar a leitura só desliga a lixeira
        raise ErroFonte("só dá para ligar a lixeira com a leitura da conta liberada")
    if estado != "sim":
        lixeira = 0
    con.execute("update email_fonte set estado=?, lixeira=? where id=?", (estado, lixeira, fonte_id))
    return {"id": fonte_id, "estado": estado, "lixeira": lixeira}


# ---------------- parâmetros ----------------
def _inteiro(v, nome: str, minimo: int, maximo: int) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not minimo <= v <= maximo:
        raise ErroFonte(f"{nome} deve ser um inteiro de {minimo} a {maximo}")
    return v


def validar_parametros(corpo) -> dict:
    """Devolve os parâmetros normalizados (VIPs em minúsculas, sem repetir)."""
    if not isinstance(corpo, dict) or not corpo:
        raise ErroFonte("envie ao menos um parâmetro")
    extra = set(corpo) - set(PADROES)
    if extra:
        raise ErroFonte(f"parâmetros desconhecidos: {sorted(extra)}")
    saida = {}
    for k, v in corpo.items():
        if k == "criterios_emergencia":
            if not isinstance(v, str) or len(v) > CRITERIOS_MAX:
                raise ErroFonte(f"criterios_emergencia deve ser um texto de até {CRITERIOS_MAX} caracteres")
            v = v.strip()
        elif k == "vips":
            if not isinstance(v, list) or len(v) > VIPS_MAX or not all(isinstance(x, str) for x in v):
                raise ErroFonte(f"vips deve ser uma lista de até {VIPS_MAX} endereços de e-mail")
            normal = [endereco(x) for x in v]
            if not all(normal):
                raise ErroFonte("vips tem um endereço de e-mail inválido")
            v = list(dict.fromkeys(normal))
        elif k == "regras_lixo":
            if not isinstance(v, list) or len(v) > REGRAS_MAX or not all(isinstance(x, str) for x in v):
                raise ErroFonte(f"regras_lixo deve ser uma lista de até {REGRAS_MAX} endereços (a@x.com) ou domínios (@x.com)")
            normal = [regra_valida(x) for x in v]
            if not all(normal):
                raise ErroFonte("regras_lixo tem um endereço ou domínio inválido")
            v = list(dict.fromkeys(normal))
        elif k == "remetentes_sistema":
            if not isinstance(v, list) or len(v) > VIPS_MAX or not all(isinstance(x, str) for x in v):
                raise ErroFonte(f"remetentes_sistema deve ser uma lista de até {VIPS_MAX} endereços (a@x.com) ou domínios (@x.com)")
            normal = [regra_valida(x) for x in v]
            if not all(normal):
                raise ErroFonte("remetentes_sistema tem um endereço ou domínio inválido")
            v = list(dict.fromkeys(normal))
        elif k == "lixeira_confianca":
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0.7 <= v <= 1.0:
                raise ErroFonte("lixeira_confianca deve ser um número de 0,7 a 1,0")
            v = float(v)
        elif k == "janela_dias":
            _inteiro(v, k, 1, 60)
        elif k == "retencao_dias":
            _inteiro(v, k, 1, 365)
        elif k == "retencao_msg_dias":
            _inteiro(v, k, 90, 3650)
        elif k == "dias_em_aberto":
            _inteiro(v, k, 1, 30)
        elif k == "max_alertas_dia":
            _inteiro(v, k, 1, 50)
        elif k == "palavras_protegidas":
            if not isinstance(v, list) or len(v) > PALAVRAS_MAX or not all(isinstance(x, str) and len(x.strip()) <= PALAVRA_MAX for x in v):
                raise ErroFonte(f"palavras_protegidas deve ser uma lista de até {PALAVRAS_MAX} palavras de até {PALAVRA_MAX} caracteres")
            vistas: dict[str, str] = {}
            for x in v:
                if x.strip():
                    vistas.setdefault(x.strip().casefold(), x.strip())
            v = list(vistas.values())
        saida[k] = v
    return saida


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


def acrescentar_regra_lixo(con, texto) -> tuple[str, bool]:
    """Acrescenta a regra "sempre lixo" (`a@x.com` ou `@x.com`) a `email.regras_lixo`. Devolve a regra normalizada e se é nova (idempotente).
    Inválida ou acima do limite → `ErroFonte`. Quem chama abre a transação."""
    regra = regra_valida(texto)
    if regra is None:
        raise ErroFonte("informe um endereço (a@x.com) ou um domínio (@x.com)")
    atuais = parametros(con)["regras_lixo"]
    if regra in atuais:
        return regra, False
    gravar_parametros(con, validar_parametros({"regras_lixo": atuais + [regra]}))
    return regra, True


def remover_regra_lixo(con, texto) -> tuple[str, bool]:
    """Tira a regra de `email.regras_lixo`. Devolve a regra normalizada e se existia. Inválida → `ErroFonte`. Quem chama abre a transação."""
    regra = regra_valida(texto)
    if regra is None:
        raise ErroFonte("informe um endereço (a@x.com) ou um domínio (@x.com)")
    atuais = parametros(con)["regras_lixo"]
    if regra not in atuais:
        return regra, False
    gravar_parametros(con, {"regras_lixo": [r for r in atuais if r != regra]})
    return regra, True
