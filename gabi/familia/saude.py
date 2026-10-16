"""Saúde em arquivo PRÓPRIO e criptografado (ADR-014), fora do banco principal. R5: a chave (32 bytes) vem de quem chama (arquivo de ambiente), nunca do repositório.
O arquivo inteiro é AES-256-GCM; o SQLite só existe em memória, enquanto o `with` está aberto. Sair do `with` sem erro grava (arquivo novo + rename, modo 0600);
com erro, descarta. Toda leitura entra no log `leitura`. Consome: identidade (Identidade) e o grau da matriz (quem chama passa)."""
import datetime as dt
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from gabi.identidade import Identidade

MAGICO = b"GSAUDE1\0"
ESQUEMA = """
create table if not exists exame(
  id integer primary key, pessoa_id text not null, marcador text not null, valor text not null, valor_num real, unidade text,
  em text not null, ref_min text, ref_max text, paperless_id integer, confirmado_por text not null, criado_em text not null,
  versao integer not null default 1, qualitativo integer not null default 0, observacao text, laboratorio text);
create index if not exists exame_serie on exame(pessoa_id, marcador, em);
create table if not exists proposta_exame(
  id integer primary key, paperless_id integer not null, pessoa_sugerida text, marcador text not null, valor text not null, unidade text,
  em text, ref_min text, ref_max text, estado text not null default 'proposta' check (estado in ('proposta','confirmada','rejeitada')), criado_em text not null,
  versao integer not null default 1, origem text, qualitativo integer not null default 0, observacao text);
create table if not exists leitura(id integer primary key, quando text not null, quem text not null, pessoa_id text, o_que text not null);
create table if not exists marcador_apelido(apelido text primary key, marcador text not null);
create table if not exists mensagem_saude(id integer primary key, de_pessoa text, recebida_em text not null, texto text not null);
"""
# Colunas acrescentadas no cofre v2: um cofre antigo ganha o que falta ao abrir (sem perder dado).
COLUNAS_V2 = {
    "exame": (("versao", "integer not null default 1"), ("qualitativo", "integer not null default 0"), ("observacao", "text"), ("laboratorio", "text")),
    "proposta_exame": (("versao", "integer not null default 1"), ("origem", "text"), ("qualitativo", "integer not null default 0"), ("observacao", "text")),
}


# Histórico: de cada documento só a versão mais recente da extração; em (pessoa, marcador, data) repetida entre documentos, a linha mais nova.
VISAO_ATUAL = """
create view if not exists exame_atual as
select * from exame e
where (e.paperless_id is null or e.versao = (select max(x.versao) from exame x where x.paperless_id = e.paperless_id))
  and e.id = (select max(y.id) from exame y where y.pessoa_id = e.pessoa_id and y.marcador = e.marcador and y.em = e.em
              and (y.paperless_id is null or y.versao = (select max(z.versao) from exame z where z.paperless_id = y.paperless_id)));
"""


def _migrar(con: sqlite3.Connection) -> None:
    """Idempotente: acrescenta as colunas da v2 que o cofre antigo não tem e cria a visão do histórico atual."""
    for tabela, colunas in COLUNAS_V2.items():
        tem = {r[1] for r in con.execute(f"pragma table_info({tabela})")}
        for nome, tipo in colunas:
            if nome not in tem:
                con.execute(f"alter table {tabela} add column {nome} {tipo}")
    con.executescript(VISAO_ATUAL)


class ChaveInvalida(Exception):
    """Chave errada ou arquivo adulterado."""


@dataclass(frozen=True)
class Ponto:
    em: dt.date
    valor: str
    unidade: str | None
    fora_da_faixa: bool


def _agora() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class Cofre:
    def __init__(self, caminho: Path, chave: bytes):
        if len(chave) != 32:
            raise ValueError("a chave da saúde tem 32 bytes")
        self.caminho, self._aes = Path(caminho), AESGCM(chave)
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row

    def __enter__(self) -> "Cofre":
        if self.caminho.exists():
            bruto = self.caminho.read_bytes()
            if not bruto.startswith(MAGICO):
                raise ChaveInvalida("arquivo de saúde inválido")
            try:
                dados = self._aes.decrypt(bruto[len(MAGICO):len(MAGICO) + 12], bruto[len(MAGICO) + 12:], MAGICO)
            except InvalidTag as e:
                raise ChaveInvalida("chave errada ou arquivo adulterado") from e
            self.con.deserialize(dados)
        self.con.executescript(ESQUEMA)
        _migrar(self.con)
        return self

    def __exit__(self, tipo, valor, tb) -> bool:
        try:
            if tipo is None:
                self.con.commit()
                self._gravar()
        finally:
            self.con.close()
        return False

    def _gravar(self) -> None:
        nonce = os.urandom(12)
        cifrado = MAGICO + nonce + self._aes.encrypt(nonce, self.con.serialize(), MAGICO)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.caminho.parent, prefix=".saude-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(cifrado)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.caminho)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def abrir_saude(caminho: Path, chave: bytes) -> Cofre:
    return Cofre(caminho, chave)


def _num(v: str) -> float | None:
    try:
        return float(v.replace(",", "."))
    except ValueError:
        return None


def _log(s: Cofre, quem: str, pessoa_id: str | None, o_que: str) -> None:
    s.con.execute("insert into leitura(quando, quem, pessoa_id, o_que) values (?,?,?,?)", (_agora(), quem, pessoa_id, o_que))


def registrar_exame(s: Cofre, pessoa_id: str, marcador: str, valor: str, unidade: str | None, em: dt.date,
                    referencia: tuple[str, str] | None, paperless_id: int | None, confirmado_por: str, *,
                    versao: int = 1, qualitativo: bool = False, observacao: str | None = None, laboratorio: str | None = None) -> int:
    """Só entra com a pessoa CONFIRMADA por alguém (`confirmado_por`): laudo de quem? é decisão do Ricardo, nunca do extrator."""
    if not confirmado_por or not confirmado_por.strip():
        raise ValueError("o exame só entra depois que alguém confirma de quem é o laudo")
    ref_min, ref_max = referencia if referencia else (None, None)
    return s.con.execute(
        "insert into exame(pessoa_id, marcador, valor, valor_num, unidade, em, ref_min, ref_max, paperless_id, confirmado_por, criado_em, versao, qualitativo, observacao, laboratorio) "
        "values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (pessoa_id, marcador, valor, _num(valor), unidade, em.isoformat(), ref_min, ref_max, paperless_id, confirmado_por, _agora(),
         versao, int(qualitativo), observacao, laboratorio)).lastrowid


def _fora(valor: str, ref_min: str | None, ref_max: str | None) -> bool:
    v = _num(valor)
    if v is None:
        return False
    lo, hi = (_num(ref_min) if ref_min else None), (_num(ref_max) if ref_max else None)
    return (lo is not None and v < lo) or (hi is not None and v > hi)


def serie(s: Cofre, pessoa_id: str, marcador: str, quem: str) -> list[Ponto]:
    _log(s, quem, pessoa_id, f"serie:{marcador}")
    return [Ponto(dt.date.fromisoformat(r["em"]), r["valor"], r["unidade"], _fora(r["valor"], r["ref_min"], r["ref_max"]))
            for r in s.con.execute("select * from exame_atual where pessoa_id=? and marcador=? and qualitativo=0 order by em, id", (pessoa_id, marcador))]


def resumo_para_consulta(s: Cofre, pessoa_id: str, quem: str) -> str:
    """Texto curto com o último valor de cada marcador da pessoa escolhida (e só dela)."""
    _log(s, quem, pessoa_id, "resumo")
    linhas = []
    for r in s.con.execute("select * from exame_atual e where pessoa_id=? and em=(select max(em) from exame_atual where pessoa_id=e.pessoa_id and marcador=e.marcador) "
                           "group by marcador order by marcador", (pessoa_id,)):
        faixa = f" (ref. {r['ref_min']} a {r['ref_max']})" if r["ref_min"] and r["ref_max"] else ""
        marca = " ← fora da faixa" if _fora(r["valor"], r["ref_min"], r["ref_max"]) else ""
        linhas.append(f"- {r['marcador']}: {r['valor']} {r['unidade'] or ''}{faixa}, em {r['em']}{marca}".replace("  ", " "))
    return "\n".join(linhas) or "Sem exames registrados."


def pode_ver(ident: Identidade, grau: str, pessoa_id: str) -> bool:
    """boss com grau total vê todos; grau parcial = só a PRÓPRIA pessoa; 'nenhum' nunca."""
    if grau == "total":
        return True
    return grau == "parcial" and ident.pessoa_id is not None and ident.pessoa_id == pessoa_id


def marcadores(s: Cofre, pessoa_id: str, quem: str) -> list[dict]:
    """Último valor de cada marcador da pessoa (para a tela Família)."""
    _log(s, quem, pessoa_id, "lista")
    return [{"marcador": r["marcador"], "valor": r["valor"], "unidade": r["unidade"], "em": r["em"], "fora_da_faixa": _fora(r["valor"], r["ref_min"], r["ref_max"]),
             "qualitativo": bool(r["qualitativo"]), "ref_min": r["ref_min"], "ref_max": r["ref_max"]}
            for r in s.con.execute("select * from exame_atual e where pessoa_id=? and em=(select max(em) from exame_atual where pessoa_id=e.pessoa_id and marcador=e.marcador) "
                                   "group by marcador order by marcador", (pessoa_id,))]
