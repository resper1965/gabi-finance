# Virada: do gabi-brain para o gabi-finance

**Para quem é:** o Ricardo, rodando como `root` na VPS (Ubuntu). O Claude guia (explica, confere a saída que você colar), mas **você** roda cada comando. Um passo de cada vez: só siga quando a verificação do passo bater. Todos os blocos são para colar inteiros num shell de root (`sudo -i`).

**O que muda.** O dinheiro (extratos, saldos, A pagar, projeção, gastos, notas, a receber, avisos financeiros) sai do `gabi-brain` e passa a viver no `gabi-finance`, com banco próprio (uma **cópia** do banco do brain), usuário próprio e portas próprias na mesma máquina. O `gabi-brain` **não é removido**: continua instalado e cuidando de agenda, e-mail, família e projetos; com `GABI_SEM_FINANCEIRO=1` ele só deixa de falar de dinheiro.

**Estado.** A virada ainda não aconteceu. Nada deste roteiro foi executado na VPS; os comandos foram escritos contra o código final e testados em banco de teste, não na máquina de produção. Por isso há uma verificação depois de cada passo e uma seção de volta no fim.

## Mapa

| Coisa | gabi-brain (hoje) | gabi-finance (depois) |
|---|---|---|
| Usuário do serviço | `gabibrain` | `gabifinance` (e `gabifinance-fontes` para a ponte do Nibo) |
| Código | `/opt/gabi-brain` | `/opt/gabi-finance` |
| Banco | `/var/lib/gabi-brain/gabi.db` | `/var/lib/gabi-finance/gabi.db` |
| Backups | `/var/backups/gabi-brain` | `/var/backups/gabi-finance` |
| Segredos | `/etc/gabi/*.env` | `/etc/gabi-finance/*.env` |
| Unidades | `gabi-brain-*` | `gabi-finance-*` |
| Painel | `https://gabi-brain.tail985643.ts.net` | `https://gabi-brain.tail985643.ts.net:8446` (mesma máquina, porta própria) |
| MCP para agentes externos | `https://gabi-brain.tail985643.ts.net:8443` | `https://gabi-brain.tail985643.ts.net:8447` (opcional; [runbook](runbook.md#servidor-mcp-e-tokens-de-agentes)) |
| MCP do Hermes | porta 8081, servidor `gabi_brain` | porta 8082, servidor `gabi_finance` |
| Token do Hermes | `GABI_BRAIN_TOKEN` | `GABI_FINANCE_TOKEN` (token **novo**) |

## Antes de começar (pré-requisitos)

1. **Snapshot da VPS e backup exportado** (gate G1): o instalador pede a confirmação e eu também: sem isso, não comece.
2. **Token novo do Nibo** em mãos (o atual expirou; as notas estão paradas desde pelo menos 09/11). Sem ele a virada funciona, só que as notas ficam paradas e a fonte responde `nao_configurada`.
3. **Uma janela de uns 60 minutos**, de preferência de manhã cedo, sem mexer no painel do brain durante ela (o que for decidido no brain depois da cópia do banco **não** vai para o finance).
4. **A branch `corte` já juntada na `main`** do gabi-finance (o passo 1 clona a `main`).
5. **O patch do brain instalado:** o `gabi-brain` instalado a partir da branch `sem-financeiro` com o instalador do brain (`sudo ~/instalar-brain.sh`, como hoje). Confirme o caminho do instalador no runbook do próprio brain (`docs/runbook.md#sem-financeiro` daquela branch) antes. Sozinho, o patch não muda nada: o brain só para de falar de dinheiro quando `GABI_SEM_FINANCEIRO=1` entra no passo 10. Verificação: `grep -c GABI_SEM_FINANCEIRO /opt/gabi-brain/gabi/sem_financeiro.py` imprime um número maior que 0.

Variáveis usadas em todos os passos (cole no começo da sessão de root; ajuste só as duas primeiras):

```bash
export HUSER=ricardo              # confirmado no passo 0
export LOGIN='seu-login@tailscale' # o login do Tailscale que entra como boss no painel
export PY=/opt/gabi-finance/venv/bin/python
export HOJE=$(TZ=America/Sao_Paulo date +%F)
export D=$(date +%F-%H%M)          # sufixo de todos os backups desta virada: anote-o
export HOME_H=$(getent passwd "$HUSER" | cut -d: -f6)
echo "HUSER=$HUSER HOME_H=$HOME_H D=$D HOJE=$HOJE"
```

Se a sessão de root cair, cole o bloco de novo **com o mesmo `D`** (`export D=<o anotado>`).

## Passo 0: confirmar quem é o usuário do Hermes e o estado de partida

O repositório sugere que o Hermes roda como `ricardo`, mas **confirme na máquina**, porque o `config.yaml`, o `.env`, o SOUL e as rotinas são do usuário que o roda:

```bash
systemctl show hermes-gateway -p User --value      # imprime o usuário; vazio = roda como root (pare e me avise)
ls -d /home/*/.hermes                              # deve listar a pasta do mesmo usuário
```

**Verificação:** os dois comandos apontam para o mesmo usuário. Se for outro que não `ricardo`, ajuste `HUSER` e cole de novo o bloco de variáveis. Depois confira que o brain está de pé e quais timers estão ligados (anote a lista, vale para a volta):

```bash
echo "$HOME_H"                                                    # a pasta do usuário do Hermes
systemctl is-active gabi-brain-api gabi-brain-mcp hermes-gateway   # três "active"
systemctl list-timers 'gabi-brain-*' --no-pager
ls -l /etc/gabi/brain.env /etc/gabi/telegram.env /etc/gabi/backup.pub 2>&1 | cut -c1-80
tailscale serve status                                            # anote: a 8443 é do brain; a 8446 e a 8447 NÃO podem aparecer
```

Se a 8446 ou a 8447 já aparecerem no `tailscale serve status`, **pare** e me diga o que está nelas.

## Passo 1: instalar (nada é ligado)

O repositório é privado: clone como root com o `gh` (se `gh auth status` disser que não está logado, rode `gh auth login` e `gh auth setup-git`; o token fica só no root). O clone vai para a pasta do usuário do Hermes, porque o passo 9 usa scripts dele.

```bash
gh auth status
if [ -d "$HOME_H/gabi-finance/.git" ]; then
  git -c safe.directory="$HOME_H/gabi-finance" -C "$HOME_H/gabi-finance" fetch origin
  git -c safe.directory="$HOME_H/gabi-finance" -C "$HOME_H/gabi-finance" switch main
  git -c safe.directory="$HOME_H/gabi-finance" -C "$HOME_H/gabi-finance" pull --ff-only origin main
else
  gh repo clone resper1965/gabi-finance "$HOME_H/gabi-finance" -- --branch main
fi
chown -R "$HUSER": "$HOME_H/gabi-finance"
sudo -u "$HUSER" -H bash -c 'cd ~/gabi-finance/painel && npm ci && npm run build'
cd "$HOME_H/gabi-finance" && git -c safe.directory="$PWD" log --oneline -1 && ls gabi/painel/index.html
bash deploy/instalar.sh --confirmo-backup-exportado
```

**Verificação:**

```bash
id gabifinance gabifinance-fontes                       # os dois usuários existem
ls -l /opt/gabi-finance /etc/gabi-finance               # código e pasta de segredos (vazia)
ls /opt/gabi-finance/migrations | tail -1               # 0092_limpar_herdados.sql
systemctl list-unit-files 'gabi-finance-*' --no-pager   # "disabled" para as que têm [Install]; "static" para as oneshot sem [Install] e o falha@
systemctl list-unit-files 'gabi-finance-*' --no-pager | grep -c enabled   # 0
systemctl is-active gabi-finance-api                    # "inactive"
ss -ltn | grep -E ':8082' || echo "8082 livre"          # o MCP do brain segue na 8081; a 8082 ainda livre
```

## Passo 2: segredos em `/etc/gabi-finance/`

Os segredos **não** vão para o repositório nem aparecem na tela. Crie os arquivos assim (modo 600, `root:root`; o systemd os lê como root):

```bash
umask 077
grep '^MCPAI_KEY=' /etc/gabi/brain.env > /etc/gabi-finance/mcpai.env
read -rsp "Cole o token NOVO do Nibo e tecle Enter: " T; echo; printf 'NIBO_TOKEN=%s\n' "$T" > /etc/gabi-finance/nibo.env; unset T
if [ -f /etc/gabi/backup.pub ]; then install -m 644 /etc/gabi/backup.pub /etc/gabi-finance/backup.pub; fi
chown root:root /etc/gabi-finance/*; chmod 600 /etc/gabi-finance/*.env
```

O `telegram.env` é do passo 11: **não** o crie agora.

**Verificação** (sem mostrar o conteúdo):

```bash
ls -l /etc/gabi-finance/                               # mcpai.env e nibo.env com -rw------- root root
grep -c '^MCPAI_KEY=.' /etc/gabi-finance/mcpai.env      # 1
grep -c '^NIBO_TOKEN=.' /etc/gabi-finance/nibo.env      # 1
```

## Passo 3: parar o dinheiro no brain e copiar o banco

Pare **só os timers** de dinheiro do brain (uma rodada em andamento termina sozinha; não a interrompa: a de extratos pode levar até 30 minutos):

```bash
systemctl stop gabi-brain-extratos.timer gabi-brain-saldos.timer gabi-brain-notas.timer
ocupado() { for u in extratos saldos notas; do case "$(systemctl show -p ActiveState --value gabi-brain-$u.service)" in inactive|failed) ;; *) return 0;; esac; done; return 1; }
while ocupado; do
  echo "$(date +%T) rodada do brain em andamento; esperando..."; sleep 30
done
systemctl is-active gabi-brain-extratos.timer gabi-brain-saldos.timer gabi-brain-notas.timer gabi-brain-extratos.service gabi-brain-saldos.service gabi-brain-notas.service
```

**Verificação:** a última linha imprime seis `inactive` (um `.service` pode aparecer `failed`: me avise antes de seguir; `activating` = rodada ainda em andamento: rode o laço de novo).

Confira que o banco do brain está na versão que o gabi-finance espera (as migrações 0090 a 0092 do finance partem dela):

```bash
runuser -u gabibrain -- python3 -c "
import sqlite3
c = sqlite3.connect('file:/var/lib/gabi-brain/gabi.db?mode=ro', uri=True)
print(c.execute('select max(nome) from schema_versao').fetchone()[0])
"
```

**Verificação:** imprime `0089_projeto_linear.sql`. Qualquer outro valor: **pare** e me diga.

Agora a cópia consistente do banco (API de backup do SQLite, que lê um retrato consistente mesmo com o brain escrevendo em WAL; **nunca `cp`**). Ela roda como o dono do banco do brain, grava em `/tmp` e depois você a coloca no lugar:

```bash
runuser -u gabibrain -- python3 - /tmp/gabi-virada.db <<'PY'
import os, sqlite3, sys
os.umask(0o077)
src = sqlite3.connect("/var/lib/gabi-brain/gabi.db")
dst = sqlite3.connect(sys.argv[1])
src.backup(dst)
dst.execute("pragma journal_mode=delete")
ok = dst.execute("pragma integrity_check").fetchone()[0]
dst.close(); src.close()
print("integridade:", ok)
sys.exit(0 if ok == "ok" else "cópia com problema: " + ok)
PY
rm -f /var/lib/gabi-finance/gabi.db-wal /var/lib/gabi-finance/gabi.db-shm
install -o gabifinance -g gabifinance -m 600 /tmp/gabi-virada.db /var/backups/gabi-finance/gabi-brain-copia-pre-migracao.db
install -o gabifinance -g gabifinance -m 600 /tmp/gabi-virada.db /var/lib/gabi-finance/gabi.db
rm -f /tmp/gabi-virada.db
ls -l /var/backups/gabi-finance/gabi-brain-copia-pre-migracao.db /var/lib/gabi-finance/gabi.db*
```

**Verificação:** a saída traz `integridade: ok`; o `ls` mostra só os dois arquivos (sem `-wal`/`-shm`), ambos `gabifinance` e `-rw-------`; e o `/tmp/gabi-virada.db` sumiu. A cópia `...pre-migracao.db` fica como referência intocada para a conferência (passo 5) e para a volta.

## Passo 4: migrar a cópia e limpar os tokens herdados

Aplica as migrações do corte: 0090 derruba as tabelas das áreas que saíram; 0091 derruba `pet`, `allowlist_vip` e `memoria`; 0092 limpa as linhas herdadas que o finance não usa (avisos não financeiros e de unidades do brain, perguntas com efeito que o finance não conhece, telefone e dados pessoais de `pessoa` fora do que o dinheiro usa, agenda passada ou privada, parâmetros dos módulos que saíram e o `mcp.url` do brain; detalhes em [`dados.md`](dados.md)):

```bash
cd /opt/gabi-finance
runuser -u gabifinance -- ./venv/bin/python -c "
from pathlib import Path
from gabi.db import conectar, migrar
c = conectar(Path('/var/lib/gabi-finance/gabi.db'))
print('aplicadas:', migrar(c, Path('migrations')))
print('ultima:', c.execute('select max(nome) from schema_versao').fetchone()[0])
print('integridade:', c.execute('pragma integrity_check').fetchone()[0])
print('tabelas que saíram ainda existem?', c.execute(\"select count(*) from sqlite_master where name in ('pet','allowlist_vip','memoria','projeto','documento')\").fetchone()[0])
print('pessoas com telefone:', c.execute('select count(*) from pessoa where telefone is not null').fetchone()[0])
print('mcp.url:', c.execute(\"select count(*) from parametro where chave='mcp.url'\").fetchone()[0])
"
```

**Verificação:** `aplicadas:` lista `0090_corte_financeiro.sql`, `0091_minimizar_dados.sql` e `0092_limpar_herdados.sql`; `ultima: 0092_limpar_herdados.sql`; `integridade: ok`; as três contagens dão `0`. (Se `aplicadas` vier vazia e `ultima` for a 0092, o banco já estava migrado: normal numa segunda tentativa.)

A cópia trouxe os **tokens de agentes** do brain (só o hash). Revogue todos no finance (ADR-036): o token novo do Hermes sai no passo 9, e **cada agente externo** que você usava com o brain (Claude Code, Cursor...) precisa de uma chave **nova** emitida no painel do finance se for usar o dinheiro por ele. Isto só mexe no banco do finance; o brain segue com os dele:

```bash
cd /opt/gabi-finance
runuser -u gabifinance -- $PY -m gabi.mcp.tokens --banco /var/lib/gabi-finance/gabi.db listar
for id in $(runuser -u gabifinance -- $PY -m gabi.mcp.tokens --banco /var/lib/gabi-finance/gabi.db listar | awk '$NF=="ativo"{print $1}'); do
  runuser -u gabifinance -- $PY -m gabi.mcp.tokens --banco /var/lib/gabi-finance/gabi.db revogar "$id"
done
runuser -u gabifinance -- $PY -m gabi.mcp.tokens --banco /var/lib/gabi-finance/gabi.db listar | grep -c ' ativo$' || true    # 0
```

**Verificação:** a última linha imprime `0`.

## Passo 5: conferência lado a lado (antes de qualquer rodada nova)

Este é o passo que diz se o dinheiro **bateu**. O mesmo programa (`tools/conferir_virada.py`, só leitura) lê a cópia **antes** de migrar e o banco **depois** de migrar, com a mesma data, e a saída tem de ser idêntica. Como ainda não houve rodada nova, qualquer diferença é falha do corte, não dado novo. Rode como `gabifinance` (nunca como root).

```bash
cd /opt/gabi-finance
runuser -u gabifinance -- $PY -m tools.conferir_virada --banco /var/backups/gabi-finance/gabi-brain-copia-pre-migracao.db --hoje "$HOJE" > /tmp/conf-antes.txt
runuser -u gabifinance -- $PY -m tools.conferir_virada --banco /var/lib/gabi-finance/gabi.db --hoje "$HOJE" > /tmp/conf-depois.txt
diff /tmp/conf-antes.txt /tmp/conf-depois.txt && echo "BATEU: sem diferença"
cat /tmp/conf-depois.txt
```

A saída traz três blocos: **saldos por conta** (com total e faturas abertas), **a pagar do mês** (aberto, atrasado e a conferir, com total e quantos estão sem valor) e a **projeção de caixa de 30 dias** (com o menor saldo). **Verificação:** o `diff` não imprime nada e aparece `BATEU: sem diferença`. Cole-me o `conf-depois.txt` para eu olhar se os números fazem sentido para você.

**Conferência mais forte (opcional):** o **código do brain** lendo a cópia antes de migrar contra o código do finance lendo o banco migrado. Se der erro de import, me cole a mensagem; a conferência acima continua valendo.

```bash
cd /tmp && runuser -u gabifinance -- env PYTHONPATH=/opt/gabi-brain /opt/gabi-brain/venv/bin/python /opt/gabi-finance/tools/conferir_virada.py --banco /var/backups/gabi-finance/gabi-brain-copia-pre-migracao.db --hoje "$HOJE" > /tmp/conf-brain.txt && diff /tmp/conf-brain.txt /tmp/conf-depois.txt && echo "BATEU com o código do brain"
```

**Se não bater: pare aqui.** Não ligue nada. A volta é a seção "Volta", item 2 (religar os timers do brain); o brain não foi alterado.

## Passo 6: ligar a ponte, a API e o MCP

Nesta ordem (a API e o MCP falam com a ponte):

```bash
systemctl enable --now gabi-finance-fontes
systemctl enable --now gabi-finance-api gabi-finance-mcp
```

**Verificação:**

```bash
systemctl is-active gabi-finance-fontes gabi-finance-api gabi-finance-mcp        # três "active"
ls -ld /run/gabi-finance                                                          # drwx------ gabifinance
curl -s --unix-socket /run/gabi-finance/api.sock http://localhost/api/eu -H "Tailscale-User-Login: $LOGIN"; echo   # {"login":...,"nivel":"boss"}
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8082/mcp          # 401 (sem token não entra)
ss -ltnp | grep -E 'gabi-finance|uvicorn' | grep -v '127.0.0.1:8082' || echo "nenhuma porta TCP da API"
```

Se `/api/eu` não devolver `"nivel":"boss"`, o seu login não está em `acesso` na cópia: me diga o que saiu.

## Passo 7: expor o painel no Tailscale (porta 8446)

Mesma máquina do brain, porta própria. A 8443 já é do MCP externo do brain e **não** é tocada. Primeiro confira que a 8446 está livre:

```bash
tailscale serve status
tailscale serve status | grep -q ':8446' && echo "PARE: a 8446 já está em uso" || echo "8446 livre"
```

Se imprimir `PARE`, não siga: me cole o `tailscale serve status`. Com a porta livre:

```bash
tailscale serve --bg --https=8446 unix:/run/gabi-finance/api.sock
tailscale serve status        # aparece https://gabi-brain.tail985643.ts.net:8446 -> unix:/run/gabi-finance/api.sock; o que já existia continua igual
```

O `tailscale serve` termina o TLS e injeta o cabeçalho de identidade `Tailscale-User-Login`; a API só escuta no socket. A unidade da API já confia na origem `https://gabi-brain.tail985643.ts.net:8446` (com a porta: a API compara a origem exatamente).

**Verificação (de outro aparelho na sua tailnet):** abrir `https://gabi-brain.tail985643.ts.net:8446/api/eu` mostra o **seu login** e `"nivel":"boss"`, e o painel em `https://gabi-brain.tail985643.ts.net:8446/` abre e carrega o Caixa, com o "dados até" da data da cópia. **Se a resposta vier sem o seu login (anônimo) ou 403, pare** e me avise: sem identidade o painel não deve ser usado (R3); desfaça com `tailscale serve --https=8446 off`. O painel do brain (`https://gabi-brain.tail985643.ts.net`, sem porta) continua igual.

## Passo 8: a primeira rodada de verdade e os timers

Rode uma rodada de cada, à mão, **antes** de ligar os timers. As duas do mcp.ai chamam o provedor de verdade:

```bash
systemctl start gabi-finance-saldos
journalctl -u gabi-finance-saldos -n 20 --no-pager -o cat
systemctl start gabi-finance-extratos        # pode levar vários minutos (limite de 30 min)
journalctl -u gabi-finance-extratos -n 30 --no-pager -o cat
systemctl start gabi-finance-notas           # precisa do token novo do Nibo
journalctl -u gabi-finance-notas -n 20 --no-pager -o cat
```

**Verificação:** sem `sem_chave` nem `nao_configurada` nos logs, e a última rodada de extratos terminou **conferida**:

```bash
cd /opt/gabi-finance
runuser -u gabifinance -- $PY -c "
import sqlite3
c = sqlite3.connect('file:/var/lib/gabi-finance/gabi.db?mode=ro', uri=True)
for r in c.execute(\"select id, fonte, inicio, fim, status, lidos, novos, conferida from rodada order by id desc limit 4\"): print(r)
"
```

Esperado: a rodada `open-finance` mais recente com `status` `ok` e `conferida` = 1. Se a rodada de extratos terminar **não conferida**, não ligue os timers: me cole as linhas do `conferencia` dessa rodada. Se só o Nibo falhar (token), o resto do dinheiro segue válido; trate o token e repita `gabi-finance-notas` depois.

Com as rodadas boas, ligue os timers (o do Telegram fica para o passo 11):

```bash
systemctl enable --now gabi-finance-saldos.timer gabi-finance-extratos.timer gabi-finance-notas.timer gabi-finance-avisos.timer gabi-finance-backup.timer
if [ -f /etc/gabi-finance/backup.pub ]; then systemctl enable --now gabi-finance-exportacao.timer; else echo "sem backup.pub: exportação semanal fica desligada (veja runbook#backup-fora)"; fi
systemctl list-timers 'gabi-finance-*' --no-pager
```

**Verificação:** `list-timers` mostra os timers com a próxima execução (saldos aos :05, extratos 06:00/14:00, notas 06:40, avisos a cada 15 min, backup 03:30).

## Passo 9: o Hermes passa a usar o gabi_finance para o dinheiro

O Hermes ganha um token **novo** e um segundo servidor MCP; o `gabi_brain` continua para todo o resto. Tudo isto é no usuário do Hermes (os comandos usam `sudo -u "$HUSER"` para os arquivos continuarem dele), e **eu não vejo o token**: ele vai direto para o `.env`.

**9.1 Backups do Hermes** (são a volta):

```bash
sudo -u "$HUSER" cp -p "$HOME_H/.hermes/config.yaml" "$HOME_H/.hermes/config.yaml.bak-antes-finance-$D"
sudo -u "$HUSER" cp -p "$HOME_H/.hermes/.env" "$HOME_H/.hermes/.env.bak-antes-finance-$D"
sudo -u "$HUSER" cp -p "$HOME_H/.hermes/cron/jobs.json" "$HOME_H/.hermes/cron/jobs.json.bak-antes-finance-$D"
ls -l "$HOME_H"/.hermes/*.bak-antes-finance-"$D" "$HOME_H"/.hermes/cron/*.bak-antes-finance-"$D"
```

**Verificação:** o `ls` lista os três backups. (O do SOUL é feito pelo próprio script no 9.4.)

**9.2 Emitir o token e gravá-lo no `.env`** sem imprimir (idempotente: tira uma linha antiga e garante a quebra de linha no fim antes de acrescentar):

```bash
cd /opt/gabi-finance
F="$HOME_H/.hermes/.env"
TOKEN=$(runuser -u gabifinance -- $PY -m gabi.mcp.tokens --banco /var/lib/gabi-finance/gabi.db emitir hermes fin,trabalho,propostas,pedidos,decisoes | tail -n 1)
sudo -u "$HUSER" sed -i '/^GABI_FINANCE_TOKEN=/d' "$F"
if [ -n "$(tail -c1 "$F")" ]; then echo | sudo -u "$HUSER" tee -a "$F" >/dev/null; fi
printf 'GABI_FINANCE_TOKEN=%s\n' "$TOKEN" | sudo -u "$HUSER" tee -a "$F" >/dev/null; unset TOKEN
grep -c '^GABI_FINANCE_TOKEN=.' "$F"                       # 1
stat -c '%U %a' "$F"                                       # o usuário do Hermes e as permissões de antes
runuser -u gabifinance -- $PY -m gabi.mcp.tokens --banco /var/lib/gabi-finance/gabi.db listar | grep -c ' ativo$'   # 1 (só o do Hermes)
```

**9.3 `config.yaml`.** Abra o arquivo (`sudo -u "$HUSER" nano "$HOME_H/.hermes/config.yaml"`) e faça duas coisas em `mcp_servers`:

(a) Acrescente o servidor novo, com a lista **exata** de [`fontes/hermes.md`](fontes/hermes.md) (33 ferramentas, sem curinga; copie o bloco de lá, ou do clone: `less $HOME_H/gabi-finance/docs/fontes/hermes.md`):

```yaml
mcp_servers:
  gabi_finance:
    url: http://127.0.0.1:8082/mcp
    headers:
      Authorization: Bearer ${GABI_FINANCE_TOKEN}
    tools:
      include:
      # ... as 33 ferramentas de docs/fontes/hermes.md
```

(b) No servidor antigo `gabi_brain`, tire do `include` **só as 28 ferramentas de dinheiro** listadas em [`fontes/hermes.md`](fontes/hermes.md#o-que-sai-do-gabi_brain-na-virada) (bloco "tirar do include do gabi_brain"). `avisos_abertos`, `resumo_manha`, `decisoes_abertas`, `decisoes_recentes` e `decisao_responder` **ficam** no `gabi_brain` (existem nos dois). As ferramentas não financeiras do brain ficam como estão.

Confira com o Python que tem PyYAML (o `python3` do sistema ou o do Hermes):

```bash
HPY=python3; sudo -u "$HUSER" -H $HPY -c 'import yaml' 2>/dev/null || HPY=$(sed -n '1s/^#!//p' "$(sudo -u "$HUSER" -H bash -lc 'command -v hermes')")
echo "python: $HPY"
sudo -u "$HUSER" -H $HPY - "$HOME_H/.hermes/config.yaml" "$HOME_H/gabi-finance/docs/fontes/hermes.md" <<'PY'
import re, sys, yaml
cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
doc = open(sys.argv[2], encoding="utf-8").read()
fin = re.findall(r"^      - (\w+)$", doc, re.M)
tirar = re.findall(r"^- (\w+)$", doc.split("# tirar do include do gabi_brain:")[1].split("```")[0], re.M)
s = cfg["mcp_servers"]
print("servidores:", sorted(s))
inc_f = s["gabi_finance"]["tools"]["include"]
print("gabi_finance igual à lista (33):", sorted(inc_f) == sorted(fin), len(inc_f))
inc_b = (s["gabi_brain"].get("tools") or {}).get("include")
if inc_b is None:
    print("ATENÇÃO: gabi_brain sem include explícito: pare e me avise")
else:
    print("gabi_brain ainda com dinheiro:", sorted(set(inc_b) & set(tirar)) or "nenhuma")
    print("nos dois servidores:", sorted(set(inc_b) & set(inc_f)))
PY
```

**Verificação:** `servidores` lista `gabi_brain` e `gabi_finance`; `gabi_finance igual à lista (33): True 33`; `gabi_brain ainda com dinheiro: nenhuma`; `nos dois servidores` mostra só (algumas de) `avisos_abertos`, `decisao_responder`, `decisoes_abertas`, `decisoes_recentes`, `resumo_manha`. Erro de YAML: corrija a indentação e rode de novo.

**9.4 SOUL: editar, não substituir.** O script guarda `SOUL.md.bak-antes-finance-$D`, põe o prefixo `mcp__gabi_finance__` nas 28 ferramentas de dinheiro (só dentro de crases; as que existem nos dois servidores não mudam) e acrescenta uma seção curta "Dinheiro". Todo o resto do SOUL (agenda, e-mail, família, projetos, jeito da Gabi) fica igual. Rodar de novo não muda nada.

```bash
sudo -u "$HUSER" -H python3 "$HOME_H/gabi-finance/deploy/hermes/editar_soul.py" --data "$D"
diff "$HOME_H/.hermes/SOUL.md.bak-antes-finance-$D" "$HOME_H/.hermes/SOUL.md" | grep -c '^>'      # linhas mudadas (> 0)
grep -c 'mcp__gabi_finance__' "$HOME_H/.hermes/SOUL.md"                                          # > 0
grep -c 'Dinheiro (gabi_finance):' "$HOME_H/.hermes/SOUL.md"                                      # 1
sudo -u "$HUSER" -H python3 "$HOME_H/gabi-finance/deploy/hermes/editar_soul.py" --data "$D"      # "SOUL já editado: nada a mudar"
```

**Verificação:** a primeira execução imprime `backup:` e `SOUL editado: N nomes...`; a segunda, `SOUL já editado: nada a mudar`. Se quiser, me cole o `diff` inteiro para eu conferir.

**9.5 Reiniciar e abrir conversa nova:**

```bash
systemctl restart hermes-gateway
sleep 5; systemctl is-active hermes-gateway                # active
```

Depois mande `/new` no Telegram **e** no WhatsApp.

**Verificação:** peça ao Hermes "qual é o meu saldo?". A resposta vem com os saldos, e aparece uma chamada nova `financeiro_saldo` `ok` no MCP do finance:

```bash
cd /opt/gabi-finance
runuser -u gabifinance -- $PY -c "
import sqlite3
c = sqlite3.connect('file:/var/lib/gabi-finance/gabi.db?mode=ro', uri=True)
for r in c.execute('select quando, ferramenta, status from chamada_mcp order by id desc limit 5'): print(r)
"
```

**9.6 Rotinas agendadas do Hermes.** Algumas rotinas falam de dinheiro com o brain (porta 8081, `GABI_BRAIN_TOKEN` ou ferramentas `financeiro_*`). Liste e procure:

```bash
sudo -u "$HUSER" -H hermes cron list
grep -nE '8081|GABI_BRAIN_TOKEN|fechamento_dia|financeiro_' "$HOME_H"/.hermes/scripts/* 2>/dev/null
sudo -u "$HUSER" -H python3 - <<'PY'
import json, os, re
d = json.load(open(os.path.expanduser("~/.hermes/cron/jobs.json"), encoding="utf-8"))
jobs = d.get("jobs", d) if isinstance(d, dict) else d
jobs = list(jobs.values()) if isinstance(jobs, dict) else jobs
pad = re.compile(r"8081|GABI_BRAIN_TOKEN|fechamento_dia|financeiro_\w+|resumo_manha|despesa\w*|assinatura\w*|olhar_a_frente|agenda_financeira")
for j in jobs:
    t = json.dumps(j, ensure_ascii=False)
    if pad.search(t):
        print("==", j.get("name") or j.get("id"), "| script:", j.get("script"), "| achados:", sorted(set(pad.findall(t))))
        print("   prompt:", (j.get("prompt") or "")[:300])
PY
```

Cole-me a saída. O esperado é aparecerem `fechamento-noturno` (script `fechamento_dia.py`), `resumo-manha` e o `vigia_semanal.py` do brain (este fica como está: o passo 10 cuida dele). Para os dois primeiros:

**fechamento-noturno** (script sem modelo): passa a chamar o MCP do finance com o token do finance.

```bash
S="$HOME_H/.hermes/scripts/fechamento_dia.py"
sudo -u "$HUSER" cp -p "$S" "$S.bak-antes-finance-$D"
sudo -u "$HUSER" sed -i 's#127\.0\.0\.1:8081#127.0.0.1:8082#g; s#GABI_BRAIN_TOKEN#GABI_FINANCE_TOKEN#g' "$S"
grep -nE '808[12]|GABI_(BRAIN|FINANCE)_TOKEN' "$S"          # só 8082 e GABI_FINANCE_TOKEN
sudo -u "$HUSER" -H python3 "$S" | head -8                  # o fechamento do dia, sem erro
```

**resumo-manha** (rotina com modelo): o prompt passa a pedir os dois resumos e juntar, dinheiro primeiro.

```bash
sudo -u "$HUSER" -H hermes cron edit resumo-manha --prompt "Resumo da manhã: chame mcp__gabi_finance__resumo_manha e mcp__gabi_brain__resumo_manha e junte numa mensagem só, dinheiro primeiro. Repasse as linhas como vierem; se alguma vier com aviso de dados desatualizados, ele vai na primeira linha. Se uma das duas falhar, diga em uma linha qual falhou e mande a outra."
sudo -u "$HUSER" -H hermes cron list | grep -A3 resumo-manha
```

Se o prompt antigo (impresso acima) tinha alguma instrução sua além de chamar o `resumo_manha`, me cole antes: eu junto as duas coisas. Se aparecer **outra** rotina com dinheiro (por exemplo `forecast-semanal` ou `resumo-semanal-pagamentos`), me cole o prompt dela: a troca é a mesma (`mcp__gabi_brain__<ferramenta de dinheiro>` vira `mcp__gabi_finance__<ferramenta>`), com `hermes cron edit <nome> --prompt "..."`.

**Verificação:** `sudo -u "$HUSER" -H hermes cron run resumo-manha` e o resumo chega com o dinheiro do finance (sem "dados desatualizados" do brain).

**9.7 (opcional, endurecimento)** O token do Hermes no **brain** ainda tem os escopos de dinheiro (`fin` e `propostas`, que no brain só cobre `classificar_lancamento` e `regras_sugerir`). Para o brain não aceitar mais dinheiro desse token, anote os escopos atuais e tire os dois (o segredo não muda; na volta, devolva os anotados):

```bash
cd /opt/gabi-brain
runuser -u gabibrain -- ./venv/bin/python -m gabi.mcp.tokens --banco /var/lib/gabi-brain/gabi.db listar     # anote o id e os escopos do token do Hermes
# runuser -u gabibrain -- ./venv/bin/python -m gabi.mcp.tokens --banco /var/lib/gabi-brain/gabi.db escopos <id> <os escopos anotados, sem fin e sem propostas>
```

## Passo 10: o brain para de falar de dinheiro (sem remover)

Pré-requisito: o patch da branch `sem-financeiro` do brain instalado (ver "Antes de começar", item 5). O que o flag faz está no runbook do brain (`docs/runbook.md#sem-financeiro`, na branch `sem-financeiro`): o brain deixa de criar e de enviar avisos de dinheiro, tira o dinheiro do resumo da manhã, do frescor e das decisões abertas. Agenda, e-mail, família e projetos seguem iguais.

Primeiro impeça que os timers de dinheiro do brain voltem num reinício da máquina (estão parados desde o passo 3):

```bash
systemctl disable gabi-brain-extratos.timer gabi-brain-saldos.timer gabi-brain-notas.timer
systemctl is-enabled gabi-brain-extratos.timer gabi-brain-saldos.timer gabi-brain-notas.timer    # três "disabled"
```

Agora o flag, por drop-in (um arquivo com nome próprio em cada unidade, para a volta apagar só ele):

```bash
for u in api mcp avisos telegram; do
  install -d "/etc/systemd/system/gabi-brain-$u.service.d"
  printf '[Service]\nEnvironment=GABI_SEM_FINANCEIRO=1\n' > "/etc/systemd/system/gabi-brain-$u.service.d/gabi-sem-financeiro.conf"
done
systemctl daemon-reload
systemctl restart gabi-brain-api gabi-brain-mcp
for u in api mcp avisos telegram; do
  systemctl show "gabi-brain-$u.service" -p Environment | grep -q 'GABI_SEM_FINANCEIRO=1' && echo "gabi-brain-$u: ok" || echo "gabi-brain-$u: FALTA"
done
systemctl is-active gabi-brain-api gabi-brain-mcp          # dois "active"
```

(`avisos` e `telegram` do brain são rodadas de timer: pegam o flag na próxima execução.)

O vigia semanal do brain é um script do Hermes e lê o flag do ambiente do Hermes; ponha-o no `.env` do Hermes (idempotente) e reinicie o gateway:

```bash
F="$HOME_H/.hermes/.env"
sudo -u "$HUSER" sed -i '/^GABI_SEM_FINANCEIRO=/d' "$F"
if [ -n "$(tail -c1 "$F")" ]; then echo | sudo -u "$HUSER" tee -a "$F" >/dev/null; fi
echo 'GABI_SEM_FINANCEIRO=1' | sudo -u "$HUSER" tee -a "$F" >/dev/null
grep -c '^GABI_SEM_FINANCEIRO=1$' "$F"                     # 1
systemctl restart hermes-gateway; sleep 5; systemctl is-active hermes-gateway
```

**Verificação:** as quatro linhas `gabi-brain-<u>: ok`; e a lista de avisos do brain sem nenhum tipo de dinheiro:

```bash
curl -s --unix-socket /run/gabi-brain/api.sock http://localhost/api/v1/avisos -H "Tailscale-User-Login: $LOGIN" | python3 -c "
import json, sys
itens = json.load(sys.stdin)['dados']['itens']
din = {'rodada_parada','saldo_divergente','banco_desatualizado','conta_atrasada','cobrada_apos_cancelar','vence_hoje','vence_em_breve','valor_diferente','lancamento_sem_conversao'}
print('avisos de dinheiro no brain:', sorted({i['tipo'] for i in itens if i['tipo'] in din}) or 'nenhum')
"
```

Esperado: `avisos de dinheiro no brain: nenhum`. (Se o socket da API do brain tiver outro caminho, veja `systemctl cat gabi-brain-api | grep uds`.)

## Passo 11: Telegram do finance (obrigatório)

Com o brain calado sobre dinheiro (passo 10), quem avisa dinheiro no Telegram passa a ser o `gabi-finance-telegram`. Sem este passo, os avisos de dinheiro deixam de chegar. Use o mesmo bot e o mesmo chat do brain:

```bash
umask 077
grep -E '^(TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID)=' /etc/gabi/telegram.env > /etc/gabi-finance/telegram.env
chown root:root /etc/gabi-finance/telegram.env; chmod 600 /etc/gabi-finance/telegram.env
grep -cE '^(TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID)=.' /etc/gabi-finance/telegram.env    # 2
systemctl enable --now gabi-finance-telegram.timer
systemctl start gabi-finance-telegram
journalctl -u gabi-finance-telegram -n 20 --no-pager -o cat
```

**Verificação:** o `grep -c` dá `2`; `ls -l /etc/gabi-finance/telegram.env` mostra `-rw------- root root`; o `journal` traz só contagens (enviados, descartados), sem erro; `systemctl list-timers gabi-finance-telegram.timer --no-pager` mostra a próxima execução (a cada 5 minutos).

## Passo 12: aceite nas primeiras 24 horas

- `systemctl --failed | grep gabi-finance` vazio.
- Amanhã, depois das 06:00 e 06:40: as rodadas de extratos e de notas do dia aparecem em `rodada` e a mais recente de extratos está conferida.
- O resumo das 07:05 chega pelo Hermes, com o dinheiro do finance primeiro e o resto do brain depois.
- No painel (`:8446`), Caixa › A pagar mostra "dados até" de hoje e o **mesmo A pagar do mês** do passo 5 (mais o que a rodada trouxe de novo).
- `chamada_mcp` mostra chamadas `ok` do token do Hermes.
- Os avisos de dinheiro chegam no Telegram **uma vez só** (do finance).
- O backup das 03:30 gravou um arquivo novo em `/var/backups/gabi-finance/` e a rodada `backup` está `ok`.

Depois de uma semana sem problema, o brain pode deixar de ser mantido para o dinheiro (a remoção dele é decisão da etapa 3, não daqui).

## Volta (rollback)

A volta é segura em qualquer ponto **porque o banco do brain não foi alterado** (só ficou parado) e tudo o que mudou fora do finance tem backup datado com o sufixo `$D` ou é um arquivo próprio da virada. O que se perde numa volta: o que você tiver decidido **no finance** nesse intervalo (decisões, classificações, A pagar marcado como pago), que não volta para o brain. As rodadas que o brain não fez durante a janela, a próxima captura dele pega (a leitura é incremental).

Faça na ordem; pule o que você ainda não tinha feito. Use o `D` anotado (`ls "$HOME_H"/.hermes/*.bak-antes-finance-*` mostra qual é).

**1. Parar o finance e tirar a porta do Tailscale** (passos 6 a 8 e 11):

```bash
systemctl disable --now gabi-finance-saldos.timer gabi-finance-extratos.timer gabi-finance-notas.timer gabi-finance-avisos.timer gabi-finance-backup.timer gabi-finance-exportacao.timer gabi-finance-telegram.timer 2>/dev/null
systemctl stop 'gabi-finance-*.service'
systemctl disable gabi-finance-fontes gabi-finance-api gabi-finance-mcp 2>/dev/null
rm -f /etc/gabi-finance/telegram.env
tailscale serve --https=8446 off
tailscale serve --https=8447 off 2>/dev/null   # só se você expôs o MCP externo do finance
systemctl list-units 'gabi-finance-*' --state=active --no-pager      # vazio
tailscale serve status                                                # sem 8446 nem 8447; o resto igual ao do passo 0
```

**2. Religar o dinheiro no brain** (passos 3 e 10):

```bash
rm -f /etc/systemd/system/gabi-brain-{api,mcp,avisos,telegram}.service.d/gabi-sem-financeiro.conf
systemctl daemon-reload
systemctl restart gabi-brain-api gabi-brain-mcp
for u in api mcp avisos telegram; do systemctl show "gabi-brain-$u.service" -p Environment | grep -q GABI_SEM_FINANCEIRO && echo "gabi-brain-$u: AINDA COM FLAG" || echo "gabi-brain-$u: sem flag"; done
systemctl enable --now gabi-brain-extratos.timer gabi-brain-saldos.timer gabi-brain-notas.timer
systemctl list-timers 'gabi-brain-*' --no-pager                       # os três de volta, com próxima execução
systemctl start gabi-brain-saldos                                     # atualiza os saldos já
```

Se você fez o 9.7, devolva ao token do Hermes no brain os escopos anotados (`... gabi.mcp.tokens --banco /var/lib/gabi-brain/gabi.db escopos <id> <escopos anotados>`).

**3. Restaurar o Hermes** (passos 9 e 10; com o gateway parado, para ele não regravar as rotinas):

```bash
systemctl stop hermes-gateway
sudo -u "$HUSER" cp -p "$HOME_H/.hermes/config.yaml.bak-antes-finance-$D" "$HOME_H/.hermes/config.yaml"
sudo -u "$HUSER" cp -p "$HOME_H/.hermes/.env.bak-antes-finance-$D" "$HOME_H/.hermes/.env"
sudo -u "$HUSER" cp -p "$HOME_H/.hermes/SOUL.md.bak-antes-finance-$D" "$HOME_H/.hermes/SOUL.md"
sudo -u "$HUSER" cp -p "$HOME_H/.hermes/cron/jobs.json.bak-antes-finance-$D" "$HOME_H/.hermes/cron/jobs.json"
S="$HOME_H/.hermes/scripts/fechamento_dia.py"; if [ -f "$S.bak-antes-finance-$D" ]; then sudo -u "$HUSER" cp -p "$S.bak-antes-finance-$D" "$S"; fi
grep -cE '^(GABI_FINANCE_TOKEN|GABI_SEM_FINANCEIRO)=' "$HOME_H/.hermes/.env" || true    # 0
grep -c 'mcp__gabi_finance__' "$HOME_H/.hermes/SOUL.md" || true                         # 0
systemctl start hermes-gateway; sleep 5; systemctl is-active hermes-gateway
sudo -u "$HUSER" -H hermes cron list
```

Depois `/new` no Telegram **e** no WhatsApp. **Verificação:** a lista de rotinas é a do passo 9.6; peça o saldo ao Hermes e a chamada aparece em `chamada_mcp` do **brain**.

O código instalado, os usuários, `/etc/gabi-finance/` e o banco do finance podem ficar onde estão (não fazem mal parados) para uma nova tentativa; para repetir do zero, refaça a partir do passo 3 (cópia nova do banco do brain).
