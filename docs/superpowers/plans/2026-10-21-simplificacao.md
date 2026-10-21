# Simplificação do gabi.brain — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cortar escuta, saúde, Trabalho e cobrança/reembolso PJ, aplicar sozinho o "para quem" certeiro e tornar a conferência de saldo informativa, sem perder dado nem funcionalidade usada.

**Architecture:** Primeiro mover para fora dos módulos condenados o que o resto usa (contatos, helpers de modelo, Hoje, Agenda), com a suíte verde; depois cortar módulo por módulo (código, rotas, telas, MCP, units, testes); por fim as duas mudanças de comportamento, uma migração que só remove tabelas vazias, e docs.

**Tech Stack:** Python 3 + FastAPI + SQLite (migrações SQL em `migrations/`), pytest; painel React + TypeScript (Vite, vitest); systemd.

**Spec:** `docs/superpowers/specs/2026-10-21-simplificacao-design.md`

## Global Constraints
- Branch `feat/simplificacao` a partir da `main` (`a82b09b`); um commit por tarefa; mensagens terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Só tabelas **vazias** saem; `escuta_remetente`, `caixa_email`, `memoria` ficam com o dado.
- Não tocar em `/etc/gabi/*`, `saude.enc`, chaves, nem no banco de produção (só leitura). Nada de `sudo` sem autorização do Ricardo.
- R2 intacta: nada novo envia para fora.
- Suíte: `.venv/bin/python -m pytest -q` (ler o resumo `N passed`, não o código de saída); painel: `cd painel && npx vitest run && npm run build`.
- Ao remover arquivo, remover seus testes e todo `import`/referência (grep pelo nome do módulo deve dar vazio fora de `docs/historico`).
- Textos de commit e docs em português.

## Review Focus
1. Import pendente de módulo removido em caminho que só roda em produção (unit systemd, `python -m`, import tardio dentro de função) — `tests/test_deploy.py` deve importar cada `-m` das units restantes (Task 12).
2. Painel com link/aba para tela removida (menu, `rotaParaTela`, `App.tsx`) — vitest de navegação confere que cada aba do `GRUPOS` tem componente (Task 6/12).
3. "Para quem" certeiro sobrescrevendo pessoa já escolhida (`voce`, `regra`, `fonte`) — teste explícito (Task 9).
4. Migração removendo tabela com dado — teste que semeia linha numa tabela legada e confirma que ela sobrevive (Task 11).
5. `envelope`/`dados_ate` ainda lendo fontes removidas (`exames`, `reembolso-saude`, `trabalho`, `escuta`, `comprovantes-paperless`) e marcando "desatualizado" — teste do envelope sem essas fontes (Task 12).

---

### Task 1: Branch e linha de base
- [ ] `git switch -c feat/simplificacao`
- [ ] Rodar a suíte e o painel; anotar `N passed` e falhas pré-existentes em `docs/superpowers/plans/2026-10-21-simplificacao-baseline.txt` (não commitar se tudo verde; commitar se houver falha pré-existente, para o revisor saber).

### Task 2: Mover contatos, telefone e helpers de modelo para fora da escuta
**Files:**
- Create: `gabi/contatos/__init__.py`, `gabi/contatos/telefone.py`, `gabi/correio/modelo.py`, `gabi/rotas/contatos.py`
- Move (`git mv`): `gabi/escuta/{contatos,contatos_propostas,contatos_gravar,interacao}.py` → `gabi/contatos/`; testes de contatos de `tests/escuta/` → `tests/contatos/`
- Modify: todos os importadores listados na spec §1; `deploy/gabi-brain-contatos.service`; `gabi/api.py` (registrar `rotas_contatos`); `painel/src/telas/ContatosPropostas.tsx` e `Cadastros.tsx` (URLs)

**Interfaces (Produces):**
- `gabi.contatos.telefone.normalizar_telefone(numero: str) -> str | None` (corpo atual de `escuta/caixa.py`)
- `gabi.correio.modelo`: `Falha`, `_chamar`, `ModeloComCusto`, `cliente_da_ponte` (corpos atuais, mesma assinatura); `escuta/classificar.py` e `escuta/__main__.py` passam a importar daqui até a Task 4 apagá-los
- Rotas: `/api/v1/escuta/contatos/...` → `/api/v1/contatos/...` (mesmos sufixos, métodos e respostas)
- Unit: `ExecStart=... -m gabi.contatos.contatos`, `ExecStartPost=... -m gabi.contatos.contatos_gravar`

- [ ] Fazer os movimentos e ajustar imports (só mover; nenhuma mudança de lógica).
- [ ] Ajustar `tests/test_deploy.py` para o novo `-m` e os testes de rota para o prefixo novo.
- [ ] Suíte e painel verdes, mesmo `N passed` da linha de base (± testes movidos).
- [ ] Commit `refactor: contatos e helpers de modelo saem de gabi/escuta`.

### Task 3: Mover Hoje, Agenda e ferramentas do dia para fora do Trabalho
**Files:**
- Modify: `gabi/hoje.py` (recebe `hoje()` e `_dinheiro()` de `trabalho/hoje.py`, sem `emails_importantes`, `_recorte_email` e filtro por frente), `gabi/agenda/consulta.py` (recebe `class Conflito`), `gabi/rotas/agenda.py` (recebe `GET /api/v1/agenda`), nova rota `GET /api/v1/hoje` em `gabi/rotas/agenda.py` ou módulo de rotas existente que não seja `trabalho.py`
- Move: `gabi/mcp/ferramentas_trab.py` → `gabi/mcp/ferramentas_dia.py` com só `resumo_manha`, `agenda_listar`, `email_listar` (escopo `trabalho` mantido para não invalidar tokens)
- Test: `tests/test_hoje.py`, `tests/mcp/test_trabalho.py` → `tests/mcp/test_dia.py`

**Interfaces (Produces):** `gabi.hoje.hoje(con, agora, filtro="all", *, painel=False) -> dict` sem a chave `emails_importantes`; filtro aceita `'all'` ou id de empresa. `gabi.agenda.consulta.Conflito(evento_a: int, evento_b: int, sugestao_inicio: str)`.

- [ ] Teste: `test_hoje_nao_le_item_email` — com `item_email` inexistente (drop na fixture), `hoje(con, agora)` responde com `prioridades`, `agenda`, `correio_importantes`, `dinheiro`.
- [ ] Implementar os movimentos; `Hoje.tsx` deixa de ler `emails_importantes` e o filtro por frente.
- [ ] Suíte e painel verdes. Commit `refactor: Hoje, Agenda e resumo da manhã saem de gabi/trabalho`.

### Task 4: Cortar a escuta
**Files:** apagar `gabi/escuta/`, rotas restantes de `gabi/rotas/escuta.py`, `painel/src/telas/Escuta.tsx` e a aba `escuta` de `navegacao.ts`, `ouvinte/`, `tools/comparar_escuta.py`, `deploy/gabi-brain-escuta.{service,timer,path}`, `deploy/escuta-ouvinte.service`, tipos `escuta_*` em `gabi/avisos.py`, `tests/escuta/`, `tests/rotas/test_escuta.py`, `tests/test_comparar_escuta.py`; em `deploy/instalar.sh` as linhas 15-36 da escuta/ouvinte e as units da lista de cópia e os comentários 67-70.
- [ ] Remover; `grep -rn "gabi.escuta\|escuta_msg\|escuta_grupo\|ouvinte" gabi painel/src tools deploy tests` só pode achar `escuta_remetente` em migração antiga.
- [ ] Suíte e painel verdes. Commit `feat!: remove a escuta do WhatsApp (nunca registrou mensagem; ADR-023)`.

### Task 5: Cortar a saúde
**Files:** apagar `gabi/familia/`, `gabi/reembolso_saude/`, `gabi/visao_pdf.py` (se `grep` mostrar que `fontes/openrouter.py` só o cita em comentário; se importar, manter), `gabi/rotas/familia.py`, `gabi/rotas/reembolso_saude.py`, `gabi/mcp/ferramentas_reembolso.py`, telas `Familia.tsx`, `FamiliaSaude.tsx`, `Reembolso.tsx` e a área `familia` de `navegacao.ts`, `api.py:68-69` e os `include_router` de família/reembolso, rotas e UI de liberação de sensível (`rotas/cadastros.py` `/liberacoes`, parte de `CadastrosCobranca.tsx`, `pessoas_dado` em `ferramentas_prop.py`), `deploy/gabi-brain-exames.*`, `deploy/gabi-brain-reembolso-saude.*`, `tools/medir_exames.py`, partes de saúde de `tools/gerar_amostras.py`, testes `tests/familia/`, `tests/reembolso_saude/`, `tests/test_saude_blindagem.py`, `tests/rotas/test_familia.py`, `tests/rotas/test_reembolso_saude.py`, `tests/mcp/test_reembolso_saude.py`; fontes `exames`/`reembolso-saude` em `gabi/envelope.py:22`.
- [ ] Remover; a rota `/api/saude` (saúde do sistema) continua e seu teste passa.
- [ ] Suíte e painel verdes. Commit `feat!: remove a saúde da família (descartada em 21/10; ADR-023)`.

### Task 6: Cortar o módulo Trabalho
**Files:** apagar `gabi/trabalho/`, `gabi/rotas/trabalho.py` (o que sobrou após a Task 3), telas `Trabalho/{Frentes,Mensagens,Contatos,Tarefas,Entregas}.tsx`, `CadastrosCaixas.tsx`, áreas `temas` e `tarefas` e a aba `emails` e `contatos` de `msgs` em `navegacao.ts`, `deploy/gabi-brain-trabalho.*`, partes do Trabalho em `tools/demo.py`, `tests/trabalho/`, `tests/rotas/test_trabalho.py`; `gabi/envelope.py:64` (`_em_uso(con, "caixa_email")`) e a fonte `trabalho` do envelope.
- [ ] Teste (vitest, `painel/src/navegacao.test.ts` ou o existente): cada `[area, aba]` de `GRUPOS` tem tela registrada em `App.tsx`.
- [ ] Remover. Suíte e painel verdes. Commit `feat!: remove o módulo Trabalho legado (Hoje e Agenda preservados; ADR-023)`.

### Task 7: Cortar cobrança/reembolso PJ e criar `despesas_por_empresa`
**Files:**
- Delete: `gabi/cobrar/{reembolso,cobranca,lote_nibo,comprovantes,ingestao,extrator,pedidos}.py`, `gabi/dinheiro/cobranca_atraso.py`, as rotas correspondentes em `gabi/rotas/cobrar.py`, telas `Cobrar/{Reembolsos,Comprovantes,EmailCobranca}.tsx`, `Caixa/Pedidos.tsx` e suas abas, parte "pode pedir" de `CadastrosCobranca.tsx`, ferramentas MCP `cobranca_rascunho`, `reembolsos_listar`, `reembolsos_preparar_email`, `pedidos_registrar`, `pedidos_estado`, `deploy/gabi-brain-comprovantes.*`, testes correspondentes (`tests/cobrar/`, `tests/rotas/test_cobrar_api.py`).
- Create: `gabi/dinheiro/despesas_empresa.py`; ferramenta em `gabi/mcp/servidor.py`
- Test: `tests/dinheiro/test_despesas_empresa.py`, `tests/mcp/test_servidor.py`

**Interfaces (Produces):** `despesas_por_empresa(con, mes: str) -> list[dict]` — `mes` = `"AAAA-MM"`; cada item `{"empresa_id", "empresa", "total_centavos", "itens": [{"lancamento_id", "data", "descricao", "valor_centavos"}]}`, só `valor_centavos < 0` (valor devolvido positivo), `empresa_id` não nulo, `conta.pj = 0`, conta não excluída; ordenado por total decrescente. MCP `despesas_por_empresa(mes: str | None = None)` (padrão: mês corrente no fuso da agenda), escopo `fin`, valores formatados como as demais ferramentas `fin`.
- [ ] Testes: agrupa por empresa; ignora conta PJ, entrada (valor > 0), lançamento sem empresa e mês diferente; `mes` inválido → `ValueError`.
- [ ] Implementar, remover o resto. Suíte e painel verdes. Commit `feat!: troca cobrança/reembolso PJ por despesas_por_empresa (ADR-023)`.

### Task 8: Limpezas pequenas
**Files:** apagar `gabi/dinheiro/perfil.py`, `gabi/dinheiro/condicao.py` (e o uso: `regras.py`, `classificar.py:_regras_ativas` passa a devolver `(padrao, acao)`; a coluna `regra.condicao` é ignorada), `painel/src/telas/Configuracao.tsx`, `gabi/rotas/setup.py`, a aba `setup`; em `gabi/mcp/` remover `hoje_resumo`, `frentes_listar`, `frentes_itens`, `contatos_em_aberto`, `tarefas_propor`, `financeiro_vazamentos`, `financeiro_rumo`, `decisoes_abertas`, `decisao_responder`, `avisos_pendentes`, `avisos_confirmar_entrega` (o que ainda existir após as Tasks 3-7; `ferramentas_dec.py` sai se ficar vazio); testes correspondentes.
- [ ] Teste: `ferramentas_do_token(todos os escopos)` devolve exatamente as 16 da spec §5.
- [ ] Rodar `tools/gerar_hermes.py` e commitar a saída regenerada, se houver arquivo versionado.
- [ ] Suíte e painel verdes. Commit `chore: remove código morto e ferramentas MCP sem uso (ADR-023)`.

### Task 9: "Para quem" certeiro
**Files:** Modify `gabi/dinheiro/classificar.py` (`_sugerir_por_cache` e `classificar`); Create `gabi/dinheiro/para_quem_fila.py`; chamar a fila uma vez de `gabi/dinheiro/rodar.py` (idempotente: só age sobre pendentes); Test `tests/dinheiro/test_para_quem_certeiro.py`

**Interfaces (Produces):** constante `MIN_DECISOES_CERTEIRO = 2` em `classificar.py`; `aplicar_fila_para_quem(con, agora_iso: str) -> int` (quantas aplicou).
- [ ] Testes:
  - `test_aplica_com_duas_decisoes_iguais`: 2 lançamentos do estabelecimento com `para_quem_id='louise', para_quem_origem='voce'`; o 3º, classificado, fica `para_quem_id='louise'`, `para_quem_origem='gabi'`, sem sugestão pendente, e há 1 linha em `decisao` com `quem='gabi (para quem certeiro)'`, `origem='classificacao'`.
  - `test_sugere_com_uma_decisao`: com 1 decisão anterior só, cria sugestão pendente e não preenche.
  - `test_nao_aplica_se_decisoes_divergem`.
  - `test_nao_sobrescreve`: lançamento com `para_quem_origem` em `voce`, `regra`, `fonte` não muda.
  - `test_categoria_continua_sugestao`.
  - `test_fila_aplica_pendentes`: sugestão `para_quem` pendente que passa no critério → lançamento preenchido (`gabi`), sugestão `aprovada`, `motivo` termina com "aplicada sozinha"; a que não passa continua `pendente`; segunda chamada devolve 0.
- [ ] Implementar. Suíte verde. Commit `feat: aplica sozinho o "para quem" certeiro (≥2 decisões iguais do Ricardo; ADR-023)`.

### Task 10: Conferência de saldo informativa
**Files:** Modify `gabi/dinheiro/conferencia.py` (fica só `_saldo_final` simples, `conferir`, `marcar_conferida`), `gabi/avisos.py:330-336`, `gabi/dinheiro/rodar.py` se necessário; Test `tests/dinheiro/test_conferencia.py`, `tests/test_avisos.py`, `tests/test_envelope.py`, `tests/test_aceite.py`

**Interfaces:** `conferir(con, rodada_id, conta_id, hoje) -> list[Conferencia]` grava **uma** linha `tipo='saldo_final'` por conta; `marcar_conferida(con, rodada_id) -> bool` = `status=='ok' and not erro`; constante `TOLERANCIA_SALDO = 1`. Novo tipo de aviso `saldo_divergente`, chave de deduplicação `(conta_id, dia)`, payload `{"conta_id", "conta", "diferenca_centavos", "detalhe"}`, gerado por `avisos.py` a partir das linhas `ok=0` da última rodada.
- [ ] Testes:
  - `test_rodada_ok_e_conferida_mesmo_com_divergencia`.
  - `test_rodada_com_erro_nao_e_conferida`.
  - `test_um_centavo_nao_diverge`; `test_cartao_sem_conferencia`.
  - `test_divergencia_gera_saldo_divergente_uma_vez_por_dia` (duas rodadas no mesmo dia → 1 aviso).
  - `test_rodada_parada_so_por_falha` (duas rodadas `ok` com divergência não geram `rodada_parada`; duas com `status='erro'` geram).
- [ ] Remover os testes das heurísticas que saíram (buraco, volume, subconjunto, dia-base, fatura).
- [ ] Implementar. Suíte verde. Commit `feat: conferência de saldo vira aviso e não trava o dados_ate (ADR-023)`.

### Task 11: Migração das tabelas vazias e do FTS
**Files:** Create `migrations/0075_simplificacao.sql`; Test `tests/test_esquema.py` (ou `tests/test_migracao_simplificacao.py`)
- [ ] Conteúdo: `drop table if exists` para `escuta_msg, escuta_grupo, exame_doc, reembolso_saude_acao, reembolso_saude_doc, reembolso_saude_dossie, edicao_externa, liberacao_sensivel, item_email, item_frente, frente, evento, tarefa, entrega, regra_expurgo, cobranca_item, cobranca, comprovante_vinculo, comprovante, reembolso_baixa, reembolso_item, reembolso, lote_nibo_item, lote_nibo, pedido, setup_passo` (filhas antes das mães); gatilhos `memoria_ai/ad/au` (conferir os nomes reais em `0001_base.sql`) e `drop table if exists memoria_fts`. Conferir no `0001`..`0074` se alguma view ou gatilho referencia essas tabelas e removê-los também.
- [ ] Testes: depois de migrar, nenhuma dessas tabelas existe; `escuta_remetente`, `caixa_email`, `memoria` existem e uma linha semeada antes da 0075 sobrevive; `insert into memoria` funciona sem o FTS.
- [ ] O banco-modelo do `tests/conftest.py` é regenerado (conferir como ele detecta migração nova). Suíte verde. Commit `feat: migração 0075 remove tabelas vazias e o FTS da memória (ADR-023)`.

### Task 12: Deploy, documentação e ADR-023
**Files:** `deploy/instalar.sh` (lista de units, `systemctl enable`, comentários; nenhum comando novo de apagar dado), `tests/test_deploy.py` (cada `-m gabi.X` das units existentes é importável), `gabi/envelope.py` (fontes esperadas sem `exames`, `reembolso-saude`, `trabalho`, `escuta`, `comprovantes-paperless`) e `tests/test_envelope.py` (Review Focus 5), `tools/gerar_docs_api.py` → `docs/api.md`, `docs/openapi.json`; `docs/adr/023-simplificacao.md`; notas em ADR-009, 014, 016, 018 e nas da escuta; `docs/BACKLOG.md`, `docs/STATUS.md`, `docs/ARQUITETURA.md` (tabelas legadas), `docs/runbook.md`; `git mv` de `docs/{PROGRESSO-GOAL,RELATORIO-2026-10-16,TRILHA,aceite-fase-2}.md`, `docs/design/` e specs/planos anteriores a 21/10 de `docs/superpowers/` para `docs/historico/`, corrigindo links quebrados (`grep -rn` pelos nomes movidos).
- [ ] ADR-023 com: contexto (uso medido em 21/10), decisões 1-3 da spec, tabelas legadas, flexibilização de R1 no "para quem", conferência informativa, o que fica para o Ricardo decidir (spec "Produção" item 5).
- [ ] Suíte, `test_docs_api` e painel verdes. Commit `docs: ADR-023 e documentos atualizados para a simplificação`.

### Task 13: Verificação final
- [ ] Suíte inteira e painel: anotar `N passed` (comparar com a linha de base: a queda deve corresponder aos testes removidos).
- [ ] `grep -rn "gabi\.\(escuta\|familia\|reembolso_saude\|trabalho\)\b" gabi tools deploy tests painel/src` vazio.
- [ ] `git diff --stat main` resumido para o Ricardo (linhas removidas/adicionadas).
- [ ] **Parar.** Produção (spec "Produção" 1-4) só com autorização explícita do Ricardo.
