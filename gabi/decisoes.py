"""Canal de decisão: perguntas com opções numeradas que o Ricardo responde pelo Telegram/WhatsApp (o Hermes só apresenta e repassa o número).
R1: a Gabi pergunta, o Ricardo decide. R2: nada é enviado daqui. `efeito` vem de uma lista FECHADA e validada; nunca código livre.
Responder grava a decisão (origem 'canal') e aplica o efeito na mesma transação; só uma resposta por pergunta."""
import json

from gabi.db import transacao


class ErroDecisao(Exception):
    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo, self.mensagem = codigo, mensagem


def _conta_estado(estado: str):
    def aplicar(con, p: dict) -> None:
        r = con.execute("update conta set estado=? where id=? and excluido_em is null", (estado, p["conta_id"]))
        if r.rowcount != 1:
            raise ErroDecisao("conta_inexistente", "a conta não existe mais")
    return aplicar


def _conta_existe(con, p: dict) -> None:
    if not isinstance(p.get("conta_id"), int) or isinstance(p.get("conta_id"), bool) or \
            con.execute("select 1 from conta where id=? and excluido_em is null", (p["conta_id"],)).fetchone() is None:
        raise ErroDecisao("opcoes_invalidas", "conta_id não existe")


CAMPOS_NOVO_COMPROMISSO = {"nome", "extrato", "vencimento", "ajuste_dia_util", "valor_tipo", "valor_padrao", "forma", "obs", "ativo"}


def _compromisso_novo(con, p: dict):
    """Valida pela MESMA regra do cadastro (planilha) e devolve a linha pronta; não grava."""
    from gabi.rotas import cadastros as cad
    if not isinstance(p, dict) or not p.get("nome") or set(p) - CAMPOS_NOVO_COMPROMISSO:
        raise ErroDecisao("opcoes_invalidas", f"criar_compromisso aceita só os campos {sorted(CAMPOS_NOVO_COMPROMISSO)} e exige nome")
    if not isinstance(p.get("ativo", True), bool):
        raise ErroDecisao("opcoes_invalidas", "ativo deve ser true ou false")
    dado = {k: v for k, v in p.items() if k not in ("obs", "ativo")}
    dado["id"] = cad._id_unico(con, "compromisso_linha", cad._slug(str(p["nome"])))
    try:
        return cad.COMPROMISSOS._validar(con, dado, None)
    except Exception as e:  # HTTPException do cadastro: devolve o motivo como erro de decisão
        raise ErroDecisao("opcoes_invalidas", f"compromisso inválido: {getattr(e, 'detail', e)}")


def _criar_compromisso_validar(con, p: dict) -> None:
    _compromisso_novo(con, p)


def _criar_compromisso_aplicar(con, p: dict) -> None:
    from gabi.rotas import cadastros as cad
    linha = _compromisso_novo(con, p)  # dentro da transação da resposta: o id é recalculado agora, sem corrida
    cad.COMPROMISSOS._gravar(con, linha, p.get("ativo", True), p.get("obs"), True)


def _para_quem_validar(con, p: dict) -> None:
    if not isinstance(p, dict) or set(p) != {"estabelecimento", "pessoa_id"} or not str(p.get("estabelecimento") or "").strip():
        raise ErroDecisao("opcoes_invalidas", "atribuir_para_quem exige estabelecimento e pessoa_id, só esses dois")
    if con.execute("select 1 from pessoa where id=?", (p["pessoa_id"],)).fetchone() is None:
        raise ErroDecisao("opcoes_invalidas", "pessoa_id não existe")


def _para_quem_aplicar(con, p: dict) -> None:
    """Só preenche o que está sem dono (nunca troca um dono já escolhido); a origem é 'voce': foi o Ricardo quem decidiu."""
    _para_quem_validar(con, p)
    con.execute("update lancamento set para_quem_id=?, para_quem_origem='voce' where para_quem_id is null and coalesce(estabelecimento, descricao_original)=?",
                (p["pessoa_id"], p["estabelecimento"]))


def _canal_email_validar(con, p: dict) -> None:
    """Só o e-mail de um contato do Google cujo telefone é um canal whatsapp DESTA pessoa (nada de endereço livre), já normalizado."""
    from gabi.cobrar.cadastro import dados
    from gabi.correio.regras import endereco
    from gabi.escuta.caixa import normalizar_telefone
    if not isinstance(p, dict) or set(p) != {"pessoa_id", "email"} or not isinstance(p.get("pessoa_id"), str) or not isinstance(p.get("email"), str):
        raise ErroDecisao("opcoes_invalidas", "adicionar_canal_email exige pessoa_id e email, só esses dois")
    if endereco(p["email"]) != p["email"]:
        raise ErroDecisao("opcoes_invalidas", "email deve ser um endereço válido em minúsculas")
    pessoa = con.execute("select id, dados from pessoa where id=? and excluido_em is null", (p["pessoa_id"],)).fetchone()
    if pessoa is None:
        raise ErroDecisao("opcoes_invalidas", "pessoa_id não existe")
    numeros = {normalizar_telefone(c[9:]) or c[9:] for c in dados(pessoa).get("canais") or [] if isinstance(c, str) and c.startswith("whatsapp:")}
    if not any(con.execute("select 1 from contato_google_email where email=? and telefone=?", (p["email"], n)).fetchone() for n in numeros):
        raise ErroDecisao("opcoes_invalidas", "esse e-mail não é de um contato com o telefone desta pessoa")


def _canal_email_aplicar(con, p: dict) -> None:
    """Acrescenta `email:<endereço>` a `canais` (sem repetir) e não toca em mais nada de `pessoa.dados`."""
    from gabi.cobrar.cadastro import dados
    _canal_email_validar(con, p)  # a resposta pode vir dias depois: o contato pode ter mudado
    pessoa = con.execute("select dados from pessoa where id=?", (p["pessoa_id"],)).fetchone()
    d = dados(pessoa)
    canais = d.get("canais") if isinstance(d.get("canais"), list) else []
    if not any(isinstance(c, str) and c.lower() == f"email:{p['email']}" for c in canais):
        d["canais"] = canais + [f"email:{p['email']}"]
        con.execute("update pessoa set dados=? where id=?", (json.dumps(d, ensure_ascii=False), p["pessoa_id"]))


# efeito -> (validação na criação, aplicação na resposta). Acrescentar um efeito é mudança de código revisada, nunca dado.
EFEITOS = {
    "registrar_nota": (lambda con, p: None, lambda con, p: None),
    "marcar_conta_nao": (_conta_existe, _conta_estado("nao")),
    "marcar_conta_sim": (_conta_existe, _conta_estado("sim")),
    "criar_compromisso": (_criar_compromisso_validar, _criar_compromisso_aplicar),
    "atribuir_para_quem": (_para_quem_validar, _para_quem_aplicar),
    "adicionar_canal_email": (_canal_email_validar, _canal_email_aplicar),
}


def _validar(con, opcoes) -> list[dict]:
    if not isinstance(opcoes, list) or not 1 <= len(opcoes) <= 9:
        raise ErroDecisao("opcoes_invalidas", "informe de 1 a 9 opções")
    limpas = []
    for i, o in enumerate(opcoes, 1):
        if not isinstance(o, dict) or o.get("n") != i or isinstance(o.get("n"), bool) or not str(o.get("rotulo") or "").strip():
            raise ErroDecisao("opcoes_invalidas", "as opções devem ser numeradas 1, 2, 3... e ter rótulo")
        efeito = o.get("efeito")
        if efeito not in EFEITOS:
            raise ErroDecisao("opcoes_invalidas", f"efeito fora da lista: {sorted(EFEITOS)}")
        params = o.get("parametros") or {}
        if not isinstance(params, dict):
            raise ErroDecisao("opcoes_invalidas", "parametros deve ser um objeto")
        EFEITOS[efeito][0](con, params)
        limpas.append({"n": i, "rotulo": str(o["rotulo"]).strip(), "efeito": efeito, "parametros": params})
    return limpas


def criar_pergunta(con, tipo: str, titulo: str, contexto: str | None, opcoes, origem: str, agora: str) -> int:
    if not str(tipo or "").strip() or not str(titulo or "").strip():
        raise ErroDecisao("requisicao_invalida", "tipo e titulo são obrigatórios")
    limpas = _validar(con, opcoes)
    with transacao(con, imediata=True):
        cur = con.execute("insert into pergunta(tipo, titulo, contexto, opcoes, estado, criada_em, origem) values (?,?,?,?, 'aberta', ?, ?)",
                          (tipo.strip(), titulo.strip(), contexto, json.dumps(limpas, ensure_ascii=False), agora, origem))
    return cur.lastrowid


def _linha(r) -> dict:
    return {"id": r["id"], "tipo": r["tipo"], "titulo": r["titulo"], "contexto": r["contexto"], "estado": r["estado"],
            "criada_em": r["criada_em"], "respondida_em": r["respondida_em"], "escolha": r["escolha"],
            "opcoes": [{"n": o["n"], "rotulo": o["rotulo"]} for o in json.loads(r["opcoes"])]}  # o efeito não sai: é decisão do código, não do canal


def abertas(con) -> list[dict]:
    return [_linha(r) for r in con.execute("select * from pergunta where estado='aberta' order by id")]


def todas(con, limite: int = 50) -> list[dict]:
    return [_linha(r) for r in con.execute("select * from pergunta order by id desc limit ?", (limite,))]


def expirar(con, criadas_antes_de: str) -> int:
    with transacao(con, imediata=True):
        return con.execute("update pergunta set estado='expirada' where estado='aberta' and criada_em<?", (criadas_antes_de,)).rowcount


def responder(con, pergunta_id: int, n, quem: str, agora: str) -> dict:
    if isinstance(n, bool) or not isinstance(n, int):
        raise ErroDecisao("opcao_invalida", "a opção deve ser um número inteiro")
    with transacao(con, imediata=True):
        p = con.execute("select * from pergunta where id=?", (pergunta_id,)).fetchone()
        if p is None:
            raise ErroDecisao("nao_encontrada", "pergunta não existe")
        if p["estado"] == "expirada":
            raise ErroDecisao("expirada", "a pergunta expirou")
        if p["estado"] == "respondida":
            if p["escolha"] == n:
                return {"id": p["id"], "estado": "respondida", "escolha": n, "ja_respondida": True}
            raise ErroDecisao("ja_respondida", f"a pergunta já foi respondida com a opção {p['escolha']}")
        opcao = next((o for o in json.loads(p["opcoes"]) if o["n"] == n), None)
        if opcao is None:
            raise ErroDecisao("opcao_invalida", "número fora das opções")
        EFEITOS[opcao["efeito"]][1](con, opcao.get("parametros") or {})
        con.execute("update pergunta set estado='respondida', respondida_em=?, escolha=? where id=?", (agora, n, pergunta_id))
        con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'canal')",
                    (agora, quem, f"pergunta {pergunta_id} ({p['titulo']}): {n}) {opcao['rotulo']}"))
    return {"id": pergunta_id, "estado": "respondida", "escolha": n, "ja_respondida": False}
