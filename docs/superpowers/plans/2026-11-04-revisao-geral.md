# Revisão geral 04/11 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir os achados da avaliação de 04/11 (pacotes A a D) sem mudar comportamento visível além do descrito no spec.

**Architecture:** Mudanças pontuais em módulos existentes; nada novo de arquitetura. Backend Python (FastAPI + SQLite WAL), deploy systemd/bash, painel React/Vite.

**Tech Stack:** Python 3.12, sqlite3, urllib, pytest; bash/systemd; React 18 + TypeScript + vitest.

**Spec:** `docs/superpowers/specs/2026-11-04-revisao-geral-design.md`

## Global Constraints
- Branch `fix/revisao-geral` no worktree `~/gabi-brain-revisao` (criar a partir da `main`). Nada de merge, push ou instalação sem ok explícito do Ricardo.
- Não ler nem mexer em segredos (`/etc/gabi/*.env`, `~/.hermes/auth.json`); não tocar em `/var/lib/gabi-brain` nem em `/opt`.
- Nunca mexer em despesa/ocorrência paga; dados nunca chumbados.
- Testes: `.venv/bin/python -m pytest -q` (usar o `.venv` do repo principal: `~/gabi-brain/.venv`); painel: `cd painel && npx vitest run && npm run build`.
- Comentários e mensagens em português, no estilo dos arquivos vizinhos (docstring curta com "Consome:"/"Grava:" quando o módulo já usa).
- Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Desvios do spec (decididos ao planejar)
- A2: em vez de trocar caso a caso, o padrão de `transacao` vira `begin immediate` (toda transação do código grava; ler antes de gravar é a regra, não a exceção). O `begin` manual de `captura.py` também vira `begin immediate`.
- C3: os clientes HTTP devolvem só `(status, json)`, sem cabeçalhos; o retry usa espera fixa 2 s e 5 s em vez de `Retry-After`.
- D2: `CustoGabi` e `Gabi/Qualidade` formatam dólar (US$), ficam como estão; o formatador único é só de R$.

## Review Focus
1. Conta com um único lançamento ilegível: as outras transações da mesma conta continuam gravadas e o valor antigo do ilegível no banco não muda (Task 1).
2. Transação só de leitura que passou a pegar o lock de escrita: nenhuma deve existir; conferir os 71 `transacao(` (Task 2, passo de auditoria).
3. Redirecionamento para o mesmo host continua levando o token (download do Paperless/Nibo não quebra) (Task 6).
4. Instalação com banco em uso (API no ar): o backup consistente não trava nem corrompe; instalação numa VPS sem banco ainda não falha (Task 5).
5. Painel: trocar de filtro e voltar ao anterior rapidamente não mostra o dado da url errada (Task 9).

---

### Task 1: Valor ilegível não vira zero (A1)

**Files:**
- Modify: `gabi/dinheiro/moeda.py` (`valor_lancamento`, linha ~38)
- Modify: `gabi/dinheiro/captura.py` (`_gravar_contas` ~linha 190, `_processar_conta` ~linha 225, resumo da rodada)
- Test: `tests/dinheiro/test_moeda.py` (ou o teste de moeda existente), `tests/dinheiro/test_captura.py`

**Interfaces:**
- Produces: `valor_lancamento(t, tipo_conta)` levanta `ValorIlegivel(ValueError)` (definida em `moeda.py`) quando `amount` não é legível. `_processar_conta` devolve `(lidos, novos, ilegiveis)`; o resultado da rodada ganha a chave `ilegiveis: int`, impressa ao lado de `lidos`/`novos`.

- [ ] **Step 1: testes que falham**
  - `test_amount_ilegivel_levanta`: `valor_lancamento({"amount": "1,234.56", "type": "DEBIT"}, "BANK")` e `{"amount": ""}` e `{}` → `pytest.raises(ValorIlegivel)`.
  - `test_lancamento_ilegivel_nao_sobrescreve_valor`: grava pela captura uma transação `id="t1"` com `amount: "-50.00"`; segunda rodada com `t1` `amount: "lixo"` e `t2` `amount: "-10.00"` → `valor_centavos` de `t1` continua `-5000`, `t2` gravada, `ilegiveis == 1`.
  - `test_saldo_ilegivel_nao_grava`: conta com `balance: "abc"` → nenhuma linha nova em `saldo` para essa conta; as outras contas gravam.
- [ ] **Step 2:** rodar `pytest tests/dinheiro -q -k "ilegivel"` → FAIL.
- [ ] **Step 3:** implementar. Em `_processar_conta`, `try: val = valor_lancamento(...) except ValorIlegivel: ilegiveis += 1; continue`. Em `_gravar_contas`, se `para_centavos(...)` do `balance` der None, não executa o `insert or replace into saldo` daquela conta. Atualizar o desempacotamento em `rodar` (linha ~331) e somar `ilegiveis` como `lidos`/`novos`.
- [ ] **Step 4:** `pytest tests/dinheiro -q` → PASS.
- [ ] **Step 5:** commit `fix(captura): valor ilegível é pulado e contado, nunca vira zero`.

### Task 2: Transações seguras no SQLite (A2, A3, A4, A5)

**Files:**
- Modify: `gabi/db.py:69-78` (`transacao`), `gabi/dinheiro/captura.py:195-200` (`_purgar_futuro`) e `:327` (`begin` manual), `gabi/api.py:146-148` (revogar tudo)
- Test: `tests/test_db.py`, `tests/dinheiro/test_captura.py`, `tests/test_api.py`

**Interfaces:**
- Produces: `transacao(con, imediata: bool = True, aberta: bool = False)` (padrão muda para True).

- [ ] **Step 1: testes que falham**
  - `test_transacao_padrao_e_imediata`: `con.set_trace_callback(lista.append)`; `with transacao(con): pass` → `"begin immediate"` em `lista`.
  - `test_transacao_commit_falho_faz_rollback`: conexão falsa cujo `execute("commit")` levanta `sqlite3.OperationalError`; depois do `pytest.raises`, `"rollback"` foi executado.
  - `test_purgar_futuro_tudo_ou_nada`: dois lançamentos futuros com conciliação; trace callback que levanta na segunda `delete from lancamento` → os dois lançamentos e conciliações continuam no banco.
  - `test_revogar_tudo_atomico`: falha simulada no `insert into decisao` (trigger `raise(abort)` criado no teste) → nenhum token ficou revogado.
- [ ] **Step 2:** rodar os quatro → FAIL.
- [ ] **Step 3:** implementar: padrão `imediata=True`; `commit` dentro de `try` (se falhar, `rollback` e relança); `_purgar_futuro` inteiro em `with transacao(con):`; `begin` manual da captura → `begin immediate`; revogar-tudo em `with transacao(con):`.
- [ ] **Step 4: auditoria** — `grep -rn "transacao(" gabi` e conferir que cada bloco grava. Bloco só de leitura (se houver) passa a não usar `transacao`. Registrar a conclusão no corpo do commit ("71 usos conferidos; N ajustados").
- [ ] **Step 5:** `pytest -q` completo → PASS (a suíte inteira, porque o padrão mudou).
- [ ] **Step 6:** commit `fix(db): transação imediata por padrão; purga e revogar-tudo atômicos; commit falho desfaz`.

### Task 3: Testes que dependem da data (A6)

**Files:**
- Modify: `painel/tests/despesas.test.tsx:16-24`
- Modify: qualquer teste pytest que falhe na base do worktree só por causa da data de hoje (a Task 13 roda a suíte inteira; aqui, rodar `pytest -q` na base antes de mexer e anotar as falhas)

- [ ] **Step 1:** no worktree, `npx vitest run tests/despesas.test.tsx` → FAIL ("Dispensar este mês" não achado).
- [ ] **Step 2:** no teste, `vi.useFakeTimers({ toFake: ["Date"] }); vi.setSystemTime(new Date("2026-10-26T12:00:00-03:00"))` antes do render e `vi.useRealTimers()` no fim (mesmo padrão da linha 131).
- [ ] **Step 3:** `npx vitest run` → 205 passed. Para cada falha do pytest que dependa de `date.today()`/`datetime.now()`, injetar a data como os testes vizinhos fazem (parâmetro `hoje`/`agora`).
- [ ] **Step 4:** commit `test: fixa a data nos testes que venciam com o calendário`.

### Task 4: Units e backup (B1, B2, B5)

**Files:**
- Modify: `deploy/gabi-brain-backup.timer` (`OnCalendar=*-*-* 03:30:00 America/Sao_Paulo`; Description idem)
- Modify: `deploy/gabi-brain-api.service`, `deploy/gabi-brain-mcp.service`, `deploy/gabi-brain-fontes.service` (seção `[Unit]`: `OnFailure=gabi-brain-falha@%n.service`)
- Modify: `gabi/backup.py:14` (`TABELAS_CONTAGEM` += `"atividade", "projeto", "compromisso_linha", "valor_do_mes", "documento"`)
- Test: `tests/test_deploy.py:49-51`, `tests/test_backup_banco.py`

- [ ] **Step 1: testes que falham**
  - `test_backup_diario_as_0330_com_teste_de_restauracao`: passa a exigir `"OnCalendar=*-*-* 03:30:00 America/Sao_Paulo"`.
  - `test_servicos_longos_avisam_falha`: para api, mcp, fontes: `"OnFailure=gabi-brain-falha@%n.service"` e `"StartLimitBurst="` no texto.
  - `test_contagem_inclui_tabelas_novas`: os 5 nomes em `TABELAS_CONTAGEM` e `testar_restauracao` roda sem erro no banco-modelo do conftest.
- [ ] **Step 2:** FAIL. **Step 3:** editar. **Step 4:** `pytest tests/test_deploy.py tests/test_backup_banco.py -q` → PASS.
- [ ] **Step 5:** commit `fix(deploy): backup às 03:30 de Brasília, contagem com tabelas novas, serviços longos avisam falha`.

### Task 5: Instalador com backup e troca segura + restauração documentada (B3, B4)

**Files:**
- Modify: `deploy/instalar.sh:17-20`
- Modify: `docs/runbook.md` (nova seção `## Restaurar` com âncora `#restaurar`; trocar as menções soltas "ver Backup e restauração" pelo link)
- Test: `tests/test_deploy.py`

- [ ] **Step 1: testes que falham** (texto do script, como os vizinhos)
  - `test_instalar_faz_backup_do_banco_antes_de_copiar`: `"gabi.db.antes-instalar-"` aparece antes da primeira cópia para `/opt/gabi-brain`; usa `.backup(` (API do sqlite, não `cp` do arquivo); `chmod 600`/`chown gabibrain` no destino; retenção `tail -n +6`.
  - `test_instalar_troca_por_mv_e_nao_apaga_antes_de_copiar`: não existe `rm -rf /opt/gabi-brain/gabi` antes do `cp`; existe `.novo` e `mv`.
  - `test_arvore_copiada_pelo_instalar_roda_sozinha` continua passando.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** implementar. Backup (só se `/var/lib/gabi-brain/gabi.db` existir), com `python3` do sistema e heredoc: conexão ao banco, `src.backup(dst)`, destino `/var/backups/gabi-brain/gabi.db.antes-instalar-$(date +%F-%H%M)`; `chown gabibrain:gabibrain`, `chmod 600`; `ls -1t /var/backups/gabi-brain/gabi.db.antes-instalar-* | tail -n +6 | xargs -r rm -f`. Cópia: `rm -rf /opt/gabi-brain/.novo /opt/gabi-brain/.velho`, `install -d` dos dois, `cp -r` de gabi/migrations/seeds para `.novo` e as tools da lista para `.novo/tools`; depois, para cada pasta, `[ -e /opt/gabi-brain/$d ] && mv /opt/gabi-brain/$d /opt/gabi-brain/.velho/`; `mv /opt/gabi-brain/.novo/$d /opt/gabi-brain/`; no fim `rm -rf .novo .velho`.
- [ ] **Step 4:** runbook `#restaurar`: parar `gabi-brain-api gabi-brain-mcp gabi-brain-fontes` e os timers (`systemctl stop 'gabi-brain-*.timer'`); copiar o backup escolhido para `/var/lib/gabi-brain/gabi.db`, apagar `gabi.db-wal`/`-shm`; `chown gabibrain:gabibrain`, `chmod 600`; `sudo -u gabibrain sqlite3 ... "pragma integrity_check"` → `ok`; `systemctl start` serviços e os timers que estavam ligados (`systemctl list-timers` antes, anotar). Linha em `decisao`.
- [ ] **Step 5:** `bash -n deploy/instalar.sh` e `pytest tests/test_deploy.py -q` → PASS.
- [ ] **Step 6:** commit `fix(deploy): instalador faz backup do banco e troca o código sem janela vazia; runbook de restauração`.

### Task 6: Redirecionamento sem credencial e `next` do Paperless (C1, C2)

**Files:**
- Modify: `gabi/fontes/_http.py` (handler + opener exportado)
- Modify: `gabi/fontes/paperless.py:30-34,60-64`, `nibo.py:26-47`, `nibo_escrita.py:19`, `google_oauth.py:30`, `openrouter.py:90`, `mcpai.py:52`, `tokens.py:28` (trocar `urllib.request.urlopen` por `abrir`)
- Test: `tests/fontes/test_http.py` (novo), `tests/fontes/test_paperless.py`

**Interfaces:**
- Produces: em `_http.py`, `class SemCredencialEntreHosts(urllib.request.HTTPRedirectHandler)` e `abrir = urllib.request.build_opener(SemCredencialEntreHosts).open` (mesma assinatura de `urlopen`: `abrir(req, timeout=...)`).

- [ ] **Step 1: testes que falham**
  - `test_redirecionamento_outro_host_tira_credencial`: `SemCredencialEntreHosts().redirect_request(req, fp, 302, "Found", {}, "https://outro.example/x")` com `req` de `https://a.example/` com cabeçalhos `Authorization`, `ApiToken`, `X-Api-Key` → o novo request não tem nenhum dos três.
  - `test_redirecionamento_mesmo_host_mantem`: destino `https://a.example/y` → `Authorization` presente.
  - `test_paperless_next_de_outro_host_recusado`: `_http` falso devolvendo `{"results": [], "next": "https://mau.example/api/documents/?page=2"}` → `pytest.raises(ErroPaperless, match="link inválido")` e o `_http` falso não recebeu chamada para `mau.example`.
  - `test_clientes_nao_usam_urlopen_direto`: varre os 8 arquivos e falha se achar `urllib.request.urlopen(`.
- [ ] **Step 2:** FAIL. **Step 3:** implementar. `redirect_request` chama o `super()`; se `urlsplit(novo).netloc != urlsplit(req.full_url).netloc`, remove do novo request (e de `unredirected_hdrs`) os cabeçalhos cujo nome em minúsculas seja `authorization`, `apitoken`, `x-api-key` ou comece com `x-auth`. No Paperless, `_paginas` exige `url.startswith(self.base)`. `graph_ness.py` não muda.
- [ ] **Step 4:** `pytest tests/fontes -q` → PASS.
- [ ] **Step 5:** commit `fix(fontes): redirecionamento para outro host sem credencial; next do Paperless só no mesmo servidor`.

### Task 7: Retry em leitura (C3)

**Files:**
- Modify: `gabi/fontes/_http.py` (função de retry), `gabi/fontes/graph_ness.py:146-162` (`_get`), `gabi/fontes/google_email.py:45` (`_pegar`, só quando `metodo == "GET"`), `gabi/fontes/google_agenda.py:29` (`_pegar`), e o GET de `google_contatos.py` se houver helper equivalente
- Test: `tests/fontes/test_http.py`, `tests/fontes/test_graph_ness.py`, `tests/fontes/test_google_email.py`

**Interfaces:**
- Produces: `com_retry(fazer: Callable[[], tuple[int, Any]], *, dorme=time.sleep, esperas=(2, 5)) -> tuple[int, Any]` em `_http.py`; repete enquanto status ∈ `REPETIR = {429, 502, 503, 504}` e houver espera; devolve o último `(status, resp)`.

- [ ] **Step 1: testes que falham**
  - `test_com_retry_repete_429_e_para_no_ok`: `fazer` devolve 429, 503, 200 → resultado 200, `dorme` chamado com 2 e 5.
  - `test_com_retry_desiste_depois_de_duas`: sempre 503 → devolve 503, 3 chamadas.
  - `test_com_retry_nao_repete_404`: 1 chamada.
  - `test_graph_get_repete_503`: `_http` falso 503 depois 200 → `_get` devolve o dict.
  - `test_escrita_nao_repete`: `teams_chat_enviar` com `_http` falso 503 → uma chamada só (e `google_email` POST idem).
- [ ] **Step 2:** FAIL. **Step 3:** implementar; o `dorme` é injetável pelos construtores/funções que já recebem `http` (padrão `time.sleep`); nos testes existentes que simulam 429/503, injetar `dorme=lambda s: None`.
- [ ] **Step 4:** `pytest tests/fontes tests/envios -q` → PASS.
- [ ] **Step 5:** commit `feat(fontes): leitura repete em 429/5xx (2 s, 5 s); escrita segue com uma tentativa`.

### Task 8: Ponte não espera para sempre (C4)

**Files:**
- Modify: `gabi/fontes/ponte.py:108-113` (`_Manipulador.handle`)
- Test: `tests/fontes/test_ponte.py`

**Interfaces:**
- Produces: constante `ESPERA_PEDIDO = 30` em `ponte.py` (segundos).

- [ ] **Step 1: teste que falha** `test_servidor_desiste_de_cliente_mudo`: com `ponte.ESPERA_PEDIDO` monkeypatchado para 0.2, sobe o `Servidor` num `tmp_path`, conecta e não envia nada nem fecha; em até 2 s o servidor fecha a conexão (`recv` devolve `b""`).
- [ ] **Step 2:** FAIL (fica pendurado; usar `timeout` no socket do teste para não travar a suíte).
- [ ] **Step 3:** `self.request.settimeout(ESPERA_PEDIDO)` antes de `_ler_tudo`; `TimeoutError` → retorna sem resposta; `self.request.settimeout(None)` antes de `_atender`.
- [ ] **Step 4:** `pytest tests/fontes/test_ponte.py -q` → PASS. **Step 5:** commit `fix(ponte): servidor dá 30 s para chegar o pedido`.

### Task 9: Painel — dado da url certa e links seguros (D1, C5)

**Files:**
- Modify: `painel/src/lib/useApi.ts`
- Create: `painel/src/lib/url.ts` (`urlSegura`)
- Modify: `painel/src/telas/Trabalho/Hoje.tsx:32`, `painel/src/telas/CadastrosDocumentos.tsx` (onde `paperless` vira `href`)
- Test: `painel/tests/useApi.test.tsx` (novo), `painel/tests/url.test.ts` (novo)

**Interfaces:**
- Produces: `urlSegura(u: string | null | undefined): string | null` — devolve `u` se `new URL(u).protocol` for `http:` ou `https:`, senão `null`. `useApi` mantém a interface `Leitura<T>`.

- [ ] **Step 1: testes que falham**
  - `useApi`: render com url `/a` (resposta A), troca para `/b` com resposta pendente → `estado === "carregando"` e `env === null`; resolve B → `env.dados` é B. Recarregar `/b` com erro → `estado === "erro"` e `env` continua B.
  - `useApi`: `/a` lento, troca para `/b` rápido, `recarregar()` aguardado → a promessa só resolve depois da resposta de `/b`, mesmo que `/a` termine antes.
  - `urlSegura`: `"https://x"` → igual; `"javascript:alert(1)"`, `"data:text/html,x"`, `"lixo"`, `null` → `null`.
  - Hoje: evento com `link_reuniao: "javascript:x"` → sem link "entrar".
- [ ] **Step 2:** FAIL. **Step 3:** `useApi` guarda `{ url, env }` num estado só; `env` exposto é `null` quando `guardado.url !== url`; `liberar()` só dentro de `if (vivo)`. Nas telas, `href={urlSegura(x)}` e o link só aparece se não for `null`.
- [ ] **Step 4:** `npx vitest run` → PASS. **Step 5:** commit `fix(painel): troca de filtro não mostra dado velho; links externos só http(s)`.

### Task 10: Painel — formatadores únicos e código morto (D2, D3)

**Files:**
- Modify: `painel/src/lib/formato.ts` (+ `formatarBRL`, `horaDe`, `diaSP`)
- Modify: `componentes/Valor.tsx`, `telas/Projetos.tsx:29-30`, `telas/Atividades.tsx:19-24`, `telas/Regras.tsx:15`, `telas/Trabalho/Agenda.tsx:12` (passa a importar `diaSP`), `telas/CadastrosDocumentos.tsx:55`
- Create: `painel/src/graficos/fluxo.ts` (`No`, `Fluxo`, `corDestino` movidos de `Sankey.tsx`)
- Delete: `painel/src/graficos/Treemap.tsx`, `painel/src/graficos/Sankey.tsx` (se nada mais importar o componente `Sankey`)
- Test: `painel/tests/formato.test.ts` (existente ou novo)

**Interfaces:**
- Produces: `formatarBRL(v: string | number): string` (Intl pt-BR BRL, espaço normal no lugar do NBSP, `"—"` se não numérico); `horaDe(iso: string): string | null` ("HH:MM" de `AAAA-MM-DDTHH:MM...`, null se não casar o padrão); `diaSP(n = 0): string` (`AAAA-MM-DD` em America/Sao_Paulo, o atual `diaLocal`). `quando(a)` de Atividades e Projetos passa a ser um só, exportado de `lib/formato.ts` como `quandoVence(vence_em: string | null, tem_hora: boolean)`.

- [ ] **Step 1: testes que falham**: `formatarBRL("1234.5") === "R$ 1.234,50"`, `formatarBRL("-1") === "-R$ 1,00"`, `formatarBRL("abc") === "—"`; `horaDe("2026-11-04T09:30:00") === "09:30"`, `horaDe("2026-11-04") === null`; `diaSP()` com `vi.setSystemTime(new Date("2026-11-05T01:00:00Z"))` → `"2026-11-04"`.
- [ ] **Step 2:** FAIL. **Step 3:** implementar e trocar os usos; `fmt` interno de `formato.ts` continua (valor absoluto é proposital em `originalEmReais`). `grep -rn "Treemap\|graficos/Sankey" painel/src painel/tests` vazio depois da mudança (ajustar o teste que afirma "sem botão Treemap" só se ele importar o arquivo).
- [ ] **Step 4:** `npx vitest run && npm run build` → PASS. **Step 5:** commit `refactor(painel): um formatador de R$ e de hora no fuso de São Paulo; remove Treemap e Sankey sem uso`.

### Task 11: Dependências declaradas e ruff (D4, D5)

**Files:**
- Modify: `pyproject.toml` (dependências e `[tool.ruff]`)
- Modify: arquivos que o ruff apontar
- Modify: `docs/STATUS.md` (linha de testes: comando do ruff)

- [ ] **Step 1:** listar imports de terceiros: `grep -rhoE "^(import|from) [a-zA-Z_]+" gabi tools | sort -u`, cruzar com `requirements.lock`. Declarar em `dependencies` cada pacote importado pelo código (nomes de distribuição, sem versão; ex.: `PyJWT`, `mcp`, `cryptography`, `python-multipart`, `httpx` se importado). `dev` += `ruff`.
- [ ] **Step 2:** instalar ruff só no `.venv` de desenvolvimento (`~/gabi-brain/.venv/bin/pip install ruff`), não no lock.
- [ ] **Step 3:** `[tool.ruff] line-length = 200`, `[tool.ruff.lint] select = ["F"]`; rodar `.venv/bin/ruff check gabi tools tests`.
- [ ] **Step 4:** corrigir os achados (import sem uso, variável sem uso, nome indefinido). Nome indefinido é bug: corrigir com teste se for alcançável. Re-exportações intencionais ganham `__all__` ou `# noqa: F401` com motivo.
- [ ] **Step 5:** `ruff check` → 0; `pytest -q` → PASS.
- [ ] **Step 6:** commit `chore: dependências declaradas no pyproject e ruff (pyflakes) sem erro`.

### Task 12: Documentação em dia (D6)

**Files:**
- Modify: `docs/STATUS.md` (cabeçalho "Estado em 04/11/2026"; despesas e projetos: mergeados e instalados em 27/10; Documentos instalado 25/10; nova linha "Revisão geral 04/11: branch `fix/revisao-geral`, aguardando ok"), `docs/HANDOFF.md` (remover as seções 1 e 3 vencidas; manter o que segue em aberto), `docs/BACKLOG.md` (DS1 e PJ1 fechados; item novo para o merge/instalação desta revisão)
- Create: `migrations/README.md`, `docs/adr/README.md` (uma linha cada: números pulados são faixas reservadas/ADRs não escritas; a aplicação das migrações é por nome de arquivo, em ordem)

- [ ] **Step 1:** editar; conferir cada afirmação no git (`git log`, `git branch --merged`) e em `ls /opt/gabi-brain/migrations` (só leitura).
- [ ] **Step 2:** commit `docs: status, handoff e backlog em dia (04/11); README dos números pulados`.

### Task 13: Verificação final e entrega (D7)

- [ ] **Step 1:** `pytest -q` completo (ler o resumo, não o exit code), `cd painel && npx vitest run && npm run build`, `.venv/bin/ruff check gabi tools tests`.
- [ ] **Step 2:** revisão da branch inteira (`superpowers:requesting-code-review`), corrigir o que for confirmado.
- [ ] **Step 3:** parar e pedir ao Ricardo, num resumo curto: (a) ok para merge na `main` e push; (b) ok para `sudo ~/instalar-brain.sh` (primeira instalação já com backup automático); (c) se apaga `feat/projetos-melhorias`. Nada disso sem o sim dele.
