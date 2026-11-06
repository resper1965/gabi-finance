# Hermes enxuto: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Desligar por configuração as skills, plugins e o toolset `todo` do Hermes que não servem à Gabi ou concorrem com o brain, e fixar a política "dado do Ricardo é do brain, capacidade genérica é do Hermes".

**Architecture:** Só configuração do Hermes (CLI `hermes plugins`, `hermes tools`, `hermes skills`), sem código do brain. Cada lote tem backup, verificação por comando e desfazer. Documentação (política, guia, BACKLOG) vai para o repositório do brain.

**Tech Stack:** CLI `hermes`, `~/.hermes/config.yaml`, Markdown. Sem pytest novo (não há código novo); a suíte existente do brain prova que nada mudou.

**Spec:** `docs/superpowers/specs/2026-11-06-hermes-enxuto-design.md`

## Global Constraints
- Nada é apagado: só desligar. Cada lote é reversível.
- Backup antes de qualquer mudança: `~/.hermes/config.yaml` e qualquer arquivo de estado que `hermes plugins`/`hermes skills` alterem (descobertos por comparação antes e depois).
- Skills que ficam (12): `gabi-brain`, `humanizer`, `maps`, `youtube-content`, `grounded-citations`, `blocked-page-recovery`, `arxiv`, `product-price-monitor`, `competitor-news-monitor`, `docx`, `xlsx`, `powerpoint`.
- Plugins que ficam: `telegram-platform`, `whatsapp-platform`, os de autenticação do painel (`basic`, `drain`, `nous`, `self-hosted`) e um provedor de web, de imagem e de vídeo em uso.
- Toolsets que ficam no Telegram e no WhatsApp: `clarify`, `connections`, `cronjob`, `image_gen`, `memory`, `session_search`, `skills`, `tts`, `vision`, `web`. Sai só `todo`.
- Segredos: não ler, não imprimir, não mexer (`auth.json`, tokens).
- Reiniciar `hermes-gateway` (`sudo`) e mandar `/new` nos dois canais são passos do Ricardo, um comando por vez.
- Qualquer mudança que não possa ser feita por comando (skills interativas) é do Ricardo, com a lista fechada deste plano.

## Review Focus
- Desligar um plugin do qual o Hermes depende (provedor de web ou imagem) quebra a busca ou a geração de imagem: testar `web` e `image_gen` depois do lote de plugins.
- O `hermes update` religa o que é embutido: conferir `hermes plugins list --enabled` e `hermes skills list --enabled-only` depois de cada update.
- Desligar `todo` não pode afetar as atividades do brain: testar "lembra de X amanhã" (cria atividade) depois do lote 1.
- A macro "o que você pode fazer?" continua respondendo (SOUL intacto).
- Rotinas existentes (`resumo-manha`, `continuidade` e as outras) continuam ativas: `hermes cron list` antes e depois deve ser idêntico.

---

### Task 1: Linha de base e backup

**Files:**
- Create: `~/hermes-enxuto-2026-11-06/` (pasta de snapshots, fora do repositório)

**Interfaces:**
- Produces: arquivos `config.yaml.antes`, `plugins-antes.json`, `skills-antes.txt`, `tools-antes.txt`, `cron-antes.txt` nessa pasta; os lotes seguintes comparam contra eles.

- [ ] **Step 1: Criar a pasta e copiar o config**
Run: `mkdir -p ~/hermes-enxuto-2026-11-06 && cp -p ~/.hermes/config.yaml ~/hermes-enxuto-2026-11-06/config.yaml.antes`
Expected: sem erro; arquivo existe.
- [ ] **Step 2: Gravar o estado atual**
Run: `hermes plugins list --json > ~/hermes-enxuto-2026-11-06/plugins-antes.json; hermes skills list > ~/hermes-enxuto-2026-11-06/skills-antes.txt; hermes tools list > ~/hermes-enxuto-2026-11-06/tools-antes.txt; hermes cron list > ~/hermes-enxuto-2026-11-06/cron-antes.txt`
Expected: quatro arquivos não vazios.
- [ ] **Step 3: Conferir contagens**
Run: `python3 -I -c "import json;d=json.load(open('/home/ricardo/hermes-enxuto-2026-11-06/plugins-antes.json'));print(len(d))"` e `hermes skills list --enabled-only | grep -c '│'`
Expected: 59 plugins; contagem de skills ligadas igual à de `skills-antes.txt`.

### Task 2: Lote 1, toolset `todo` desligado no Telegram e no WhatsApp

**Files:**
- Modify: `~/.hermes/config.yaml` (via CLI, não editar à mão)

**Interfaces:**
- Consumes: baseline da Task 1.

- [ ] **Step 1: Desligar**
Run: `hermes tools disable todo --platform telegram; hermes tools disable todo --platform whatsapp`
Expected: confirmação nas duas plataformas.
- [ ] **Step 2: Verificar**
Run: `python3 -I -c "import yaml;c=yaml.safe_load(open('/home/ricardo/.hermes/config.yaml'))['platform_toolsets'];print('todo' in c['telegram'],'todo' in c['whatsapp'])"`
Expected: `False False`.
- [ ] **Step 3: Teste do brain (Ricardo)** Reiniciar o gateway (`! sudo systemctl restart hermes-gateway`), `/new` nos dois canais, dizer "lembra de ligar pro contador amanhã às 10h". Expected: o Hermes cria atividade pelo brain (`atividade_criar`), confirmável em `hermes -z "chame atividade_listar"`; depois "esquece essa atividade" a cancela.

### Task 3: Lote 2, plugins de plataformas não usadas e `a2a`

**Files:**
- Modify: estado de plugins do Hermes (via CLI)

**Interfaces:**
- Consumes: `plugins-antes.json` (Task 1).

- [ ] **Step 1: Confirmar o `a2a` sem porta exposta**
Run: `ss -ltnp 2>/dev/null | grep -i hermes`
Expected: só 127.0.0.1 (painel 9119); registrar a saída. Se aparecer porta pública, parar e avisar o Ricardo.
- [ ] **Step 2: Confirmar se `email-platform` é usado**
Run: `grep -n -i 'email' ~/.hermes/config.yaml | grep -v '^#' | head` e `python3 -I -c "import yaml;print(list(yaml.safe_load(open('/home/ricardo/.hermes/config.yaml'))['platforms']))"`
Expected: se `email` não estiver em `platforms`, entra no lote; senão, fica.
- [ ] **Step 3: Desligar o lote**
Run, um por vez: `hermes plugins disable <nome>` para `buzz-platform dingtalk-platform discord-platform feishu-platform google_chat-platform irc-platform line-platform matrix-platform mattermost-platform ntfy-platform photon-platform raft-platform simplex-platform slack-platform sms-platform teams-platform wecom-platform a2a-platform` (mais `email-platform` se o Step 2 permitir).
Expected: cada um confirma "disabled".
- [ ] **Step 4: Verificar**
Run: `hermes plugins list --enabled --plain`
Expected: aparecem `telegram-platform`, `whatsapp-platform`, os de autenticação do painel e os provedores de web, imagem e vídeo; nenhum dos desligados.
- [ ] **Step 5: Diff do estado** Run: `diff ~/hermes-enxuto-2026-11-06/config.yaml.antes ~/.hermes/config.yaml`. Expected: mostra o que mudou (guardar para o desfazer e para descobrir o arquivo de estado a incluir no backup).
- [ ] **Step 6: Teste (Ricardo)** Reiniciar o gateway e `/new`; mandar "pesquise na web o preço do dólar hoje" e "gere uma imagem de um gato". Expected: as duas funcionam. Se alguma falhar, religar o último plugin desligado (`hermes plugins enable <nome>`) e investigar.

### Task 4: Lote 3, skills do grupo 2 (não servem à Gabi, 33)

**Files:**
- Modify: estado de skills do Hermes

**Interfaces:**
- Consumes: `skills-antes.txt`.
- Produces: o mecanismo de desligar skill (comando não interativo, se existir) usado na Task 5.

- [ ] **Step 1: Descobrir o mecanismo.** Run: `hermes skills config --help; hermes skills --help | grep -i -E 'disable|enable'`. Expected: se houver forma não interativa, usar. Senão, o Ricardo roda `! hermes skills config` e desliga a lista abaixo; eu verifico depois.
- [ ] **Step 2: Desligar:** `apple-notes apple-reminders findmy imessage`; as 12 de `software-development` (`codebase-inspection dogfood github hermes-agent-skill-authoring inspecting-hermes-desktop-dom node-inspect-debugger python-debugpy requesting-code-review simplify-code spike systematic-debugging test-driven-development`); as 9 de `creative` (`architecture-diagram ascii-video baoyu-infographic claude-design design-md manim-video p5js popular-web-designs songwriting-and-ai-music`); as 5 de `autonomous-ai-agents` (`claude-code codex computer-use hermes-agent opencode`); `xurl songsee gif-search`.
- [ ] **Step 3: Verificar**
Run: `hermes skills list --enabled-only | grep -c '│'`
Expected: 33 a menos que em `skills-antes.txt` (o número exato da linha de base menos 33).
- [ ] **Step 4: Teste (Ricardo)** `/new` e "o que você pode fazer?". Expected: a macro responde igual ao guia de uma tela.

### Task 5: Lote 4, skills do grupo 1 (concorrem com o brain, 14)

**Files:**
- Modify: estado de skills do Hermes

**Interfaces:**
- Consumes: mecanismo da Task 4.

- [ ] **Step 1: Desligar:** `google-workspace himalaya email-inbox-triage notion box airtable obsidian llm-wiki pdf meeting-action-items document-to-action-items weekly-review-planning teams-meeting-pipeline sdlc-review`.
- [ ] **Step 2: Verificar**
Run: `hermes skills list --enabled-only | grep -c '│'`
Expected: 12 skills ligadas, exatamente as listadas em Global Constraints.
- [ ] **Step 3: Teste (Ricardo)** `/new`; "saldo?", "que avisos tenho?" e mandar um PDF. Expected: saldo e avisos pelo brain; o PDF vai ao Paperless com a resposta de uma linha (SOUL).

### Task 6: Sobreposições S1, S3 e S4 (só leitura e decisão)

**Files:**
- Create: `docs/superpowers/plans/2026-11-06-hermes-enxuto-achados.md` (registro dos achados, no repositório)

**Interfaces:**
- Consumes: saídas das Tasks 1 a 3.

- [ ] **Step 1: S1, memória.** Run: `ls -la ~/.hermes/memories && wc -c ~/.hermes/memories/*`. Ler o conteúdo; listar fatos de pessoa ou dinheiro que deviam estar no brain. Propor ao Ricardo a migração de cada um; não migrar sem o "sim".
- [ ] **Step 2: S3, a2a.** Registrar a saída do Step 1 da Task 3 como evidência.
- [ ] **Step 3: S4, rotinas.** Run: `hermes cron list` e comparar com `cron-antes.txt`; mostrar ao Ricardo as duas criadas em 06/11 às 04:28 (nome, agenda, destino). Manter ou remover só por decisão dele (`hermes cron pause|remove <id>`).
- [ ] **Step 4: S2, transcrição.** Pedir ao Ricardo um áudio curto no Telegram; ler a mensagem em `~/.hermes/state.db` (leitura) e registrar se o Hermes já recebe o texto transcrito. A decisão sobre o brain parar de transcrever fica registrada como recomendação nos achados, sem mudar o brain.
- [ ] **Step 5: Escrever os achados e commit.** `git add docs/superpowers/plans/2026-11-06-hermes-enxuto-achados.md && git commit -m "docs: achados do Hermes enxuto (S1 a S4)"` (com a atribuição padrão).

### Task 7: Documentação e política

**Files:**
- Modify: `docs/PLANO-DEFINITIVO.md` (seção curta "Hermes × brain"), `docs/BACKLOG.md` (item "Hermes enxuto"), `deploy/hermes/SOUL.md` (só se o guia mudar)
- Modify: `~/COMO-USAR-HERMES.md` e `~/COMO-USAR-HERMES-CURTO.txt` (fora do repositório), acrescentando o que o Hermes faz sozinho (web, imagem, voz, mapas, rotinas, pesquisa)
- Test: `tests/mcp/test_confiabilidade.py` (regras do SOUL; não mudar o teste)

**Interfaces:**
- Consumes: política da seção 3 da spec, copiada literalmente.

- [ ] **Step 1: Seção "Hermes × brain" no `docs/PLANO-DEFINITIVO.md`** com a regra e as 4 perguntas do critério (texto da spec, seção 3).
- [ ] **Step 2: Item no `docs/BACKLOG.md`** "HE4 Hermes enxuto (spec 06/11)": dono R+C, status conforme as Tasks 2 a 6.
- [ ] **Step 3: Atualizar os dois guias** (`~/COMO-USAR-HERMES.md` e `~/COMO-USAR-HERMES-CURTO.txt`) com uma seção "O que ele faz sozinho"; sem a palavra "reembolso" fora das linhas permitidas se o texto for ao SOUL.
- [ ] **Step 4: Se o resumo do SOUL mudou, rodar a suíte**
Run: `cd ~/gabi-brain && .venv/bin/python -m pytest tests/mcp -q`
Expected: `280 passed` (ou mais), sem falhas. Rodar em segundo plano, leva cerca de 2 minutos.
- [ ] **Step 5: Commit**
```bash
git add docs/PLANO-DEFINITIVO.md docs/BACKLOG.md deploy/hermes/SOUL.md
git commit -m "docs: política Hermes x brain e item HE4"
```

### Task 8: Verificação final (com o Ricardo)

**Interfaces:**
- Consumes: tudo acima.

- [ ] **Step 1: Estado final**
Run: `hermes plugins list --enabled --plain; hermes skills list --enabled-only | grep -c '│'; hermes tools list | grep -i todo; hermes cron list | diff - ~/hermes-enxuto-2026-11-06/cron-antes.txt`
Expected: plugins e skills como em Global Constraints; `todo` desligado para Telegram e WhatsApp; rotinas iguais ao antes, exceto decisões do Ricardo na Task 6.
- [ ] **Step 2: Conversa de teste** (depois de reiniciar o gateway e `/new`): "o que você pode fazer?", "saldo?", uma pergunta com web e um pedido de projeto ("como está o projeto X?"). Expected: todas respondem.
- [ ] **Step 3: Registrar no BACKLOG** o resultado e as datas; fechar HE4 com a evidência (comando e saída).
- [ ] **Desfazer tudo:** `cp -p ~/hermes-enxuto-2026-11-06/config.yaml.antes ~/.hermes/config.yaml`, religar plugins com `hermes plugins enable <nome>` e skills pelo mesmo mecanismo da Task 4, reiniciar o gateway e `/new`.
