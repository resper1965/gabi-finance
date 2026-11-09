# Plano: assistente proativo (ADR-037)
Spec: `docs/superpowers/specs/2026-11-09-assistente-proativo-design.md`. Execução inline, TDD, um commit por tarefa. Sem migração.

1. **olhar_a_frente** — `gabi/antecipar.py` + testes; bloco no `resumo_da_manha`.
2. **revisao_semana** — `gabi/revisao.py` + testes.
3. **preparar_reuniao** — `gabi/reuniao.py` + testes.
4. **promessas_candidatas** — `enviados_textos` em `google_email.py`, `graph_ness.py`, roteador e `PERMITIDOS`; função no MCP + testes.
5. **MCP** — `gabi/mcp/ferramentas_assistente.py` (4 ferramentas, escopos), registro no `servidor.py`, imunidade ao envelhecimento (`ENVELHECE`), teste de contagem.
6. **Hermes** — `tools/gerar_hermes.py` (75), SOUL (promessas, rascunho, revisão), `docs/fontes/hermes.md`.
7. **Docs** — ADR-037, runbook `#assistente`, BACKLOG (AS1), STATUS. Suíte inteira + ruff.
