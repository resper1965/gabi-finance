"""Vocabulário fechado do reembolso de saúde: tipos de documento, campos exigíveis, sinônimos e etiquetas `gabi:*`.
Puro (sem banco, sem rede). Os ROTULOS são só o padrão de exibição: o Ricardo troca em `parametro` (`rotulos`)."""
import unicodedata

ETIQUETA_ENTRADA = "gabi:saude-reembolso"
ETIQUETA_PEDIDO = "gabi:reembolso-pedido"
ETIQUETA_RECEBIDO = "gabi:reembolso-recebido"
# etiquetas do gabi-fin: só LIDAS (adoção dos documentos antigos); o brain nunca as altera
ETIQUETAS_LEGADAS = {"reembolso-a-pedir": "a_pedir", "reembolso-pedido": "pedido", "reembolso-recebido": "recebido"}
TIPO_PAPERLESS_AUTORIZACAO = "Autorização"

TIPOS_DOC = ("nf", "recibo", "comprovante", "pedido_medico", "relatorio", "autorizacao")
CAMPOS = ("paciente", "prestador", "valor", "doc_prestador", "conselho", "especialidade")
ITENS = frozenset(TIPOS_DOC) | frozenset(CAMPOS) | {"data"}
PORTOES = frozenset({"nf", "autorizacao"})
CASOS = ("consulta", "tratamento")
ROTULOS = {"nf": "nota fiscal", "recibo": "recibo", "comprovante": "comprovante", "pedido_medico": "pedido médico", "relatorio": "relatório médico",
           "autorizacao": "aprovação da operadora", "paciente": "paciente", "prestador": "prestador", "valor": "valor", "data": "data",
           "doc_prestador": "CPF/CNPJ do profissional", "conselho": "CRM/CRP", "especialidade": "especialidade"}

_SINONIMOS = {
    "nf": ("nf", "nfe", "nfse", "nf-e", "nfs-e", "nota fiscal", "nota fiscal de servico", "nota fiscal eletronica"),
    "recibo": ("recibo",),
    "comprovante": ("comprovante", "comprovante de pagamento", "comprovante de pix", "pix"),
    "pedido_medico": ("pedido medico", "pedido_medico", "pedido de exame", "solicitacao medica", "prescricao"),
    "relatorio": ("relatorio", "relatorio medico", "laudo medico"),
    "autorizacao": ("autorizacao", "aprovacao", "aprovacao da operadora", "autorizacao da operadora", "guia autorizada"),
}


def _chave(s) -> str:
    sem = "".join(c for c in unicodedata.normalize("NFD", str(s or "")) if unicodedata.category(c) != "Mn")
    return " ".join(sem.lower().replace("_", " ").split())


_POR_TEXTO = {_chave(t): k for k, ts in _SINONIMOS.items() for t in ts}


def tipo_do_documento(texto) -> str | None:
    """Chave do tipo (nf, recibo...) a partir do que a escuta ou o modelo escreveu; desconhecido = None (nunca adivinha)."""
    return _POR_TEXTO.get(_chave(texto))


def caso_valido(texto) -> str | None:
    c = _chave(texto)
    return c if c in CASOS else None


def e_de_reembolso(campos: dict) -> bool:
    """A mensagem de saúde da escuta é de reembolso (e não de exame)? Só com tipo de documento de reembolso ou `caso` informado;
    qualquer dúvida segue como exame (`gabi:saude-exame`), o comportamento de antes."""
    c = campos or {}
    return tipo_do_documento(c.get("documento")) is not None or caso_valido(c.get("caso")) is not None
