"""Propostas de criar/corrigir contato da ness (sem modelo, depois da sincronização). Nada é escrito aqui: só se gera, lista e decide.
`listar` devolve nome e telefone porque alimenta o painel; nada neste módulo imprime nem registra nome ou número."""
import re
import unicodedata

from gabi.db import transacao
from gabi.escuta import contatos
from gabi.escuta.interacao import interacao, passa_piso

_E164 = re.compile(r"^\+\d{10,15}$")
ESTADOS_DECISAO = ("aprovada", "recusada")


class ErroProposta(ValueError):
    """Pedido inválido (400), inexistente (404) ou em conflito (409), com a mensagem em pt-BR para o painel."""

    def __init__(self, mensagem: str, nao_encontrado: bool = False, conflito: bool = False):
        super().__init__(mensagem)
        self.nao_encontrado, self.conflito = nao_encontrado, conflito


def _nome(v) -> str | None:
    return v.strip()[:200] if isinstance(v, str) and v.strip() else None


_LIXO = "|¦*_~^`\\<>="  # símbolos que sobram em nomes de contato; hífen, parênteses, ponto, apóstrofo e & são nome de verdade


def limpar_nome(nome: str) -> str:
    """Só tira lixo: sobrescrito/subscrito (`⁹`), símbolos de `_LIXO` soltos ou nas pontas e espaço sobrando. Não mexe em caixa nem em dígito comum (EMR3)."""
    sem = "".join(c for c in nome if not unicodedata.name(c, "").startswith(("SUPERSCRIPT", "SUBSCRIPT")))
    palavras = [w for w in sem.split() if w.strip(_LIXO)]
    return " ".join(w.strip(_LIXO) if w[0] in _LIXO or w[-1] in _LIXO else w for w in palavras)


def _letra_latina_ou_digito(c: str) -> bool:
    return unicodedata.name(c, "").startswith(("LATIN", "DIGIT"))


def _digitos(t: str) -> str:
    return re.sub(r"\D", "", t or "").lstrip("0")


def _muda_digitos(original: str, e164: str) -> bool:
    """Correção = a normalização muda os DÍGITOS do celular (ex.: celular antigo de 8 dígitos que ganhou o 9), nunca só a formatação
    (espaço, hífen, parênteses, +55, zero de discagem). Compara os dígitos do texto original sem DDI 55 com os do E.164 sem +55."""
    if not e164.startswith("+55"):
        return False
    d = _digitos(original)
    if len(d) > 11 and d.startswith("55"):
        d = d[2:].lstrip("0")
    return d != e164[3:].lstrip("0")


def _ja_decidida(con, conta, tipo, graph_id, telefone, nome) -> bool:
    return con.execute("select 1 from contato_proposta where conta=? and tipo=? and graph_id is ? and telefone_depois=? and nome_depois=? "
                       "and estado in ('recusada','aplicada')", (conta, tipo, graph_id, telefone, nome)).fetchone() is not None


def _inserir(con, agora, tipo, conta, graph_id, antes_nome, antes_tel, nome, tel, origem, email=None) -> int:
    if _ja_decidida(con, conta, tipo, graph_id, tel, nome):
        return 0
    return con.execute("insert or ignore into contato_proposta(tipo, conta, graph_id, nome_antes, telefone_antes, nome_depois, telefone_depois, origem, criada_em, email_depois) "
                       "values (?,?,?,?,?,?,?,?,?,?)", (tipo, conta, graph_id, antes_nome, antes_tel, nome, tel, origem, agora, email)).rowcount


_STOP = {"dos", "das", "del"}  # "de/da/do" já caem fora por ter menos de 3 letras


def _partes(nome: str | None) -> set[str]:
    sem = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().lower()
    return set(re.findall(r"[a-z]{3,}", sem)) - _STOP


def nome_compativel(a: str | None, b: str | None) -> bool:
    """Os nomes dividem ao menos uma parte (sem acento nem caixa, só partes de 3+ letras, sem preposição)."""
    return bool(_partes(a) & _partes(b))


MAX_EMAILS = 3  # o Outlook guarda poucos e-mails por contato (não verificado; limite seguro) e a ponte recusa mais de 5
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+$")


def _email_valido(e) -> str | None:
    e = (e or "").strip().lower()
    return e if _EMAIL.match(e) else None


def _emails(con, agora: str) -> tuple[int, int]:
    """adicionar_email: só para contato da ness com UMA linha em contato_graph (a ponte recusa contato cujos telefones atuais difiram do enviado),
    telefone que não aparece em outro contato. Só entram e-mails de linhas do Google cujo próprio nome é compatível com o do contato; linha de nome
    incompatível ou nulo no mesmo telefone, mais de MAX_EMAILS e-mails distintos ou conta do contato que já tem e-mail para o telefone: nada se propõe
    (a última nem conta em revisar). Devolve (propostas novas, contatos com e-mail barrados)."""
    por_contato: dict[tuple, list] = {}
    donos: dict[str, set] = {}
    for r in con.execute("select conta, graph_id, nome, telefone from contato_graph order by conta, graph_id, telefone_original").fetchall():
        por_contato.setdefault((r["conta"], r["graph_id"]), []).append(r)
        if r["telefone"] is not None:
            donos.setdefault(r["telefone"], set()).add((r["conta"], r["graph_id"]))
    novas = revisar = 0
    for (conta, gid), rs in por_contato.items():
        telefones = {r["telefone"] for r in rs if r["telefone"] is not None}
        nome, tel = _nome(rs[0]["nome"]), rs[0]["telefone"]
        emails: set[str] = set()
        duvida = ja_tem = False
        for t in telefones:
            for g in con.execute("select email, nome, conta from contato_google_email where telefone=?", (t,)).fetchall():
                e = _email_valido(g["email"])
                if not e:
                    continue
                if g["conta"] == conta:
                    ja_tem = True  # e-mail que o próprio contato da ness já tem (o sincronizar o espelha aqui): nada a propor
                elif nome_compativel(nome, g["nome"]):
                    emails.add(e)
                else:
                    duvida = True  # e-mail de outra pessoa (ou de linha sem nome) no mesmo telefone: em dúvida, não
        if ja_tem or not (emails or duvida):
            continue
        if duvida or len(emails) > MAX_EMAILS or len(rs) != 1 or tel is None or len(donos[tel]) != 1:
            revisar += 1
            continue
        novas += _inserir(con, agora, "adicionar_email", conta, gid, nome, tel, nome, tel, "google_email", ";".join(sorted(emails)))
    return novas, revisar


def _sem_cara_de_telefone(original) -> bool:
    """Só o que claramente não é número (código curto, menos de 7 dígitos, sem ramal nem lista). Ramal, vários números ou número sem DDD ficam para o dono."""
    texto = (original or "").strip()
    return bool(texto) and len(re.sub(r"\D", "", texto)) < 7 and not contatos._RAMAL.search(texto)


def _limpeza(con, agora: str) -> tuple[int, int, int]:
    """corrigir_nome (um por contato), apagar_contato (nome limpo de 1 caractere, contato com 1 telefone válido e sem e-mail) e apagar_telefone
    (um por telefone que não normaliza e não é estrangeiro). Dado de terceiros só vai para a fila, nunca para log."""
    nomes = apagar_c = apagar_t = 0
    linhas = con.execute("select conta, graph_id, nome, telefone_original, telefone from contato_graph order by conta, graph_id, telefone_original").fetchall()
    por_contato: dict[tuple, list] = {}
    for r in linhas:
        por_contato.setdefault((r["conta"], r["graph_id"]), []).append(r)
    for (conta, gid), rs in por_contato.items():
        nome = _nome(rs[0]["nome"])
        limpo = limpar_nome(nome) if nome else ""
        if len(limpo) == 1:
            if not _letra_latina_ou_digito(limpo):
                continue  # nome de 1 caractere CJK, emoji ou invisível é nome (ou lixo que o dono vê), não "U": nada a apagar
            r = rs[0]
            if len(rs) == 1 and r["telefone"] is not None and not con.execute(
                    "select 1 from contato_google_email where conta=? and telefone=?", (conta, r["telefone"])).fetchone():
                apagar_c += _inserir(con, agora, "apagar_contato", conta, gid, nome, r["telefone"], limpo, "", "nome_curto")
        elif nome and limpo and limpo != nome:
            nomes += _inserir(con, agora, "corrigir_nome", conta, gid, nome, None, limpo, "", "nome_sujo")
        if nome:
            for r in rs:
                if r["telefone"] is None and len(r["telefone_original"]) <= 30 and _sem_cara_de_telefone(r["telefone_original"]):
                    # telefone_depois repete o número só como chave de deduplicação: um contato pode ter vários inválidos
                    apagar_t += _inserir(con, agora, "apagar_telefone", conta, gid, nome, r["telefone_original"], nome, r["telefone_original"], "telefone_invalido")
    return nomes, apagar_c, apagar_t


def gerar(con, agora: str) -> dict:
    """Gera as propostas pendentes e devolve só contagens; adicionar_email = propostas novas, revisar = contatos com e-mail do Google barrados pelos filtros,
    abaixo_do_piso = remetentes aprovados que não viram `criar` por falta de interação (1 resposta ou 5 mensagens nos últimos 12 meses)."""
    criar = corrigir = abaixo = 0
    conta = contatos.conta_origem(con)
    with transacao(con):
        for r in con.execute("select numero, nome from escuta_remetente where estado='aprovado' and nome is not null and trim(nome)<>'' order by numero").fetchall():
            nome, numero = _nome(r["nome"]), r["numero"]
            if nome is None or not _E164.match(numero or ""):
                continue
            if con.execute("select 1 from contato_graph where telefone=?", (numero,)).fetchone() or \
                    con.execute("select 1 from contato_google where telefone=?", (numero,)).fetchone():
                continue
            if not passa_piso(interacao(con, agora, telefone=numero)):
                abaixo += 1
                continue
            criar += _inserir(con, agora, "criar", conta, None, None, None, nome, numero, "whatsapp")
        for r in con.execute("select conta, graph_id, nome, telefone_original, telefone from contato_graph where campo='mobile' and telefone is not null "
                             "order by conta, graph_id, telefone_original").fetchall():
            nome, novo = _nome(r["nome"]), r["telefone"]
            if nome is None or not _E164.match(novo) or not _muda_digitos(r["telefone_original"], novo):
                continue
            if con.execute("select 1 from contato_graph where telefone=? and not (conta=? and graph_id=? and telefone_original=?)",
                           (novo, r["conta"], r["graph_id"], r["telefone_original"])).fetchone():
                continue  # outro contato (ou outro campo deste) já tem o número: corrigir criaria duplicata
            corrigir += _inserir(con, agora, "corrigir", r["conta"], r["graph_id"], r["nome"], r["telefone_original"], nome, novo, "telefone_invalido")
        nomes, apagar_c, apagar_t = _limpeza(con, agora)
        add_email, revisar = _emails(con, agora)
    return {"criar": criar, "corrigir": corrigir, "corrigir_nome": nomes, "apagar_telefone": apagar_t, "apagar_contato": apagar_c,
            "adicionar_email": add_email, "revisar": revisar, "abaixo_do_piso": abaixo}


def listar(con, estado: str | None = None) -> list[dict]:
    if estado is None:
        linhas = con.execute("select * from contato_proposta order by id")
    else:
        linhas = con.execute("select * from contato_proposta where estado=? order by id", (estado,))
    return [dict(r) for r in linhas]


MAX_IDS = 2000


def ids_validos(ids) -> list[int]:
    """Lista não vazia de inteiros (bool não conta), no máximo MAX_IDS; senão ErroProposta (400)."""
    if not isinstance(ids, list) or not ids or len(ids) > MAX_IDS or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        raise ErroProposta(f"ids deve ser uma lista de 1 a {MAX_IDS} inteiros")
    return list(dict.fromkeys(ids))


def decidir(con, proposta_id: int, estado: str, login: str, agora: str, auditar=None) -> None:
    """pendente -> aprovada|recusada; aprovada -> recusada (o dono desfaz a aprovação antes da gravação). O resto é terminal (409)."""
    if estado not in ESTADOS_DECISAO:
        raise ErroProposta("Decisão inválida.")
    de = ("pendente",) if estado == "aprovada" else ("pendente", "aprovada")
    with transacao(con):
        r = con.execute("select estado from contato_proposta where id=?", (proposta_id,)).fetchone()
        if r is None:
            raise ErroProposta("Proposta não encontrada.", nao_encontrado=True)
        if r["estado"] not in de:
            raise ErroProposta("A proposta já foi decidida.", conflito=True)
        n = con.execute(f"update contato_proposta set estado=?, decidida_em=?, decidida_por=? where id=? and motivo is null and estado in ({','.join('?' * len(de))})",
                        (estado, agora, login, proposta_id, *de)).rowcount
        if not n:
            raise ErroProposta("A proposta já foi decidida ou está sendo gravada.", conflito=True)
        if auditar is not None:
            auditar()  # dentro da transação: se falhar, a decisão não fica


def aprovar_correcoes(con, login: str, agora: str, ids, auditar=None) -> int:
    """Aprova só as correções (de telefone e de nome) e os adicionar_email pendentes cujos ids o painel mostrou (nunca o que o dono não viu);
    criar, apagar_telefone, apagar_contato e não pendentes ficam como estão: apagar e criar só se aprovam um a um."""
    ids = ids_validos(ids)
    with transacao(con):
        n = con.execute(f"update contato_proposta set estado='aprovada', decidida_em=?, decidida_por=? "
                        f"where id in ({','.join('?' * len(ids))}) and tipo in ('corrigir','corrigir_nome','adicionar_email') and estado='pendente'", (agora, login, *ids)).rowcount
        if auditar is not None and n:
            auditar(n)  # dentro da transação: se falhar, nada fica aprovado
        return n
