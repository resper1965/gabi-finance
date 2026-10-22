# Desligar o OpenClaw Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aposentar por completo o OpenClaw, sem perder nenhuma função que ele cumpria, deixando Hermes + gabi.brain como únicos donos.

**Architecture:** Plano operacional (units systemd, crons do Hermes, brain), não código novo. Cada tarefa é reversível até a Task 8; a remoção só roda quando o gate (Task 7) passa. "Teste" = comando de verificação com saída esperada.

**Tech Stack:** systemd, Hermes (`hermes cron`), gabi.brain (SQLite, MCP), shell.

**Spec:** `~/PLANO-DESLIGAR-OPENCLAW.md` (19/10/2026) e `docs/PLANO-DEFINITIVO.md` (OpenClaw sai por completo, sem plano B); gate H8 em `docs/BACKLOG.md`.

## Global Constraints

- Não mexer em segredos nem imprimir conteúdo de `/etc/gabi/*.env` (`gateway.env` inclusive); usar `grep -l`/`-q`, nunca mostrar valores.
- Nada de `terminal`/`file` liberados nos canais do Hermes.
- Não apagar o usuário `gabi` (containers redis/postgres rodam com ele); só a pasta `.openclaw`.
- Antes de editar qualquer unit/config, copiar para `*.bak-antes-<tarefa>-2026-10-19`.
- Dado de saúde: nada sai da VPS nem é enviado a terceiros automaticamente.
- Nada no claude.ai; ações externas (BotFather, QR, gpg) são só do Ricardo.

## Review Focus

- Units que "terminam com sucesso" sem fazer nada (vigia, guarda-sessoes): desligar só depois de provar que `hermes_parado` dispara.
- Reembolso: `gabi-reembolso` também processa pistas/comandos da escuta; conferir que o brain cobre os avisos antes de aposentar.
- `gabi-wa-docs.path` ainda observa pastas do OpenClaw: removê-las não pode quebrar o drop-in do Hermes.
- `gog.conf`: confirmar que nada do brain depende do `gog` antes de remover (`planilha.py` só cita no docstring).
- Continuidade sem destinatário válido ou com saída vazia não pode mandar mensagem vazia.

---

### Task 1: Crons de datas e continuidade no Hermes  (FEITO 19/10)

**Files:** nenhum (estado do Hermes em `~/.hermes/cron/jobs.json`).

- [x] **Step 1:** `hermes cron resume` em aniversario-benedita/cookie/chafic/sandra, continuidade (OK do Ricardo) e lembrete-passaporte (OK do Ricardo).
- [x] **Step 2: Verificar** `hermes cron list | grep -c '\[active\]'` mostra os 7 ativos; `Next run` preenchido em todos.

### Task 2: Teste a seco da continuidade

**Files:** Read: `~/.hermes/scripts/continuidade.py`.

**Interfaces:** Produces: certeza do que o job de amanhã 10:00 imprime/envia.

- [ ] **Step 1:** Ler `continuidade.py`; identificar se ele envia por conta própria ou só imprime (stdout vai ao Telegram do Ricardo).
- [ ] **Step 2:** Rodar o script uma vez com o comando que o cron usa, capturando saída. Esperado: sem traceback; saída vazia ou texto legível; se o script enviar WhatsApp a terceiros sozinho, **parar e perguntar** antes de rodar.
- [ ] **Step 3:** Se referenciar `openclaw`/`gateway.env`, trocar pelo caminho do Hermes/`gabi-msg` e repetir o Step 2.

### Task 3: Provar o aviso `hermes_parado`

**Files:** Read: `gabi/avisos.py:208-217`, `gabi/rotas/avisos.py:117`.

**Interfaces:** Consumes: `estado_do_servico` do brain. Produces: evidência de que o vigia do OpenClaw é dispensável.

- [ ] **Step 1:** Ler `_hermes_parado` e achar o limiar (minutos parado) e como o aviso chega ao Ricardo.
- [ ] **Step 2:** Teste de unidade existente: `cd ~/gabi-brain && python -m pytest tests -k hermes_parado -q`. Esperado: passed.
- [ ] **Step 3 (precisa de janela combinada com o Ricardo):** `sudo systemctl stop hermes-gateway`, esperar o limiar, rodar `gabi-brain-avisos.service`, conferir aviso `hermes_parado` registrado, `sudo systemctl start hermes-gateway`. Sem a janela, a Task 4 fica como está.

### Task 4: Silenciar vigia e guarda-sessões

**Files:** Modify (estado): `gabi-vigia.timer`, `gabi-guarda-sessoes.timer`.

- [ ] **Step 1:** Só se a Task 3 passou: `sudo systemctl disable --now gabi-vigia.timer gabi-guarda-sessoes.timer`.
- [ ] **Step 2: Verificar** `systemctl list-timers --all | grep -E 'vigia|guarda'` vazio.

### Task 5: Paridade e aposentadoria do reembolso legado

**Files:** Read: `/opt/gabi-fin/reembolso_fila.py`, `/opt/gabi-fin/paperless_fluxos.py`, `gabi/mcp/ferramentas_reembolso.py`. Modify (estado): `gabi-reembolso.{timer,path}`, `gabi-reembolso-segunda.timer`, `gabi-fluxos-diario.timer`.

- [ ] **Step 1:** Listar o que cada script legado produz (avisos "abre/pronto", lista de segunda, pistas da escuta, descarte, extrato) e mapear cada um a uma função do brain (`reembolso_saude_pendentes`, `reembolso_saude_segunda`, escuta). Registrar lacunas em `docs/BACKLOG.md`.
- [ ] **Step 2:** Comparar pendentes: saída de `reembolso_saude_pendentes` (via função do brain, leitura) contra o estado do legado (`fila-reembolso/`, Paperless). Esperado: mesmos documentos; divergência vira item de BACKLOG, não bloqueia silenciar os avisos que já falham.
- [ ] **Step 3:** Desabilitar as 3 units legadas **que já falham** (`ECONNREFUSED 127.0.0.1:18789`): `sudo systemctl disable --now gabi-reembolso.timer gabi-reembolso.path gabi-reembolso-segunda.timer gabi-fluxos-diario.timer`. O trecho "Paperless/descarte/extrato" do `fluxos-diario` só some se a Step 1 mostrar cobertura no brain; senão manter o timer e trocar `OPENCLAW_CMD` por `/usr/local/bin/gabi-msg` (backup antes).
- [ ] **Step 4: Verificar** `journalctl -u gabi-reembolso -u gabi-fluxos-diario --since '1 hour ago' | grep -c ECONNREFUSED` = 0 após uma hora.

### Task 6: Limpar `gabi-wa-docs` e arquivar units substituídas

**Files:** Modify: `/etc/systemd/system/gabi-wa-docs.path`, `gabi-wa-docs.service`; mover `gabi-financeiro`, `gabi-contas-cartoes`, `gabi-app`, `gabi-fluxos-mensal` (units + timers) para `/etc/systemd/system/_arquivo-openclaw/`.

- [ ] **Step 1:** Backup de `.path`/`.service`. Remover só os `PathChanged/PathExistsGlob` que apontam a `/var/lib/gabi/.openclaw`; manter o drop-in `hermes.conf` e o selo `wa-hermes.stamp`.
- [ ] **Step 2: Verificar** `systemctl daemon-reload && systemctl show gabi-wa-docs.path -p PathChanged` lista só pastas do Hermes; soltar um PDF de teste em `~/.hermes/cache/documents/` e conferir entrada no Paperless (usar arquivo já existente, não dado novo de saúde).
- [ ] **Step 3:** Desabilitar e mover as units substituídas; `daemon-reload`; `systemctl --failed` sem novas falhas.

### Task 7: Gate do corte (H8) — só humano/tempo

- [ ] **Step 1:** Conferir cada condição e registrar em `docs/historico/PROGRESSO-GOAL.md`:
  - `escuta.modo='ativo'` e `escuta-ouvinte.service` active (hoje: inactive; depende de QR E1 e remetentes E2–E4 do Ricardo);
  - 7 dias de Hermes sem queda desde 19/10 12:54 → liberado em 26/10;
  - backup exportado com hash (H6, chave gpg do Ricardo);
  - `grep -ril openclaw /etc/systemd/system | grep -v '\.bak'` só lista `openclaw-gateway*` e itens já arquivados.
- [ ] **Step 2:** Se qualquer condição falhar, **parar aqui** e listar ao Ricardo o que falta. Tasks 8 não rodam.

### Task 8: Remoção (só após Task 7 verde)

- [ ] **Step 1:** Confirmar que o brain não depende do `gog`: `grep -rn "gog" gabi/ --include=*.py | grep -v '^.*#'` sem uso em runtime; ponte Google testada (`agenda`/`correio` rodam verdes) antes e depois de remover `gog.conf`.
- [ ] **Step 2:** `sudo systemctl disable --now` das units restantes; mover para `_arquivo-openclaw/`; remover `openclaw-gateway.service` + `.d/`; tirar linhas `OPENCLAW_*` de `gabi.env` (backup antes, sem imprimir valores).
- [ ] **Step 3:** Desinstalar o pacote `openclaw`; manter `gabi-msg` se algo ainda o usa.
- [ ] **Step 4:** Mover `/var/lib/gabi/.openclaw` para arquivo cifrado (gpg do Ricardo); apagar do disco após 30 dias sem uso. Não tocar no usuário `gabi`.
- [ ] **Step 5:** Ricardo revoga o bot Telegram do OpenClaw no BotFather e o token do gateway.
- [ ] **Step 6: Verificar** suíte do brain verde, `systemctl --failed` vazio, `hermes-gateway` e crons ativos, resumo das 07:05 do dia seguinte entregue.

### Rollback

Até a Task 8: `sudo systemctl enable --now openclaw-gateway` e reabilitar as units desligadas (cada backup `*.bak-antes-*`). Depois da Task 8: só pelo backup cifrado da `.openclaw`.
