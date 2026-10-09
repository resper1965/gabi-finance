"""Aplica `seeds/donos-padrao.json`: donos coletivos (Casa, Pets), quem responde por qual filha, dono padrão por categoria,
quem usa cada cartão/conta, o padrão por compromisso e parâmetros (ex.: categorias de assinatura). Dados em arquivo editável (R6). Idempotente; nunca sobrescreve o que o
Ricardo já escolheu (vira `conflitos`). Uso: python -m tools.semear_donos [--arquivo CAMINHO] [--banco CAMINHO]."""
import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from gabi.db import conectar, transacao
from gabi.rotas.cadastros import _auditar


@dataclass
class Resumo:
    aplicados: int = 0
    conflitos: list[str] = field(default_factory=list)
    nao_encontrados: list[str] = field(default_factory=list)


def _pessoa(con, pid) -> bool:
    return isinstance(pid, str) and con.execute("select 1 from pessoa where id=?", (pid,)).fetchone() is not None


def _validar(con, d: dict, coletivos: set) -> None:
    """Tudo antes de gravar: dono que não é pessoa (nem coletivo do próprio arquivo) derruba o arquivo inteiro."""
    donos = [p for v in d.get("contas", {}).values() for p in v] + list(d.get("categorias", {}).values()) + \
            [p for v in d.get("responsaveis", {}).values() for p in v] + [c.get("para_quem") for c in d.get("compromissos", {}).values() if c.get("para_quem")]
    ruins = [p for p in donos if p not in coletivos and not _pessoa(con, p)]
    if ruins:
        raise ValueError(f"dono(s) que não são pessoas cadastradas: {sorted(set(map(str, ruins)))}")


def aplicar(con, arquivo: Path, quem: str) -> Resumo:
    d = json.loads(Path(arquivo).read_text(encoding="utf-8"))
    r = Resumo()
    coletivos = {c["id"] for c in d.get("coletivos", [])}
    _validar(con, d, coletivos)
    with transacao(con):
        for c in d.get("coletivos", []):
            if con.execute("select 1 from pessoa where id=?", (c["id"],)).fetchone() is None:
                con.execute("insert into pessoa(id, nome, papel, dados, origem) values (?,?,'coletivo','{}','manual')", (c["id"], c["nome"]))
                _auditar(con, quem, "pessoas", c["id"], "criada")
                r.aplicados += 1
        for pid, filhas in d.get("responsaveis", {}).items():
            linha = con.execute("select dados from pessoa where id=?", (pid,)).fetchone()
            if linha is None:
                r.nao_encontrados.append(f"pessoa {pid}")
                continue
            dados = json.loads(linha["dados"] or "{}")
            if dados.get("responsavel_por") not in (None, filhas):
                r.conflitos.append(f"pessoa {pid}")
            elif dados.get("responsavel_por") != filhas or dados.get("beneficiario") is not False:
                dados.update({"responsavel_por": filhas, "beneficiario": False})
                con.execute("update pessoa set dados=? where id=?", (json.dumps(dados, ensure_ascii=False), pid))
                _auditar(con, quem, "pessoas", pid, "alterada")
                r.aplicados += 1
        for nome, dono in d.get("categorias", {}).items():
            linha = con.execute("select id, dono_padrao from categoria where nome=? and excluido_em is null", (nome,)).fetchone()
            if linha is None:
                r.nao_encontrados.append(f"categoria {nome}")
            elif linha["dono_padrao"] not in (None, dono):
                r.conflitos.append(f"categoria {nome}")
            elif linha["dono_padrao"] is None:
                con.execute("update categoria set dono_padrao=? where id=?", (dono, linha["id"]))
                _auditar(con, quem, "categorias", linha["id"], "alterada")
                r.aplicados += 1
        for apelido, usuarios in d.get("contas", {}).items():
            linha = next((x for x in con.execute("select id, usuarios, apelido from conta where excluido_em is null")
                          if " ".join((x["apelido"] or "").split()).upper() == " ".join(apelido.split()).upper()), None)
            if linha is None:
                r.nao_encontrados.append(f"conta {apelido}")
            elif linha["usuarios"] and json.loads(linha["usuarios"]) != usuarios:
                r.conflitos.append(f"conta {apelido}")
            elif not linha["usuarios"]:
                con.execute("update conta set usuarios=? where id=?", (json.dumps(usuarios, ensure_ascii=False), linha["id"]))
                _auditar(con, quem, "contas", linha["id"], "alterada")
                r.aplicados += 1
        for linha_id, padrao in d.get("compromissos", {}).items():
            if con.execute("select 1 from compromisso_linha where id=? and excluido_em is null", (linha_id,)).fetchone() is None:
                r.nao_encontrados.append(f"compromisso {linha_id}")
                continue
            atual = con.execute("select para_quem_id from compromisso_padrao where linha_id=?", (linha_id,)).fetchone()
            if atual is None:
                con.execute("insert into compromisso_padrao(linha_id, para_quem_id) values (?,?)", (linha_id, padrao.get("para_quem")))
                _auditar(con, quem, "compromissos", linha_id, "alterada")
                r.aplicados += 1
            elif atual["para_quem_id"] not in (None, padrao.get("para_quem")):
                r.conflitos.append(f"compromisso {linha_id}")
        for chave, valor in d.get("parametros", {}).items():
            atual = con.execute("select valor from parametro where chave=?", (chave,)).fetchone()
            if atual is None:
                con.execute("insert into parametro(chave, valor) values (?,?)", (chave, json.dumps(valor, ensure_ascii=False)))
                _auditar(con, quem, "parametros", chave, "alterada")
                r.aplicados += 1
            elif json.loads(atual["valor"]) != valor:
                r.conflitos.append(f"parametro {chave}")
    return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--arquivo", default=str(Path(__file__).resolve().parent.parent / "seeds" / "donos-padrao.json"))
    ap.add_argument("--banco", default="/var/lib/gabi-brain/gabi.db")
    a = ap.parse_args()
    res = aplicar(conectar(a.banco), Path(a.arquivo), "claude (a pedido do Ricardo: donos padrão)")
    print(f"aplicados={res.aplicados} conflitos={res.conflitos} nao_encontrados={res.nao_encontrados}")
    sys.exit(0)
