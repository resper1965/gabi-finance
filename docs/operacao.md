# Operação do dia a dia

Convenções desta página (e do [`runbook.md`](runbook.md)): `BANCO=/var/lib/gabi-finance/gabi.db`, `PY=/opt/gabi-finance/venv/bin/python`. Comandos de administração rodam como o usuário do serviço (`sudo -u gabifinance`) **a partir de `/opt/gabi-finance`** (o código roda dali, sem `pip install` do projeto). Esta VPS não tem o comando `sqlite3`; consulte o banco com Python (`$PY -c "import sqlite3; ..."`).

## O que roda e quando

Tudo é `systemd`. Os serviços ficam de pé o tempo todo; o resto são tarefas curtas (`oneshot`) disparadas por timer. Os horários são de Brasília (`America/Sao_Paulo`) e os timers têm `Persistent=true`: se a máquina estava desligada na hora, a tarefa roda ao voltar.

| Unidade | O que faz | Quando | Rede | Segredo (em `/etc/gabi-finance/`) |
|---|---|---|---|---|
| `gabi-finance-fontes.service` | Ponte do Nibo: o único processo com rede e o token do Nibo; fala por socket Unix | sempre ligado | sim (Nibo) | `nibo.env` (`NIBO_TOKEN`) |
| `gabi-finance-api.service` | API e painel, em socket Unix (`/run/gabi-finance/api.sock`) atrás do `tailscale serve` | sempre ligado | não | nenhum |
| `gabi-finance-mcp.service` | Servidor MCP em `127.0.0.1:8082` | sempre ligado | só local | nenhum (tokens ficam hasheados no banco) |
| `gabi-finance-saldos.timer` | Saldos das contas (`gabi.dinheiro.rodar saldos`) | de hora em hora, aos :05 | sim (mcp.ai) | `mcpai.env` (`MCPAI_KEY`) |
| `gabi-finance-extratos.timer` | Rodada completa: captura do Open Finance, conferência, classificação, compromissos e baixas propostas (`rodar extratos --sincronizar`) | 06:00 e 14:00 | sim (mcp.ai) | `mcpai.env` |
| `gabi-finance-notas.timer` | Notas fiscais (NFS-e) do Nibo: histórico, PDF/XML e vencimentos, só leitura (`gabi.cobrar.notas_importar`) | todo dia às 06:40 | via ponte | nenhum (a ponte tem o token) |
| `gabi-finance-avisos.timer` | Gera os avisos financeiros (`gabi.avisos`) | a cada 15 minutos | não | nenhum |
| `gabi-finance-telegram.timer` | Entrega os avisos no Telegram (`gabi.telegram`) | a cada 5 minutos | sim (Telegram) | `telegram.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) |
| `gabi-finance-backup.timer` | Backup diário do banco com teste de restauração | 03:30 | não | nenhum |
| `gabi-finance-exportacao.timer` | Pacote semanal criptografado para fora da VPS | domingo 04:00 | não | `backup.pub` (chave pública) |
| `gabi-finance-falha@.service` | Gatilho `OnFailure=` de todas as unidades acima: grava o aviso `servico_falhou` | quando uma unidade falha | não | nenhum |

Duas regras de segurança aparecem nessa tabela. **R5:** só a ponte tem o token do Nibo; a API e o MCP **não têm rede** (`IPAddressDeny=any`; o MCP só aceita `localhost`) e a unidade de notas só tem socket Unix (`RestrictAddressFamilies=AF_UNIX`); todas falam com a ponte pelo socket. A chave do **mcp.ai fica fora da ponte**: as unidades de extratos e saldos a leem do próprio `mcpai.env` e chamam o mcp.ai direto (decisão do corte; ver [`adr/039-corte-gabi-finance.md`](adr/039-corte-gabi-finance.md)). **R2:** o Telegram é a única exceção a "nada sai sozinho", e só funciona se `telegram.env` existir; sem o arquivo a unidade roda e não envia.

Ver o que está agendado: `systemctl list-timers 'gabi-finance-*'`.

## Resumo da manhã e Hermes

O Hermes não tem timer aqui. O resumo das 07:05 é um agendamento do próprio Hermes que chama a ferramenta `resumo_manha` do MCP (até 5 linhas; a primeira vem como "Dados desatualizados" quando for o caso). O vigia semanal (segunda, 09h) é outro agendamento do Hermes (ver [`runbook.md`](runbook.md#vigia)).

## Logs

| Quer ver | Comando |
|---|---|
| Uma unidade | `journalctl -u gabi-finance-api -n 50 --no-pager` (troque `api` por `mcp`, `fontes`, `extratos`, `saldos`, `notas`, `avisos`, `telegram`, `backup`, `exportacao`) |
| A última rodada de extratos | `journalctl -u gabi-finance-extratos -n 30 --no-pager -o cat` |
| Tudo do gabi-finance | `journalctl -u 'gabi-finance-*' --since today --no-pager` |
| Unidades que falharam | `systemctl --failed \| grep gabi-finance` |
| Chamadas da API | tabela `chamada` (login, método, caminho, status) |
| Chamadas do MCP | tabela `chamada_mcp` (token, ferramenta, escopo, status `ok`, `sem_escopo`, `erro`, `nao_autenticado`) |
| Rodadas | tabela `rodada` (fonte, início, fim, status, contagens, `conferida`) ou `GET /api/v1/rodadas` |

Os logs nunca trazem segredo, CPF, conta nem valor por lançamento; o Telegram e os avisos levam só nome, valor e datas.

## Saúde: o que olhar de manhã

1. `systemctl is-active gabi-finance-fontes gabi-finance-api gabi-finance-mcp` → três `active`.
2. `systemctl --failed | grep gabi-finance` → vazio.
3. No painel, Caixa › A pagar: o bloco "Rodadas" mostra as duas últimas de extrato; "dados até" deve ser de hoje.
4. O sino do painel: avisos abertos (tipos na tabela abaixo).

## Avisos: o que cada um significa

Gerados por `gabi.avisos` (a cada 15 minutos) e entregues no sino do painel, no Telegram e por `avisos_abertos`.

| Tipo | Significa | O que fazer |
|---|---|---|
| `rodada_parada` | As duas últimas rodadas de extrato falharam, ou nenhuma terminou bem nas últimas horas | Ler o log do `extratos`; ver "Falhas comuns" |
| `servico_falhou` | Uma unidade com `OnFailure` falhou | `journalctl -u <unidade>` |
| `saldo_divergente` | A conferência de saldo da última rodada de extratos não bateu numa conta liberada (só informa) | Conferir a conta no painel; ver `conferencia` |
| `banco_desatualizado` | O provedor não atualiza um banco há mais de 24 horas (um aviso por banco por dia) | Normalmente é o banco; reconectar a conta no mcp.ai se durar |
| `exportacao_parada` | Sem pacote exportado há mais de 9 dias | Ver se `/etc/gabi-finance/backup.pub` existe e o log da exportação |
| `conta_atrasada` | Compromisso ainda `atrasado` | Pagar e marcar, ou dispensar o mês |
| `vence_hoje` / `vence_em_breve` | Contas que vencem hoje / nos próximos dias (`avisos.antecedencia_dias`, padrão 3) | Pagar; ver [runbook](runbook.md#avisos-vencimento) |
| `valor_diferente` | O valor real difere em mais de 10% do estimado avisado | Conferir |
| `cobrada_apos_cancelar` | Assinatura marcada para cancelar voltou a cobrar | Cancelar de fato |
| `lancamento_sem_conversao` | Lançamentos em moeda estrangeira sem conversão | Ver [runbook](runbook.md#moeda-historico) |

Aviso que deixou de ser verdade (conta já paga, por exemplo) é fechado sem envio; "fechado" não é "enviado" (ver [runbook](runbook.md#telegram)).

## Backup e restauração

- **Diário (03:30):** `gabi-finance-backup.timer` grava `/var/backups/gabi-finance/gabi-finance-AAAA-MM-DD.sqlite` (modo 600) e testa a restauração; falha de integridade grava rodada `erro` e sai com código 1. À mão: `sudo -u gabifinance $PY -m gabi.backup --banco $BANCO --destino /var/backups/gabi-finance --testar` (a partir de `/opt/gabi-finance`).
- **Semanal para fora da VPS (domingo 04:00):** pacote `.sqlite.gpg` em `/var/backups/gabi-finance/exportacao/`, que você puxa. A VPS não guarda a única cópia.
- **Antes de instalar versão nova:** o `instalar.sh` faz um backup consistente (`gabi.db.antes-instalar-AAAA-MM-DD-HHMM`, guarda os 5 mais recentes).
- **Restaurar:** passo a passo em [`runbook.md#restaurar`](runbook.md#restaurar). Nunca copie o arquivo do banco com `cp` enquanto o serviço está escrevendo (o modo WAL deixa parte dos dados no `-wal`); use as rotinas acima.

## Rotação de segredos

Todos os segredos vivem em `/etc/gabi-finance/*.env` (`root:root`, modo 600; o systemd lê como root e entrega a variável ao serviço) e **nunca** no repositório, no banco ou em log (R5). Trocar um segredo é sempre: editar o arquivo, reiniciar a unidade, conferir.

| Segredo | Arquivo | Como trocar | Conferir |
|---|---|---|---|
| Token do Nibo | `nibo.env` (`NIBO_TOKEN=...`) | Gerar o token novo no Nibo; editar o arquivo; `sudo systemctl restart gabi-finance-fontes` | `sudo systemctl start gabi-finance-notas` e `journalctl -u gabi-finance-notas -n 20 -o cat`: sem `nao_configurada` (e sem erro de autenticação) |
| Chave do mcp.ai | `mcpai.env` (`MCPAI_KEY=...`) | Editar o arquivo. Não há serviço de pé a reiniciar: a próxima execução dos timers já lê o novo valor | `sudo systemctl start gabi-finance-saldos` e `journalctl -u gabi-finance-saldos -n 20 -o cat`: sem `sem_chave` |
| Telegram | `telegram.env` | Editar; vale na próxima execução (5 min) | `sudo systemctl start gabi-finance-telegram` |
| Token do Hermes (MCP) | banco (`token_agente`) + `~/.hermes/.env` (`GABI_FINANCE_TOKEN`) | Painel › Gabi › Agentes › Rotacionar (emite outro com os mesmos escopos e revoga o antigo); colar o novo no `.env` do Hermes; `sudo systemctl restart hermes-gateway` | Pedir ao Hermes o saldo. **Enquanto o novo não estiver no Hermes, ele fica sem o dinheiro** |
| Chave pública de exportação | `backup.pub` | Gerar o par na sua máquina (a privada nunca vem para a VPS); copiar só a pública | `sudo systemctl start gabi-finance-exportacao` |
| Tudo de uma vez (suspeita de vazamento) | banco | `POST /api/revogar-tudo` com `{"confirmo": true}` (ver [runbook](runbook.md#revogar)) | `... -m gabi.mcp.tokens listar` |

Se um segredo vazou: troque no provedor primeiro (Nibo, mcp.ai, BotFather), depois aqui.

## Falhas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Extratos com `sem_chave` | `mcpai.env` ausente ou sem `MCPAI_KEY` | Criar/ajustar o arquivo (veja Rotação) |
| Notas paradas; log do `notas` com `nao_configurada` ou erro de autenticação | Token do Nibo ausente (`nao_configurada`) ou expirado | Gerar novo token no Nibo e trocar (veja Rotação) |
| Painel mostra só a página de verificação | O painel não foi compilado antes de instalar (`gabi/painel/` ausente) | `cd painel && npm ci && npm run build` no clone e reinstalar (`instalar.sh`) |
| 403 para alguém que deveria entrar | O login do Tailscale não está em `acesso` | `$PY -m gabi.acesso --banco $BANCO adicionar <login> <pessoa_id> <nivel>` |
| 403 no POST do painel | Origem não confiável (CSRF) | Conferir `GABI_ORIGENS_CONFIAVEIS` na unidade da API |
| MCP responde `sem_escopo` | O token não tem o escopo da ferramenta | Emitir outro com o escopo certo (não amplie o de outro agente) |
| MCP recusa conexão pelo nome da máquina | Host fora de `GABI_MCP_HOSTS` (anti DNS-rebinding) | Acrescentar o host por drop-in da unidade (`systemctl edit gabi-finance-mcp`) |
| Hermes sem as ferramentas de dinheiro | `tools.include` desatualizado ou token revogado | Conferir `docs/fontes/hermes.md` e o token; `restart hermes-gateway` e `/new` |
| `/api/saude` com `db != "ok"` | Banco corrompido | Parar a API e restaurar o último backup (ver [restaurar](runbook.md#restaurar)) |
| `ultimo_backup` nulo ou com mais de 2 dias | Timer parado | `systemctl status gabi-finance-backup.timer` |
| Rodada de extratos "não conferida" | Saldo ou contagem não bateu com a fonte | Ler a tabela `conferencia` da rodada; os dados não são marcados como em dia até conferir |
| Algum `:8080` ou porta TCP da API aparecendo em `ss -ltn` | Não deveria: a API só escuta em socket | Pare o serviço e investigue |

## Limitação conhecida: agenda financeira

As tabelas `agenda_evento` e `agenda_fonte` **ficam no banco** porque `dinheiro.sugestoes_agenda` as lê (transforma evento de agenda que se repete todo mês e fala de pagar em PERGUNTA do canal de decisão). Mas a agenda do Google e do Graph **saiu no corte** e, depois da virada, **nada mais alimenta essas tabelas**: elas ficam congeladas no que estava na cópia do banco.

Consequência: as sugestões de compromisso vindas da agenda **degradam** (param de aparecer novas e as antigas envelhecem). Nada financeiro quebra: o A pagar, a projeção, os avisos e o resumo da manhã não dependem delas, e nenhum teste foi enfraquecido por causa disso. **Decisão pendente para a etapa 3** (coletor e digestão): escolher a fonte que volta a alimentar a agenda financeira, ou remover `sugestoes_agenda` e as duas tabelas.

## Evolução (onde mexer)

- Regra ou padrão novo de classificação: painel › Regras, ou `seeds/donos-padrao.json` + `python -m tools.semear_donos`.
- Categoria nova: painel › Cadastros, ou `seeds/categorias-pessoais.csv` + `python -m tools.semear_categorias`.
- Despesa nova ou encerrada: painel › Caixa › A pagar e Cadastros › Despesas, ou pelo Hermes.
- Mudança de esquema: arquivo novo em `migrations/` (próximo número livre, depois da 0091), só com `create`/`alter` e `drop` explícitos; a suíte (`tests/test_migracao_corte.py`) obriga decidir se uma tabela nova fica no inventário.
- Nada novo entra sem teste, e nenhum teste financeiro é apagado ou enfraquecido para o código passar.
