#!/usr/bin/env python3
"""Virada do gabi-finance: EDITA o SOUL do Hermes (não o substitui). Roda como o usuário do Hermes, só com a biblioteca padrão.
1. Guarda o SOUL atual em SOUL.md.bak-antes-finance-<data> (só se for mudar algo; nunca sobrescreve um backup que já existe).
2. Dentro de crases, troca as 28 ferramentas só de dinheiro (sem prefixo ou com `mcp__gabi_brain__`) por `mcp__gabi_finance__<nome>`.
   As que existem nos dois servidores (avisos_abertos, resumo_manha, decisoes_*, decisao_responder) não mudam.
3. Acrescenta uma seção curta "Dinheiro" (uma vez só).
Idempotente: rodar de novo não muda nada e não cria outro backup. Não reinicia o gateway.
Uso: python3 editar_soul.py [--soul ~/.hermes/SOUL.md] [--data AAAA-MM-DD-HHMM]"""
import argparse
import datetime as dt
import re
import shutil
import sys
from pathlib import Path

# mesma lista de tools.gerar_hermes.tirar_do_brain() (testada); aqui fica escrita porque o script roda fora do repositório
DINHEIRO = (
    "agenda_financeira", "assinatura_marcar", "assinaturas_listar", "classificar_lancamento", "despesa_criar", "despesa_encerrar",
    "despesa_excluir", "despesa_mes", "despesa_mudar", "despesas_listar", "despesas_por_empresa", "empresas_listar", "fechamento_dia",
    "financeiro_a_receber", "financeiro_cancelar_a_receber", "financeiro_contas_a_pagar", "financeiro_indicar_gastador",
    "financeiro_lancamentos", "financeiro_marcar_gasto", "financeiro_marcar_reembolso", "financeiro_para_onde_vai", "financeiro_previsao",
    "financeiro_recorrentes", "financeiro_registrar_a_receber", "financeiro_saldo", "olhar_a_frente", "regras_listar", "regras_sugerir",
)
PREFIXO = "mcp__gabi_finance__"
MARCA = "Dinheiro (gabi_finance):"
SECAO = (
    f"\n{MARCA}\n"
    "- Dinheiro: `mcp__gabi_finance__*`. `avisos_abertos`, `resumo_manha`, `decisoes_*` existem nos dois: dinheiro vem do gabi_finance; "
    "agenda, e-mail, família e projetos do gabi_brain (que com GABI_SEM_FINANCEIRO=1 não traz mais dinheiro). "
    "Resumo da manhã: chame os dois e junte, dinheiro primeiro.\n"
)
_NOME = re.compile(r"^(?:mcp__gabi_brain__)?(" + "|".join(sorted(DINHEIRO, key=len, reverse=True)) + r")(?=$|\()")


def editar(texto: str) -> tuple[str, int]:
    """-> (texto novo, quantos nomes ganharam o prefixo)."""
    trocas = 0

    def trecho(m: re.Match) -> str:
        nonlocal trocas
        novo, n = _NOME.subn(lambda x: PREFIXO + x.group(1), m.group(1), count=1)
        trocas += n
        return "`" + novo + "`"

    novo = re.sub(r"`([^`\n]+)`", trecho, texto)
    if MARCA not in novo:
        novo = novo.rstrip("\n") + "\n" + SECAO
    return novo, trocas


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--soul", type=Path, default=Path.home() / ".hermes" / "SOUL.md")
    ap.add_argument("--data", default=dt.datetime.now().strftime("%Y-%m-%d-%H%M"))
    a = ap.parse_args(argv)
    if not a.soul.is_file():
        print(f"não achei {a.soul}", file=sys.stderr)
        return 1
    antes = a.soul.read_text(encoding="utf-8")
    depois, trocas = editar(antes)
    if depois == antes:
        print("SOUL já editado: nada a mudar")
        return 0
    backup = a.soul.with_name(f"{a.soul.name}.bak-antes-finance-{a.data}")
    if backup.exists():
        print(f"o backup {backup} já existe: use outra --data", file=sys.stderr)
        return 1
    shutil.copy2(a.soul, backup)
    a.soul.write_text(depois, encoding="utf-8")
    print(f"backup: {backup}")
    print(f"SOUL editado: {trocas} nomes ganharam o prefixo {PREFIXO}" + ("" if MARCA in antes else f"; seção '{MARCA}' acrescentada"))
    print("Falta reiniciar o gateway: sudo systemctl restart hermes-gateway")
    return 0


if __name__ == "__main__":
    sys.exit(main())
