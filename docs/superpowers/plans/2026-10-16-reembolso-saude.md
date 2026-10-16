# Plano: reembolso de saúde no brain (D8)
Spec: `docs/superpowers/specs/2026-10-16-reembolso-saude-design.md`. TDD em cada tarefa (teste falhando, código, verde). Testes em `tests/reembolso_saude/`. Nunca nome, valor ou texto de saúde em `gabi.db`, log, aviso ou MCP (ADR-014).

- [x] **T1 Requisitos editáveis.** `seeds/reembolso-saude-requisitos.json`; `gabi/reembolso_saude/requisitos.py` (`carregar(con)`: `parametro` ou seed; validação; `RequisitosInvalidos`; `rotulo`).
- [x] **T2 Regras de dossiê (puras).** `gabi/reembolso_saude/dossies.py`: normalização, par, chave do dossiê, itens do documento, portões, `estado_inicial`, `reabrir`, `faltando`, `resumo`, `casar_credito`.
- [x] **T3 Classificação a partir do texto.** `gabi/reembolso_saude/classificar.py` (modelo falso; JSON validado; injeção vira dado; CPF mascarado) e `tipos.py` (sinônimos de tipo, `e_de_reembolso`).
- [x] **T4 Esquema.** Migração `0040_reembolso_saude.sql` (`reembolso_saude_doc`, `reembolso_saude_dossie`, `reembolso_saude_acao`) sem coluna de saúde; cofre: `gabi/reembolso_saude/cofre.py` (tabelas `reembolso_doc`, `reembolso_dossie`).
- [x] **T5 Rodada.** `gabi/reembolso_saude/rodada.py`: fontes (etiqueta nova, legadas, tipo Autorização), classificar, gravar no cofre, reabrir, crédito, pedido sem crédito, ações, projeção, etiquetas `gabi:reembolso-*`, avisos abriu/pronto/não reembolsável.
- [x] **T6 Lista de segunda.** `gabi/reembolso_saude/texto.py`: `montar_segunda`, aviso semanal (uma vez por semana, segunda >= 08h BRT); descrição dos avisos em `gabi/rotas/avisos.py`.
- [x] **T7 Programa e deploy.** `gabi/reembolso_saude/__main__.py` (trava, aviso `servico_falhou` sem chave, contagens), units `gabi-brain-reembolso-saude.{service,timer}`, `instalar.sh`, `tests/test_deploy.py`.
- [x] **T8 Escuta.** `gabi/escuta/destinos.py`: etiqueta `gabi:saude-reembolso` para documento de reembolso.
- [x] **T9 MCP.** `gabi/mcp/ferramentas_reembolso.py`: `reembolso_saude_pendentes`, `_dossie`, `_segunda`, `_pedi`, `_recebi`; escopos; `tools.gerar_hermes`.
- [x] **T10 API de leitura.** `gabi/rotas/reembolso_saude.py` (`GET /api/v1/reembolso-saude/dossies`, com nomes, só boss com grau total).
- [x] **T11 Documentação.** Regerar `docs/api.md` e `docs/openapi.json`; STATUS, runbook, BACKLOG (D8); marcar este plano; painel como Depois.
- [x] **T12 Verificação.** Testes focados e os de fechamento (`test_deploy`, `test_esquema`, `tests/mcp/test_servidor`, `test_docs_api`, `test_hermes`).
