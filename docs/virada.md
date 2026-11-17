# Virada: do gabi-brain para o gabi-finance

**Para quem é:** o Ricardo, rodando como `root` na VPS. O Claude guia (explica, confere a saída que você colar), mas **você** roda cada comando. Um passo de cada vez: só siga quando a verificação do passo bater.

**O que muda.** O dinheiro (extratos, saldos, A pagar, projeção, gastos, notas, a receber, avisos financeiros) sai do `gabi-brain` e passa a viver no `gabi-finance`, com banco próprio (uma **cópia** do banco do brain), usuário próprio e endereço novo. O `gabi-brain` **não é removido**: continua instalado e desligado só no que é dinheiro, para a volta ser rápida.

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
| Endereço | `gabi.tail985643.ts.net` | `gabi-finance.tail985643.ts.net` |
| MCP | porta 8081, servidor `gabi_brain` | porta 8082, servidor `gabi_finance` |
| Token do Hermes | `GABI_BRAIN_TOKEN` | `GABI_FINANCE_TOKEN` (token **novo**) |

## Antes de começar (pré-requisitos)

1. **Snapshot da VPS e backup exportado** (gate G1): o instalador pede a confirmação e eu também: sem isso, não comece.
2. **Token novo do Nibo** em mãos (o atual expirou; as notas estão paradas desde pelo menos 09/11). Sem ele a virada funciona, só que as notas ficam paradas e a fonte responde `nao_configurada`.
3. **Uma janela de uns 45 minutos**, de preferência de manhã cedo, sem mexer no painel do brain durante ela (o que for decidido no brain depois da cópia do banco **não** vai para o finance).
4. O repositório do gabi-finance clonado na VPS, na branch com o corte, e o painel compilado. O instalador copia `gabi/` do clone, **inclusive o painel compilado**, e não roda npm. Veja o passo 1.

Variáveis usadas em todos os passos (cole no começo da sessão de root; ajuste só as duas primeiras):

```bash
export HUSER=ricardo              # confirmado no passo 0
export LOGIN='seu-login@tailscale' # o login do Tailscale que entra como boss no painel
export PY=/opt/gabi-finance/venv/bin/python
export HOJE=$(TZ=America/Sao_Paulo date +%F)
```

## Passo 0: confirmar quem é o usuário do Hermes e o estado de partida

O repositório sugere que o Hermes roda como `ricardo`, mas **confirme na máquina**, porque o `config.yaml`, o `.env` e o SOUL são do usuário que o roda:

```bash
systemctl show hermes-gateway -p User --value      # imprime o usuário; vazio = roda como root (avise-me)
ls -d /home/*/.hermes                              # deve listar a pasta do mesmo usuário
```

**Verificação:** os dois comandos apontam para o mesmo usuário. Se for outro que não `ricardo`, ajuste `HUSER` acima. Depois confira que o brain está de pé e quais timers estão ligados (anote a lista, vale para a volta):

```bash
export HOME_H=$(getent passwd "$HUSER" | cut -d: -f6); echo "$HOME_H"
systemctl is-active gabi-brain-api gabi-brain-mcp hermes-gateway   # três "active"
systemctl list-timers 'gabi-brain-*' --no-pager
ls -l /etc/gabi/brain.env /etc/gabi/cobrar.env /etc/gabi/telegram.env /etc/gabi/backup.pub 2>&1 | cut -c1-80
```

## Passo 1: instalar (nada é ligado)

Compile o painel **no clone** e instale. O instalador não toca no brain e deixa todas as unidades desligadas.

```bash
sudo -u "$HUSER" git clone https://github.com/resper1965/gabi-finance.git "$HOME_H/gabi-finance"   # se já existe: cd e git pull
cd "$HOME_H/gabi-finance" && sudo -u "$HUSER" git switch corte    # a branch do corte (ou main, depois do merge)
sudo -u "$HUSER" bash -c 'cd ~/gabi-finance/painel && npm ci && npm run build'
ls gabi/painel/index.html                                          # o painel compilado existe
bash deploy/instalar.sh --confirmo-backup-exportado
```

**Verificação:**

```bash
id gabifinance gabifinance-fontes                       # os dois usuários existem
ls -l /opt/gabi-finance /etc/gabi-finance               # código e pasta de segredos (vazia)
systemctl list-unit-files 'gabi-finance-*' --no-pager   # TODAS "disabled" (ou "static" para o falha@)
systemctl is-active gabi-finance-api                    # "inactive"
ss -ltn | grep -E ':8081|:8082' || echo "nada em 8081/8082 pelo finance"   # o MCP do brain segue na 8081; a 8082 ainda livre
```

Se o repositório for privado e o `git clone` pedir senha, me avise: resolvemos o acesso antes de seguir.

## Passo 2: segredos em `/etc/gabi-finance/`

Os segredos **não** vão para o repositório nem aparecem na tela. Crie os arquivos assim (modo 600, `root:root`; o systemd os lê como root):

```bash
umask 077
# mcp.ai: copie só a linha MCPAI_KEY do arquivo do brain
grep '^MCPAI_KEY=' /etc/gabi/brain.env > /etc/gabi-finance/mcpai.env
# Nibo: cole o token NOVO (não aparece na tela)
read -rsp "Cole o token do Nibo e tecle Enter: " T; echo; printf 'NIBO_TOKEN=%s\n' "$T" > /etc/gabi-finance/nibo.env; unset T
# chave pública de exportação (se o brain já tinha uma)
[ -f /etc/gabi/backup.pub ] && install -m 644 /etc/gabi/backup.pub /etc/gabi-finance/backup.pub
chown root:root /etc/gabi-finance/*; chmod 600 /etc/gabi-finance/*.env
```

O Telegram é decisão sua (passo 11): **não** crie `telegram.env` agora.

**Verificação** (sem mostrar o conteúdo):

```bash
ls -l /etc/gabi-finance/
grep -c '^MCPAI_KEY=.' /etc/gabi-finance/mcpai.env    # 1
grep -c '^NIBO_TOKEN=.' /etc/gabi-finance/nibo.env    # 1
```

## Passo 3: parar o dinheiro no brain e copiar o banco

Pare os três timers financeiros do brain e espere qualquer rodada em andamento terminar:

```bash
systemctl stop gabi-brain-extratos.timer gabi-brain-saldos.timer gabi-brain-notas.timer
systemctl stop gabi-brain-extratos.service gabi-brain-saldos.service gabi-brain-notas.service
systemctl list-units 'gabi-brain-extratos*' 'gabi-brain-saldos*' 'gabi-brain-notas*' --state=active --no-pager   # vazio
```

Agora a cópia consistente do banco (API de backup do SQLite; **nunca `cp`** com o brain escrevendo em WAL). Ela roda como o dono do banco do brain, grava em `/tmp` e depois você a coloca no lugar:

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
install -o gabifinance -g gabifinance -m 600 /tmp/gabi-virada.db /var/backups/gabi-finance/gabi-brain-copia-pre-migracao.db
install -o gabifinance -g gabifinance -m 600 /tmp/gabi-virada.db /var/lib/gabi-finance/gabi.db
rm -f /tmp/gabi-virada.db
```

**Verificação:** a saída traz `integridade: ok`; os dois arquivos existem (`ls -l /var/backups/gabi-finance/gabi-brain-copia-pre-migracao.db /var/lib/gabi-finance/gabi.db`, ambos `gabifinance`, 600); e o `/tmp/gabi-virada.db` sumiu. A cópia `...pre-migracao.db` fica como referência intocada para a conferência (passo 5) e para a volta.

## Passo 4: migrar a cópia e limpar os tokens herdados

Aplica as migrações novas (0090 derruba as tabelas das áreas que saíram; 0091 derruba `pet`, `allowlist_vip` e `memoria`):

```bash
cd /opt/gabi-finance
runuser -u gabifinance -- ./venv/bin/python -c "
from pathlib import Path
from gabi.db import conectar, migrar
c = conectar(Path('/var/lib/gabi-finance/gabi.db'))
print('aplicadas:', migrar(c, Path('migrations')))
print('integridade:', c.execute('pragma integrity_check').fetchone()[0])
print('tabelas:', c.execute(\"select count(*) from sqlite_master where type='table' and name not like 'sqlite_%'\").fetchone()[0])
print('pet existe?', c.execute(\"select count(*) from sqlite_master where name in ('pet','allowlist_vip','memoria','projeto','documento')\").fetchone()[0])
"
```

**Verificação:** `aplicadas:` lista `0090_corte_financeiro.sql` e `0091_minimizar_dados.sql`; `integridade: ok`; `pet existe? 0`. (Se `aplicadas` vier vazia, o banco já estava migrado: normal numa segunda tentativa.)

A cópia trouxe os **tokens de agentes** do brain (só o hash). O token novo do Hermes será emitido no passo 9; para que **só ele** valha no finance, revogue os herdados agora (isto só mexe no banco do finance; o brain segue com os dele):

```bash
cd /opt/gabi-finance
runuser -u gabifinance -- $PY -m gabi.mcp.tokens --banco /var/lib/gabi-finance/gabi.db listar
for id in $(runuser -u gabifinance -- $PY -m gabi.mcp.tokens --banco /var/lib/gabi-finance/gabi.db listar | awk '$NF=="ativo"{print $1}'); do
  runuser -u gabifinance -- $PY -m gabi.mcp.tokens --banco /var/lib/gabi-finance/gabi.db revogar "$id"
done
runuser -u gabifinance -- $PY -m gabi.mcp.tokens --banco /var/lib/gabi-finance/gabi.db listar     # tudo "revogado"
```

## Passo 5: conferência lado a lado (antes de qualquer rodada nova)

Este é o passo que diz se o dinheiro **bateu**. A ideia: o mesmo programa (`tools/conferir_virada.py`, só leitura) lê a cópia **antes** de migrar e o banco **depois** de migrar, com a mesma data, e a saída tem de ser idêntica. Como ainda não houve rodada nova, qualquer diferença é falha do corte, não dado novo. Rode como `gabifinance` (nunca como root: root deixaria arquivos que a API depois não consegue gravar).

```bash
cd /opt/gabi-finance
runuser -u gabifinance -- $PY -m tools.conferir_virada --banco /var/backups/gabi-finance/gabi-brain-copia-pre-migracao.db --hoje "$HOJE" > /tmp/conf-antes.txt
runuser -u gabifinance -- $PY -m tools.conferir_virada --banco /var/lib/gabi-finance/gabi.db --hoje "$HOJE" > /tmp/conf-depois.txt
diff /tmp/conf-antes.txt /tmp/conf-depois.txt && echo "BATEU: sem diferença"
cat /tmp/conf-depois.txt
```

A saída traz três blocos: **saldos por conta** (com total e faturas abertas), **a pagar do mês** (aberto, atrasado e a conferir, com total e quantos estão sem valor) e a **projeção de caixa de 30 dias** (com o menor saldo). **Verificação:** o `diff` não imprime nada e aparece `BATEU: sem diferença`. Cole-me o `conf-depois.txt` para eu olhar se os números fazem sentido para você (saldos que você reconhece, A pagar do mês).

**Se não bater: pare aqui.** Não ligue nada. A volta é só reverter o passo 3 (religar os timers do brain, ver "Volta"); o brain não foi alterado.

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
curl -s --unix-socket /run/gabi-finance/api.sock http://localhost/api/eu -H "Tailscale-User-Login: $LOGIN"   # {"login":...,"nivel":"boss"}
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8082/mcp          # 401 (sem token não entra)
ss -ltn | grep -E ':8080|:8000' || echo "sem porta TCP da API"                    # nenhuma porta TCP da API
```

Se `/api/eu` não devolver `"nivel":"boss"`, o seu login não está em `acesso` na cópia: me diga o que saiu.

## Passo 7: expor no Tailscale com o endereço novo

> **Este passo depende de configuração no console da Tailscale que eu não consigo verificar daqui, e o comando abaixo deve ser confirmado antes de rodar.** O endereço `gabi-finance.tail985643.ts.net` é diferente do nome desta máquina (`gabi`), então ele precisa ser um **Tailscale Service** (um nome próprio servido por esta máquina). Antes de rodar o comando, no console de administração da Tailscale (Services) é preciso ter o serviço `svc:gabi-finance` definido e esta máquina autorizada a hospedá-lo. Me diga o que o seu console mostra e eu confirmo a sintaxe exata para a versão do `tailscale` instalada (`tailscale version`).

O que o comando faz, com o socket Unix da API como destino (a API só escuta em socket; é o `tailscale serve` que injeta o cabeçalho de identidade `Tailscale-User-Login`):

```bash
tailscale serve --service=svc:gabi-finance --https=443 unix:/run/gabi-finance/api.sock     # SINTAXE A CONFIRMAR (ver acima)
tailscale serve status
```

**Verificação (de outro aparelho na sua tailnet):** abrir `https://gabi-finance.tail985643.ts.net/api/eu` mostra o **seu login** e `"nivel":"boss"`, e o painel em `https://gabi-finance.tail985643.ts.net/` abre. **Atenção:** se a resposta vier sem o seu login (anônimo) ou 403, o serviço não está injetando a identidade: **pare** e me avise; sem identidade o painel não deve ser usado (R3). O painel de aceite é: ele carrega o Caixa e o "dados até" da barra mostra a data da cópia.

(O endereço antigo `gabi.tail985643.ts.net` continua servindo o brain; não mexa nele.)

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

Com as rodadas boas, ligue os timers:

```bash
systemctl enable --now gabi-finance-saldos.timer gabi-finance-extratos.timer gabi-finance-notas.timer gabi-finance-avisos.timer gabi-finance-backup.timer
[ -f /etc/gabi-finance/backup.pub ] && systemctl enable --now gabi-finance-exportacao.timer || echo "sem backup.pub: exportação semanal fica desligada (veja runbook#backup-fora)"
systemctl list-timers 'gabi-finance-*' --no-pager
```

**Verificação:** `list-timers` mostra os timers com a próxima execução (saldos aos :05, extratos 06:00/14:00, notas 06:40, avisos a cada 15 min, backup 03:30).

## Passo 9: o Hermes passa a usar o gabi_finance

O Hermes ganha um token **novo** (o do brain fica como está, para a volta). Tudo isto é no usuário do Hermes, e **eu não vejo o token**: ele vai direto para o `.env`.

1. **Backups do Hermes** (guarde estes nomes: são a volta):

```bash
D=$(date +%F-%H%M)
sudo -u "$HUSER" cp -p "$HOME_H/.hermes/config.yaml" "$HOME_H/.hermes/config.yaml.bak-antes-finance-$D"
sudo -u "$HUSER" cp -p "$HOME_H/.hermes/.env" "$HOME_H/.hermes/.env.bak-antes-finance-$D"
ls -l "$HOME_H"/.hermes/*.bak-antes-finance-"$D"
```

2. **Emitir o token e gravá-lo no `.env`** sem imprimir:

```bash
cd /opt/gabi-finance
TOKEN=$(runuser -u gabifinance -- $PY -m gabi.mcp.tokens --banco /var/lib/gabi-finance/gabi.db emitir hermes fin,trabalho,propostas,pedidos,decisoes | tail -n 1)
printf 'GABI_FINANCE_TOKEN=%s\n' "$TOKEN" >> "$HOME_H/.hermes/.env"; unset TOKEN
grep -c '^GABI_FINANCE_TOKEN=.' "$HOME_H/.hermes/.env"        # 1
```

3. **`config.yaml`:** abra `$HOME_H/.hermes/config.yaml` e faça duas coisas em `mcp_servers`. (a) Acrescente o servidor novo, com a lista **exata** de `docs/fontes/hermes.md` (33 ferramentas, sem curinga; copie o bloco de lá):

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

(b) No servidor antigo `gabi_brain`, **tire do `include` as ferramentas financeiras** (as mesmas 33 da lista), para o Hermes não oferecer o mesmo dinheiro por dois caminhos. As ferramentas não financeiras do brain ficam como estão. Confira a sintaxe do arquivo:

```bash
sudo -u "$HUSER" python3 -c "import yaml,sys; d=yaml.safe_load(open('$HOME_H/.hermes/config.yaml')); print(list(d['mcp_servers']))"   # lista os dois servidores
```

4. **SOUL novo** (só financeiro; guarda o anterior como `SOUL.md.bak-<data>`):

```bash
sudo -u "$HUSER" bash "$HOME_H/gabi-finance/deploy/instalar-hermes-soul.sh"
```

> **Atenção:** o SOUL novo traz **só** as instruções de dinheiro, com o prefixo `mcp__gabi_finance__`. As instruções do Hermes para agenda, contatos e o resto saem do SOUL (ficam no `SOUL.md.bak-<data>`) até a etapa 3 juntar tudo. Se você usa o Hermes para essas coisas nesse intervalo, me diga antes, e decidimos juntos como não perdê-las.

5. **Reiniciar e abrir conversa nova:**

```bash
systemctl restart hermes-gateway
systemctl is-active hermes-gateway
```

Depois mande `/new` no Telegram **e** no WhatsApp.

**Verificação:** peça ao Hermes "qual é o meu saldo?". A resposta deve vir com os saldos, e uma chamada nova com a ferramenta `financeiro_saldo` e status `ok` aparece no registro do MCP do finance:

```bash
cd /opt/gabi-finance
runuser -u gabifinance -- $PY -c "
import sqlite3
c = sqlite3.connect('file:/var/lib/gabi-finance/gabi.db?mode=ro', uri=True)
for r in c.execute('select quando, ferramenta, status from chamada_mcp order by id desc limit 5'): print(r)
"
```

## Passo 10: desligar o dinheiro no brain (sem remover)

Os três timers já estão parados desde o passo 3. Agora impeça que voltem num reinício da máquina:

```bash
systemctl disable gabi-brain-extratos.timer gabi-brain-saldos.timer gabi-brain-notas.timer
systemctl list-unit-files 'gabi-brain-extratos.timer' 'gabi-brain-saldos.timer' 'gabi-brain-notas.timer' --no-pager   # "disabled"
```

Duas coisas **fora deste repositório** continuam do brain e ficam para a etapa 3: o bloco de dinheiro do resumo da manhã do brain (como os timers pararam, ele envelhece e passa a avisar "dados desatualizados"; o resumo financeiro de verdade agora é o `resumo_manha` do gabi-finance), e os avisos financeiros que o próprio brain ainda gera a partir da cópia congelada dele. Não apague nada do brain.

## Passo 11: Telegram (decisão sua)

Se você ligar o `gabi-finance-telegram`, os avisos financeiros vão chegar **também** do brain até a etapa 3 (o brain ainda gera e envia os avisos dele a partir do banco antigo), então o mesmo aviso pode chegar duas vezes. As opções: (a) deixar o Telegram do finance **desligado** por enquanto (o sino do painel e o Hermes continuam mostrando os avisos); (b) ligá-lo e tolerar a duplicidade até a etapa 3. Se escolher (b):

```bash
umask 077
read -rp "TELEGRAM_BOT_TOKEN: " B; read -rp "TELEGRAM_CHAT_ID: " C
printf 'TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=%s\n' "$B" "$C" > /etc/gabi-finance/telegram.env; unset B C
chown root:root /etc/gabi-finance/telegram.env; chmod 600 /etc/gabi-finance/telegram.env
systemctl enable --now gabi-finance-telegram.timer
```

## Passo 12: aceite nas primeiras 24 horas

- `systemctl --failed | grep gabi-finance` vazio.
- Amanhã, depois das 06:00 e 06:40: as rodadas de extratos e de notas do dia aparecem em `rodada` e a mais recente de extratos está conferida.
- O resumo das 07:05 chega pelo Hermes, com dinheiro.
- No painel, Caixa › A pagar mostra "dados até" de hoje e o **mesmo A pagar do mês** do passo 5 (mais o que a rodada trouxe de novo).
- `chamada_mcp` mostra chamadas `ok` do token do Hermes.
- O backup das 03:30 gravou um arquivo novo em `/var/backups/gabi-finance/` e a rodada `backup` está `ok`.

Depois de uma semana sem problema, o brain pode deixar de ser mantido para o dinheiro (a remoção dele é decisão da etapa 3, não daqui).

## Volta (rollback)

A volta é segura em qualquer ponto até o passo 10 **porque o brain não foi alterado**: o banco dele só ficou parado, e o `config.yaml`, o `.env` e o SOUL do Hermes têm backup datado. O que se perde numa volta: as rodadas que o brain não fez durante a janela (a próxima captura do brain as pega, porque a leitura é incremental) e o que você tiver decidido **no finance** nesse intervalo (decisões, classificações, A pagar marcado como pago), que não volta para o brain.

**1. Parar o finance** (se já estava ligado):

```bash
systemctl stop 'gabi-finance-*.timer'
systemctl stop 'gabi-finance-*.service'
systemctl disable gabi-finance-saldos.timer gabi-finance-extratos.timer gabi-finance-notas.timer gabi-finance-avisos.timer gabi-finance-backup.timer gabi-finance-exportacao.timer gabi-finance-telegram.timer gabi-finance-fontes gabi-finance-api gabi-finance-mcp 2>/dev/null
systemctl list-units 'gabi-finance-*' --state=active --no-pager      # vazio
```

**2. Religar o dinheiro no brain:**

```bash
systemctl enable --now gabi-brain-extratos.timer gabi-brain-saldos.timer gabi-brain-notas.timer
systemctl list-timers 'gabi-brain-*' --no-pager                       # os três de volta, com próxima execução
systemctl start gabi-brain-saldos                                     # atualiza os saldos já
```

**3. Restaurar o Hermes** (use as datas dos backups do passo 9; `ls "$HOME_H/.hermes/"`):

```bash
sudo -u "$HUSER" cp -p "$HOME_H/.hermes/config.yaml.bak-antes-finance-<data>" "$HOME_H/.hermes/config.yaml"
sudo -u "$HUSER" cp -p "$HOME_H/.hermes/.env.bak-antes-finance-<data>" "$HOME_H/.hermes/.env"
sudo -u "$HUSER" cp -p "$HOME_H/.hermes/SOUL.md.bak-<data>" "$HOME_H/.hermes/SOUL.md"
systemctl restart hermes-gateway
```

Depois `/new` no Telegram **e** no WhatsApp. **Verificação:** peça o saldo ao Hermes; a chamada aparece em `chamada_mcp` do **brain**.

**4. O Tailscale** não precisa ser desfeito: com o finance parado, `gabi-finance.tail985643.ts.net` simplesmente não responde, e `gabi.tail985643.ts.net` nunca deixou de servir o brain. Remover a definição do serviço no console da Tailscale é opcional.

O código instalado, os usuários, `/etc/gabi-finance/` e o banco do finance podem ficar onde estão (não fazem mal parados) para uma nova tentativa; para repetir do zero, refaça a partir do passo 3 (cópia nova do banco do brain).
