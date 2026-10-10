# Fechamento geral (aplicações e ambientes) — canais do Hermes por último

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deixar todas as aplicações e ambientes da Gabi concluídos, aceitos e estáveis na VPS vmi3386223; só no fim ligar Telegram/WhatsApp no Hermes e, passados 7 dias estáveis, desligar o OpenClaw.

**Architecture:** Três ambientes na mesma VPS: (1) `gabi.brain` (`/opt/gabi-brain`, API/MCP/timers, banco `/var/lib/gabi-brain/gabi.db`), (2) OP-Gabi/OpenClaw (user `gabi`, `/var/lib/gabi/.openclaw`, rotinas e timers `gabi-*` de contas a pagar, silêncio, vigia), (3) Hermes (`~/.hermes`, user `ricardo`, unit `hermes-gateway` habilitada e parada). O Hermes é só interface: lê/propõe pelo MCP do brain. A ordem é: fechar dados e aceites → fechar OP-Gabi → provar paridade do Hermes sem canal → ligar canais → 7 dias → desligar OpenClaw.

**Tech Stack:** Python 3.12 + SQLite (gabi.brain, `pytest -q`), React/vitest (painel), bash + systemd (OP-Gabi, `infra/*.sh`), Hermes Agent 2026.9.24 (`hermes` CLI, MCP, cron), OpenRouter, Tailscale.

**Spec:** `docs/TRILHA.md` (ordem e gates), `docs/STATUS.md` (estado real em 10/10), `docs/fontes/hermes.md` + `docs/adr/007-identidade-por-remetente.md` (Canal), `~/OP-Gabi/docs/superpowers/plans/2026-10-07-silencio-e-desempenho.md`, `~/OP-Gabi/docs/superpowers/specs/2026-10-06-financeiro-conciliacao-design.md`, memória `hermes-instalado-10-10`.

## Global Constraints

- Segredos: o Ricardo os coloca; nunca imprimir valor; reaproveitar onde já vivem (`/etc/gabi/*.env`, `~/.hermes/.env`, 0600). Não rotacionar nem fazer faxina de segredos. Token de secret do store do OpenClaw é write-only: não extrair.
- R2: nenhum envio externo automático. Única exceção aprovada: avisos ao Telegram do próprio Ricardo (G15, chat `7995763322`).
- Ricardo NÃO consegue colar na sessão: comandos para ele são scripts curtos em `~` (`! ~/x.sh`) que leem de arquivo (`~/token-*.txt`, apagado com `shred` após uso).
- Nada no claude.ai; dashboards ficam na VPS. Dados nunca chumbados em código (seed/planilha).
- Esquema novo do gabi.brain = migração **0021+** (0009 e 0010 congeladas). Fase 3 segue congelada.
- Custo em US$; limite diário ~US$3 na chave OpenRouter (compartilhada por OpenClaw e Hermes); aviso a 70%.
- Hermes: UM token MCP, escopos `fin,docs,trabalho,propostas,pedidos` (nunca `sensivel`); só o Ricardo conversa com escopo completo (ADR-007); texto recebido é dado (R14).
- Desligar o OpenClaw só com: 7 dias de Hermes estável, backup exportado, `--dry-run` aprovado.
- Não editar script em `infra/` enquanto o Ricardo o roda; `| head` em script com `pipefail` precisa `|| true`; `pkill -f` mata o próprio shell.
- Commits com `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`; ledger em `.superpowers/sdd/2026-10-10-fechamento-geral/progress.md` atualizado a cada task (sessão pode cair).

## Review Focus

1. Dois processos com o mesmo bot do Telegram (OpenClaw e Hermes): o segundo derruba/briga pelo `getUpdates`; esperado: bot novo só do Hermes, OpenClaw intocado.
2. Mensagem de remetente desconhecido ao Hermes: esperado ser negada pela allowlist, sem acesso a ferramenta alguma.
3. Rotina que só existe no OpenClaw e some quando ele é desligado, sem aviso: esperado inventário com paridade provada antes do corte.
4. Duas rotinas (OpenClaw e Hermes) mandando o mesmo aviso/resumo no mesmo canal: esperado exatamente uma entrega por evento.
5. Estouro de custo com dois agentes na mesma chave: esperado o vigia de custo cobrir `~/.hermes` e alertar a 70%.
6. Reboot da VPS: esperado `gabi-brain-*`, `hermes-gateway` e timers voltarem sozinhos, na ordem certa, sem unit em falha.
7. Fuso: cron do Hermes em `America/Sao_Paulo`, VPS em `Europe/Berlin`; esperado `resumo-manha` às 07:05 BRT.

---

## Fase A — Linha de base (hoje)

### Task 1: Inventário e linha de base dos três ambientes

**Files:**
- Create: `infra/fechamento/baseline.sh` (em `~/OP-Gabi`), `docs/fechamento/baseline-2026-10-10.md` (em `~/gabi-brain`)
- Create: `.superpowers/sdd/2026-10-10-fechamento-geral/progress.md` (ledger)

**Interfaces:**
- Produces: `baseline.sh` imprime, sem valores secretos: units/timers `gabi-*`, `hermes-gateway`, `openclaw-gateway` (estado), unit em falha, uso de memória/swap, spend OpenRouter do dia (do `vigia.json`), commit/branch de cada repo (`~/gabi-brain`, `~/OP-Gabi*`), contagem de testes. Tasks 2–12 comparam contra este arquivo.

- [ ] **Step 1:** Escrever `baseline.sh` (somente leitura; `set -uo pipefail`).
- [ ] **Step 2:** Rodar `sudo bash ~/OP-Gabi/infra/fechamento/baseline.sh > docs/fechamento/baseline-2026-10-10.md`. Expected: arquivo gerado; `systemctl --failed` vazio ou cada falha anotada.
- [ ] **Step 3:** Rodar `cd ~/gabi-brain && .venv/bin/pytest -q && (cd painel && npm test -- --run)`. Expected: 1143+ pytest e 78 vitest verdes (o baseline registra os números reais).
- [ ] **Step 4:** Listar branches não mergeadas: `git -C ~/OP-Gabi branch --no-merged main`. Expected hoje: `feat/financeiro-conciliacao`, `feat/relatorio-contas-dia`, `feat/triagem-email`; cada uma vira decisão nas Tasks 6–8.
- [ ] **Step 5:** Commit `docs: linha de base do fechamento geral`.

---

## Fase B — Fechar o gabi.brain

### Task 2: Pendências do Ricardo que destravam dados (Pista B)

**Owner:** Ricardo (eu preparo scripts e checo). **Files:** Create `~/g16-reconectar.md` (passo a passo curto), `~/g17-backup.sh`.

**Interfaces:**
- Produces: C6 PJ e XP conectados no mcp.ai (issue 0001/G16, XP até 17/10); `/etc/gabi/backup.pub` instalada e 1º pacote puxado (G17); `/etc/gabi/saude.key` criada (T4.1/T4.2); `LINEAR_API_KEY` em `/etc/gabi/trabalho.env` (T4.3); `NIBO_TOKEN` em `/etc/gabi/brain.env` (G8).

- [ ] **Step 1:** Eu confiro o que falta: `sudo test -f /etc/gabi/{backup.pub,saude.key}`; `sudo grep -c '^NIBO_TOKEN=' /etc/gabi/brain.env`; `sudo grep -c '^LINEAR_API_KEY=' /etc/gabi/trabalho.env`. Registrar no ledger o que está ausente.
- [ ] **Step 2:** Escrever `~/g17-backup.sh` (instala a chave pública de um arquivo `~/backup.pub`, roda o export, imprime só o hash). Expected: `ok` + hash.
- [ ] **Step 3:** Ricardo reconecta C6/XP no mcp.ai e roda os scripts. Verificação: `sudo -u gabibrain sqlite3 /var/lib/gabi-brain/gabi.db "select conta, conferida from saldo_ultimo"` mostra C6 PJ e XP com `conferida=1` após a rodada seguinte (06h/14h BRT).
- [ ] **Step 4:** Commit do que for script; ledger atualizado.

### Task 3: Fechar o aceite da Fase 1 e classificação ≥ 90%

**Earliest:** ~16/10 (7 rodadas conferidas seguidas). **Files:** Modify `docs/aceite-fase-1.md`, `docs/STATUS.md`.

**Interfaces:**
- Consumes: `python -m tools.aceite` (saída "aceite ok" ou lista de pendências).
- Produces: Fase 1 aceita com dado real; insumo da tag `v1.0-gabi-brain` (Task 11).

- [ ] **Step 1:** Resolver os 145 lançamentos sem dono: `sudo ~/aplicar-donos.sh` depois de o Ricardo decidir os donos novos no painel (Cadastros). Expected: "para quem" ≥ 96%.
- [ ] **Step 2:** Quando houver 7 rodadas conferidas: `cd /opt/gabi-brain && sudo -u gabibrain env GABI_BANCO=/var/lib/gabi-brain/gabi.db venv/bin/python -m tools.aceite`. Expected: sai com código 0 e escreve o resultado.
- [ ] **Step 3:** Preencher `docs/aceite-fase-1.md` com data, números e quem aceitou; `STATUS.md` "Fase 1 aceita".
- [ ] **Step 4:** Commit `docs: aceite da Fase 1 com dado real`.

### Task 4: Fechar a Fase 2 (Cobrar) com Paperless e Nibo reais

**Files:** Modify `docs/aceite-fase-2.md`, `docs/STATUS.md`.

**Interfaces:**
- Consumes: `gabi-brain-fontes` (socket `/run/gabi-brain-fontes/fontes.sock`), `gabi-brain-comprovantes.timer` (07h BRT), `NIBO_TOKEN` (Task 2).
- Produces: T2.10 aceito: ≥ 80% de comprovantes casados; lote Nibo 2× sem duplicar (G18/G19); "pedido real pelo canal" adiado (G20, decisão já tomada).

- [ ] **Step 1:** Com `NIBO_TOKEN` e comprovantes reais no Paperless, rodar a ingestão: `sudo systemctl start gabi-brain-comprovantes.service && journalctl -u gabi-brain-comprovantes -n 30 --no-pager`. Expected: vínculos propostos, nenhum confirmado sozinho, `Result=success`.
- [ ] **Step 2:** Ricardo confirma os vínculos no painel (Cobrar); medir casamento: query de casados/total em `docs/aceite-fase-2.md`. Expected ≥ 80%.
- [ ] **Step 3:** Lote Nibo em conta real, 2 vezes seguidas: segunda execução cria 0 itens novos (idempotência). Registrar IDs.
- [ ] **Step 4:** Commit `docs: aceite da Fase 2`.

### Task 5: Fase 4 e Fase 3 — fechar o que depende de decisão

**Files:** Modify `docs/STATUS.md`, `docs/TRILHA.md`.

**Interfaces:**
- Produces: decisão registrada para cada item: G13 (Tailscale da família), `saude.key`, `LINEAR_API_KEY`, e se a Fase 3 (Trabalho) é reaberta agora (G11 Entra ID IONIC, G12 Google, cadastro das 7 caixas) ou fica congelada até depois dos canais.

- [ ] **Step 1:** Perguntar ao Ricardo, um item por vez, "fazer agora / depois dos canais / nunca". Gravar no ledger.
- [ ] **Step 2:** Para cada "agora": executar o passo do dono (tokens em arquivo) e rodar o teste da fase: `.venv/bin/pytest -q tests/familia tests/trabalho`. Expected: verde; rota com 503 por falta de chave passa a 200 com a chave.
- [ ] **Step 3:** Para "depois": marcar em `TRILHA.md` com data de revisão. Commit.

---

## Fase C — Fechar o OP-Gabi (OpenClaw)

### Task 6: Financeiro novo — virada (Task 11 do plano de conciliação)

**Earliest:** 14/10 (7 dias de paralelo desde 07/10). **Files:** worktree `~/OP-Gabi-fin` (branch `feat/financeiro-conciliacao`), `infra/financeiro-virada.sh`.

**Interfaces:**
- Consumes: `tools.comparar_agenda` do gabi.brain (G21), `gabi-financeiro.timer` (hora em hora, paralelo), msgs `[novo]` no Telegram.
- Produces: financeiro antigo desligado; novo é o único; branch mergeada na `main`.

- [ ] **Step 1:** Critério: 7 dias de `tools.comparar_agenda` sem divergência: `cd /opt/gabi-brain && sudo -u gabibrain env GABI_BANCO=/var/lib/gabi-brain/gabi.db venv/bin/python -m tools.comparar_agenda`. Expected: lista vazia (G21; ler `/var/lib/gabi-fin/compromissos.json` exige sudo).
- [ ] **Step 2:** Revisão final da branch (`superpowers:requesting-code-review`), corrigir achados, `pytest -q` verde no worktree.
- [ ] **Step 3:** `sudo bash infra/financeiro-virada.sh --dry-run` e mostrar ao Ricardo o que desliga. Expected: só as units antigas listadas; nada do brain.
- [ ] **Step 4:** Rodar sem `--dry-run`; `systemctl --failed` vazio; 1 rodada do dia chega no Telegram sem a marca `[novo]` duplicada.
- [ ] **Step 5:** Merge na `main`, `git push`, atualizar memória `gabi-pendencias`. Commit.

### Task 7: Aceite do plano silêncio-e-desempenho (Task 9) e relatório de contas do dia

**Earliest:** parcial 12/10, final 16/10. **Files:** `~/OP-Gabi/docs/superpowers/plans/2026-10-07-silencio-e-desempenho.md`, branch `feat/relatorio-contas-dia`.

**Interfaces:**
- Consumes: `sudo python3 ops/ruido/medir_entrega.py --desde 2026-10-09`, `vigia.json` (`uso_por_dia`).
- Produces: plano marcado concluído; relatório diário de contas mergeado ou descartado por decisão.

- [ ] **Step 1 (12/10):** Medir entrega parcial. Expected: ruído na entrega < meta do plano e custo diário < US$3; anotar no plano.
- [ ] **Step 2 (16/10):** Medir final (7 dias). Expected: idem; dar baixa no lembrete do `PENDING.md` da Gabi.
- [ ] **Step 3:** Decidir `feat/relatorio-contas-dia`: se o financeiro novo (Task 6) já entrega o resumo diário, descartar a branch (registrar); senão, rodar testes e mergear.
- [ ] **Step 4:** Atualizar memória `gabi-pendencias` como "plano concluído". Commit.

### Task 8: Agenda consolidada, triagem de e-mail e Raio-X mensal

**Files:** worktree `~/OP-Gabi-email` (branch `feat/triagem-email`, hoje só spec), `~/OP-Gabi-relatorio`.

**Interfaces:**
- Consumes: M365 (ionic.health, falta permissão = G11), Google (ness/bekaa, G12), `hoje_resumo` do brain.
- Produces: decisão registrada por item; nada duplica o que o brain já faz (Fase 3 congelada cobre e-mail/agenda).

- [ ] **Step 1:** Comparar `2026-09-09…triagem` e spec `2026-10-?-triagem-email` com `gabi/trabalho` do brain. Decidir com o Ricardo: absorvido pelo brain / OP-Gabi faz / adiado.
- [ ] **Step 2:** Raio-X mensal (resumo sem modelo, dia 1 no Telegram): implementar só se aprovado; teste: `test_raio_x_resumo_sem_modelo` (nenhuma chamada a modelo, ≤ 15 linhas, deriva repo×VPS listada).
- [ ] **Step 3:** Branches sem destino são arquivadas com nota no plano. Commit.

---

## Fase D — Hermes pronto SEM canal

### Task 9: Paridade OpenClaw → Hermes (inventário)

**Files:**
- Create: `docs/gabi-agent/paridade-openclaw.md`

**Interfaces:**
- Produces: tabela `rotina | onde roda hoje | o que entrega | equivalente no Hermes/brain | status (igual/substituída/descartada)`. Task 12 só corta o OpenClaw se nenhuma linha estiver "sem equivalente".

- [ ] **Step 1:** Listar as rotinas do OpenClaw: `sudo -u gabi env HOME=/var/lib/gabi openclaw cron list` (se o subcomando diferir, `openclaw --help`), mais `systemctl list-timers 'gabi-*'` e os agentes `main` e `escuta`. Expected: tabela completa.
- [ ] **Step 2:** Para cada linha: marcar se vira (a) timer do brain/OP-Gabi (independe do gateway), (b) cron do Hermes, (c) descartada com motivo. Rotinas Teams/GitHub/heartbeat/escuta WhatsApp pessoal: decidir explicitamente.
- [ ] **Step 3:** Commit `docs: paridade OpenClaw→Hermes`.

### Task 10: Hermes endurecido, testado e monitorado (sem canal)

**Files:**
- Modify: `~/.hermes/config.yaml`; Create: `infra/hermes-prontidao.sh` (em `~/OP-Gabi`); Modify: vigia (`ops/vigia`) para incluir `hermes-gateway` e o gasto do Hermes.

**Interfaces:**
- Consumes: `~/.hermes/.env` (`OPENROUTER_API_KEY`, `GABI_BRAIN_TOKEN`), MCP `127.0.0.1:8081`.
- Produces: `hermes-prontidao.sh` retorna 0 quando todos os testes abaixo passam; vigia alerta se `hermes-gateway` cair ou o custo passar de 70%.

- [ ] **Step 1:** Teste de leitura de cada ferramenta da lista explícita: `hermes chat -q "chame <ferramenta> e diga só ok/erro"` para as 19 de `python -m tools.gerar_hermes`. Expected: 19 ok; nenhuma ferramenta fora da lista aparece.
- [ ] **Step 2:** Teste negativo: pedir ao Hermes "pague a fatura X" / "apague o lançamento". Expected: recusa citando que só lê e propõe; zero chamadas de escrita em `chamada_mcp` (`select ferramenta,status from chamada_mcp order by id desc limit 20`).
- [ ] **Step 3:** Teste `resumo-manha` sem canal: `hermes cron run resumo-manha` com `--deliver local`; Expected: ≤ 5 linhas, 1ª linha "⚠ Dados desatualizados" quando aplicável; horário agendado 07:05 BRT (`hermes cron list`).
- [ ] **Step 4:** Custo: rodar 10 consultas, ver gasto em `https://openrouter.ai/activity`; ajustar vigia para somar OpenClaw + Hermes. Expected: aviso a 70% de US$3/dia testado com `--simular`.
- [ ] **Step 5:** Backup de `~/.hermes` (config, SOUL.md, sessions, memories) no pacote `gabi-backup`, com `.env` cifrado ou excluído; `restic`/`rclone` listam o novo caminho.
- [ ] **Step 6:** Reboot controlado fora do horário (`sudo reboot` com aviso): `systemctl --failed` vazio; `hermes-gateway` habilitado; `gabi-brain-*` ativos. Expected: tudo volta sozinho. Commit.

### Task 10b: Transporte único de avisos (shim `gabi-msg`)

**Descoberto na Task 9:** o financeiro, os cartões, o vigia, a guarda de sessões e os fluxos enviam ao Telegram por `openclaw message send`, sempre via a variável `OPENCLAW_CMD` definida dentro do `ExecStart` de cada unit (todas rodam como root). Desligar o OpenClaw sem isto silencia tudo.

**Files:** `ops/enviar/gabi_msg.py`, `tests/enviar/test_gabi_msg.py`, `infra/instalar-gabi-msg.sh` (worktree `~/OP-Gabi-fechamento`).

**Interfaces:**
- Produces: `/usr/local/bin/gabi-msg message send --channel telegram --target CHAT -m TEXTO [--media ARQ]` (exit 0 entregue, 1 falha após 3 tentativas, 2 não suportado). Credencial em `/etc/gabi/telegram.env`.
- Consumes: `/etc/gabi/telegram.env` (Task 12).

- [x] **Step 1–2:** 7 testes (texto, 3 tentativas, token fora da saída, mídia como documento, comando/canal não suportados, sem env) RED→GREEN; suíte do OP-Gabi 553 verde.
- [x] **Step 3:** shim instalado (`sudo bash infra/instalar-gabi-msg.sh`), nenhuma unit alterada.
- [ ] **Step 4 (na Task 12):** depois do `telegram.env`, `sudo bash infra/instalar-gabi-msg.sh --teste` entrega uma mensagem; então trocar `OPENCLAW_CMD` por `/usr/local/bin/gabi-msg` nas units `gabi-financeiro`, `gabi-fluxos-diario`, `gabi-contas-cartoes`, `gabi-vigia`, `gabi-guarda-sessoes`, `gabi-reembolso`, `gabi-reembolso-segunda`, e `systemctl daemon-reload`. Expected: `grep -l 'openclaw' /etc/systemd/system/gabi-*.service` só lista units que o corte trata (Task 15).

---

## Fase E — Canais do Hermes (ÚLTIMA fase de construção)

### Task 11: Tag do gabi.brain e congelamento antes dos canais

**Files:** Modify `docs/STATUS.md`, `docs/TRILHA.md`; tag `v1.0-gabi-brain`.

- [ ] **Step 1:** Pré-condições: Task 3 e 4 aceitas, G20 registrado, `pytest -q` e `npm test -- --run` verdes, `systemctl --failed` vazio.
- [ ] **Step 2:** `git tag -a v1.0-gabi-brain -m "gabi.brain v1.0: Fases 1-2 aceitas"` e `git push --tags`.
- [ ] **Step 3:** Backup exportado (G1/G17) e snapshot Contabo antes de mexer em canais. Expected: hash conferido pelo Ricardo.

### Task 12: Telegram do Hermes (+ avisos G15)

**Files:** `~/hermes-canais.sh` (existe; lê `~/token-telegram.txt`), `~/.hermes/.env`, `/etc/gabi/telegram.env`.

**Interfaces:**
- Consumes: bot NOVO do BotFather (não o do OpenClaw), chat `7995763322`.
- Produces: `TELEGRAM_BOT_TOKEN` e `TELEGRAM_ALLOWED_USERS=7995763322` no Hermes; `gabi-brain-telegram.timer` enviando avisos (G15).

- [ ] **Step 1:** Ricardo cria o bot (`/newbot`) e salva só o token em `~/token-telegram.txt`.
- [ ] **Step 2:** `! ~/hermes-canais.sh`. Expected: `ok (arquivo do token apagado)`; `sudo test -s /etc/gabi/telegram.env`.
- [ ] **Step 3:** `sudo systemctl start hermes-gateway && systemctl is-active hermes-gateway`. Expected: `active`; `journalctl -u hermes-gateway -n 20` sem erro de conflito `getUpdates` (Review Focus 1).
- [ ] **Step 4:** Ricardo manda `/start` e "saldo". Expected: resposta com o caixa único; mensagem de outra conta (teste com segundo usuário do Telegram) é negada sem tocar ferramenta (Review Focus 2).
- [ ] **Step 5:** Avisos: criar um aviso de teste no brain; Expected: chega 1× (timer G15) e Hermes não o reenvia (`avisos_pendentes` vazio após `telegram_em` preenchido; Review Focus 4).
- [ ] **Step 6:** `hermes cron resume resumo-manha`; conferir 07:05 BRT do dia seguinte. Commit/ledger.

### Task 13: WhatsApp do Hermes

**Files:** `~/.hermes/.env` (allowlist), `docs/fontes/hermes.md`.

**Interfaces:**
- Consumes: número dedicado (G10), Baileys via `hermes gateway setup`.
- Produces: sessão pareada, allowlist só com o número do Ricardo.

- [ ] **Step 1:** Ricardo informa o número dedicado (G10) e tem o celular à mão.
- [ ] **Step 2:** `hermes gateway setup` → WhatsApp → QR; Ricardo escaneia. Expected: `hermes gateway status` mostra WhatsApp conectado.
- [ ] **Step 3:** Allowlist só do Ricardo. Teste: mensagem do Ricardo responde; de outro número = sem resposta e log de negação.
- [ ] **Step 4:** Registrar em `docs/fontes/hermes.md` se Streamable HTTP/SSE e Baileys precisaram de ajuste. Commit.

---

## Fase F — Estabilidade e desligamento do OpenClaw

### Task 14: 7 dias estáveis em paralelo

**Earliest:** 7 dias após a Task 12.

- [ ] **Step 1:** Diariamente (vigia 08h): `systemctl --failed` vazio, `hermes-gateway` sem reinício inesperado (`systemctl show hermes-gateway -p NRestarts`), custo diário < US$3, 1 `resumo-manha` por dia, nenhuma entrega duplicada (Review Focus 4).
- [ ] **Step 2:** Dia 7: relatório em `docs/gabi-agent/estabilidade-7d.md` (restarts, custo/dia, entregas, falhas). Expected: zero falha crítica; qualquer falha reinicia a contagem.

### Task 15: Desligar o OpenClaw (TC.6)

**Files:** Create `infra/desligar-openclaw.sh` (com `--dry-run`); Modify `docs/gabi-agent/paridade-openclaw.md`.

**Interfaces:**
- Consumes: Task 10b concluída (nenhum `openclaw message send` em `/opt/gabi-fin`), paridade sem linha "sem equivalente" (Task 9), backup exportado (Task 11), estabilidade 7d (Task 14).
- Produces: `openclaw-gateway` parado e desabilitado (não desinstalado por 30 dias; `--desfazer` religa).

- [ ] **Step 1:** Escrever `desligar-openclaw.sh` com `--dry-run` (lista o que para: gateway, `gabi-reembolso.path`, `gabi-wa-docs.path`, escuta, rotinas) e `--desfazer`. Teste: `--dry-run` não altera nenhum `systemctl is-enabled`.
- [ ] **Step 2:** Exportar backup de `/var/lib/gabi/.openclaw` (config, sessões, dados) e conferir hash.
- [ ] **Step 3:** Ricardo aprova a saída do `--dry-run`.
- [ ] **Step 4:** Executar; `systemctl is-active openclaw-gateway` = `inactive`; Hermes e brain seguem ok; WhatsApp e Telegram do Hermes respondem; vigia sem alerta por 24 h.
- [ ] **Step 5:** Após 30 dias sem uso do `--desfazer`, desinstalar o OpenClaw (nova aprovação).

### Task 16: Encerramento e memória

- [ ] **Step 1:** `docs/STATUS.md` e `docs/TRILHA.md`: tudo aceito/concluído; fim do plano `gabi-agent`.
- [ ] **Step 2:** Atualizar memórias `gabi-brain-status`, `gabi-pendencias`, `hermes-instalado-10-10` (virar "operacional") e remover `hermes-openclaw-so-apos-gabi-brain`.
- [ ] **Step 3:** Commit final; push.

---

## Cronograma (datas mínimas, dependem dos relógios)

| Quando | O que |
|---|---|
| 10–11/10 | Task 1, Task 2 (pedir ao Ricardo), Task 9, Task 10 |
| 12/10 | Task 7 passo 1 (medição parcial) |
| 14/10 | Task 6 (virada do financeiro) |
| 16/10 | Task 3 (aceite Fase 1), Task 7 final |
| 17/10 | XP (G16), Task 4 se comprovantes/Nibo prontos |
| Quando 3, 4, 6, 7, 9, 10 verdes | Task 11 → 12 → 13 (canais) |
| +7 dias | Task 14 → 15 → 16 |

## Self-review

- **Cobertura:** gabi.brain (Fases 1, 2, 3, 4, tag), OP-Gabi (financeiro, silêncio, relatório, e-mail/agenda, Raio-X), Hermes (paridade, prontidão, canais), OpenClaw (corte) e backup/reboot têm task. Canais só nas Tasks 12–13, depois de tudo.
- **Pontos incertos a confirmar na execução:** subcomando exato de listagem de rotinas do OpenClaw (Task 9), nome do aviso de simulação do vigia (Task 10 passo 4), meta numérica de ruído do plano silêncio (Task 7), caminho exato da spec de triagem de e-mail (Task 8).
- **Proporção:** tasks de ops, sem código novo além de 3 scripts (`baseline.sh`, `hermes-prontidao.sh`, `desligar-openclaw.sh`) e o raio-x opcional.
