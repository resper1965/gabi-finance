# gabi-finance · Runbook

Procedimentos para quem opera o serviço. A visão geral do dia a dia (timers, logs, falhas comuns, rotação de segredos) está em [`operacao.md`](operacao.md); o roteiro de colocar no ar está em [`virada.md`](virada.md).

Convenção: `BANCO=/var/lib/gabi-finance/gabi.db` e `PY=/opt/gabi-finance/venv/bin/python`. Comandos de administração rodam como `gabifinance` (`sudo -u gabifinance …`) **a partir de `/opt/gabi-finance`**. A VPS não tem o `sqlite3`; para consultar o banco use `$PY -c "import sqlite3; ..."`.

## Subir e parar
- Status: `systemctl is-active gabi-finance-fontes gabi-finance-api gabi-finance-mcp` → três `active`.
- Reiniciar (nesta ordem, porque a API e o MCP falam com a ponte): `sudo systemctl restart gabi-finance-fontes gabi-finance-api gabi-finance-mcp`. Parar: `sudo systemctl stop gabi-finance-api`.
- Logs: `journalctl -u gabi-finance-api -n 50 --no-pager`.
- **Instalar versão nova** (depois do merge): no clone, `cd painel && npm ci && npm run build` (a saída `gabi/painel/` é ignorada pelo git e o instalador copia `gabi/` do clone, então o painel tem de estar compilado antes) e então `sudo bash deploy/instalar.sh --confirmo-backup-exportado`. O instalador faz backup do banco, troca o código sem janela vazia e **não reinicia nada**: depois rode o `restart` acima.
- Socket: `ls -ld /run/gabi-finance` → `drwx------ gabifinance`; `ss -ltn | grep -E ':8080|:8000'` → **vazio** (a API não tem porta TCP). Se aparecer, **pare o serviço** e investigue. O MCP escuta só em `127.0.0.1:8082`.
- Chamar a API à mão (como root ou `gabifinance`): `curl --unix-socket /run/gabi-finance/api.sock http://localhost/api/eu -H 'Tailscale-User-Login: <login>'`.

## Acesso (quem entra)
- Listar: `sudo -u gabifinance $PY -m gabi.acesso --banco $BANCO listar`.
- Adicionar: `sudo -u gabifinance $PY -m gabi.acesso --banco $BANCO adicionar <login-tailscale> <pessoa_id> boss|familia_vip|terceiros`.
- Remover acesso: apagar a linha de `acesso` e conferir com `listar`. Sem login em `acesso`, a pessoa recebe 403.

## Revogar tudo (tokens de agentes) {#revogar}
`curl --unix-socket /run/gabi-finance/api.sock -X POST http://localhost/api/revogar-tudo -H 'Tailscale-User-Login: <seu-login>' -H 'Content-Type: application/json' -d '{"confirmo": true}'` → `{"revogados": N}`. Sem `confirmo: true` devolve 400 e nada muda. Depois disso o Hermes fica sem o dinheiro até receber um token novo.

## Carregar o staging
Só na instalação inicial ou se precisar refazer a carga: `sudo -u gabifinance $PY -m gabi.importar --banco $BANCO --staging <pasta do staging>` imprime as contagens; pode rodar de novo sem duplicar e registra uma rodada `importacao-staging`. Depois da migração 0091 ele já não carrega pets, lista de números autorizados nem memória de conversas. Na virada o banco vem da cópia do serviço anterior, não do staging.

## Restaurar {#restaurar}
Backups: o diário (`/var/backups/gabi-finance/gabi-finance-AAAA-MM-DD.sqlite`), o do instalador (`/var/backups/gabi-finance/gabi.db.antes-instalar-AAAA-MM-DD-HHMM`, os 5 últimos) ou um pacote decifrado de "Backup fora da VPS".
1. **Anotar os timers ligados** (para religar só esses): `systemctl list-units 'gabi-finance-*.timer' --state=active`.
2. **Parar tudo, timers primeiro:** `sudo systemctl stop 'gabi-finance-*.timer'`, depois `sudo systemctl stop 'gabi-finance-*.service'` (pega também tarefa em andamento). Conferir: `systemctl list-units 'gabi-finance-*' --state=active` deve vir vazio; só siga quando vier.
3. **Guardar o banco atual:** `sudo cp -p /var/lib/gabi-finance/gabi.db /var/backups/gabi-finance/gabi.db.antes-restaurar-$(date +%F-%H%M)`.
4. **Trocar o banco:** `sudo cp <backup escolhido> /var/lib/gabi-finance/gabi.db && sudo rm -f /var/lib/gabi-finance/gabi.db-wal /var/lib/gabi-finance/gabi.db-shm && sudo chown gabifinance:gabifinance /var/lib/gabi-finance/gabi.db && sudo chmod 600 /var/lib/gabi-finance/gabi.db`.
5. **Conferir integridade:** `cd /opt/gabi-finance && sudo -u gabifinance $PY -c "import sqlite3; print(sqlite3.connect('/var/lib/gabi-finance/gabi.db').execute('pragma integrity_check').fetchone()[0])"` deve imprimir `ok`.
6. **Religar:** `sudo systemctl start gabi-finance-fontes gabi-finance-api gabi-finance-mcp` e, para cada timer anotado no passo 1, `sudo systemctl start <timer>`; conferir `/api/saude`.
7. **Registrar:** `cd /opt/gabi-finance && sudo -u gabifinance $PY -c "import sqlite3; c=sqlite3.connect('/var/lib/gabi-finance/gabi.db'); c.execute(\"insert into decisao(quando, quem, o_que, origem) values (datetime('now'), 'ricardo', 'Banco restaurado de <backup usado>', 'runbook#restaurar')\"); c.commit()"`.

## Backup fora da VPS {#backup-fora}
Pacote semanal criptografado, para o Ricardo puxar; a chave privada nunca fica na VPS.
1. **Uma vez, na sua máquina:** `gpg --quick-generate-key ricardo-gabi-backup` e `gpg --armor --export ricardo-gabi-backup > backup.pub`. Copie só a **pública** para a VPS: `sudo install -m 644 backup.pub /etc/gabi-finance/backup.pub`. Guarde a privada (e uma cópia dela) fora da VPS.
2. Domingo 04:00 (`gabi-finance-exportacao.timer`) gera `/var/backups/gabi-finance/exportacao/gabi-finance-AAAA-MM-DD.sqlite.gpg` (600; guarda os 8 últimos) e uma rodada `exportacao`. Sem `/etc/gabi-finance/backup.pub` a unidade nem roda; se o teste de restauração falhar, nada é exportado e o sino avisa. À mão: `sudo systemctl start gabi-finance-exportacao`.
3. **Puxar:** `scp vps:/var/backups/gabi-finance/exportacao/*.gpg ./` e conferir: `gpg --decrypt gabi-finance-AAAA-MM-DD.sqlite.gpg > teste.sqlite` e `pragma integrity_check` deve dar `ok`.
4. **Restaurar a partir do pacote:** decifrar na sua máquina, copiar para a VPS e seguir [Restaurar](#restaurar).

## Alertas
| Sinal | Significa | Ação |
|---|---|---|
| `/api/saude` com `db != "ok"` | banco corrompido | parar a API e restaurar o último backup |
| rodada `backup` com `status=erro` | backup ou restauração falhou | rodar à mão com `--testar` e ler a mensagem |
| `ultimo_backup` nulo ou com mais de 2 dias | timer parado | `systemctl status gabi-finance-backup.timer` |
| 403 para alguém que deveria entrar | login fora de `acesso` | `gabi.acesso adicionar` |

A lista completa de avisos e de falhas comuns está em [`operacao.md`](operacao.md).

## Servidor MCP e tokens de agentes
- O MCP escuta **só em 127.0.0.1:8082** (`gabi-finance-mcp.service`), Streamable HTTP em `/mcp`, e exige `Authorization: Bearer <token>`. Para agentes fora da VPS (Claude Code no seu computador): `sudo tailscale serve --bg --https=8443 http://127.0.0.1:8082` e acrescentar o nome da máquina em `GABI_MCP_HOSTS` por drop-in (`systemctl edit gabi-finance-mcp`); o token continua obrigatório.
- Emitir (o token aparece **uma vez**; o banco guarda só o hash): `cd /opt/gabi-finance && sudo -u gabifinance $PY -m gabi.mcp.tokens --banco $BANCO emitir hermes fin,trabalho,propostas,pedidos,decisoes` (escopos possíveis: `fin,trabalho,pedidos,propostas,decisoes,sensivel`). Trocar só os escopos de um token ativo, sem mudar o segredo: `... -m gabi.mcp.tokens --banco $BANCO escopos <id> fin,trabalho`. Você cola o token no agente; ninguém mais o vê.
- Listar: `... -m gabi.mcp.tokens --banco $BANCO listar` · Revogar um: `... revogar <id>` · Revogar todos: ver [acima](#revogar).
- Cada chamada fica em `chamada_mcp` (token, ferramenta, escopo, status). Para ver: `$PY -c "import sqlite3; [print(r) for r in sqlite3.connect('/var/lib/gabi-finance/gabi.db').execute('select quando, ferramenta, status from chamada_mcp order by id desc limit 20')]"`.
- Só existem ferramentas de leitura, de proposta e de gravação pequena a pedido do Ricardo ([`mcp.md`](mcp.md)). Não há como enviar, pagar, apagar, aprovar nem ligar regra por MCP (R13).
- Se um agente receber `sem_escopo`, o token não tem o escopo da ferramenta: emita outro com o escopo certo (não amplie o de outro agente).

## Telas de dinheiro {#telas-dinheiro}
O painel (React + Vite, em `painel/`) responde uma pergunta por tela; a tabela de telas e rotas está em [`painel.md`](painel.md). Alguns comandos de apoio:
- **Ver sem dados reais:** `python -m tools.demo 8099` sobe a API com banco sintético e o painel compilado; mande o cabeçalho `Tailscale-User-Login: boss@x.com`.
- **Testes das telas** usam respostas reais da API (`painel/tests/amostras`, geradas por `python -m tools.gerar_amostras`); `tests/test_amostras_painel.py` falha se a API mudar e as amostras não.

## Rotina de dinheiro (donos, rodada, notas, avisos) {#rotina-dinheiro}
- **Aplicar donos padrão** (depois de editar `seeds/donos-padrao.json`): `cd /opt/gabi-finance && sudo -u gabifinance $PY -m tools.semear_donos --banco $BANCO`. Idempotente e auditado; não sobrescreve decisão do Ricardo nem regra (o que conflita vai para `conflitos`). Categorias: `python -m tools.semear_categorias`. Corrigir a origem de "para quem" vindo de padrão: `python -m tools.marcar_padroes`.
- **Rodar a rodada à mão:** `sudo systemctl start gabi-finance-extratos` (captura, conferência, classificação, compromissos e baixas propostas); ler com `journalctl -u gabi-finance-extratos -n 20 --no-pager -o cat`. Saldos: `gabi-finance-saldos`.
- **Importar notas (NFS-e):** `sudo systemctl start gabi-finance-notas`; o timer repete sozinho todo dia às 06:40. As baixas casadas aparecem em Cobrar › Notas a receber para confirmar ou rejeitar.
- **Ler avisos:** sino do painel; por linha de comando `cd /opt/gabi-finance && sudo -u gabifinance $PY -m gabi.avisos`. Tipos e o que fazer: [`operacao.md`](operacao.md#avisos-o-que-cada-um-significa).
- **Restaurar backup:** ver [Restaurar](#restaurar).

## Avisos de vencimento antecipados {#avisos-vencimento}
Além do aviso do dia (`vence_hoje`) e do de conta atrasada, o `gabi.avisos` (timer de 15 min) grava `vence_em_breve`: as contas `aberto`, `previsto` ou `debito_automatico` que vencem de amanhã até `avisos.antecedencia_dias` à frente (parâmetro, padrão 3, de 1 a 14). Cada conta entra num aviso uma única vez. O valor que ainda é estimativa aparece como "≈ R$ X (estimado)"; a conta sem valor aparece como "sem valor"; débito automático vem marcado, para você garantir saldo. Na entrega o aviso é revalidado: conta já paga sai, e o valor real que chegou substitui o estimado. Quando o valor real difere em mais de 10% do estimado avisado, sai UM `valor_diferente`. Chegam pelo Telegram e por `avisos_abertos` como os demais.

## Avisos no Telegram {#telegram}
Desligado por padrão. Para ligar (é a sua exceção à R2): crie `/etc/gabi-finance/telegram.env` (`root:root`, 600) com `TELEGRAM_BOT_TOKEN=...` e `TELEGRAM_CHAT_ID=...` (o bot vem do BotFather; o chat, do `getUpdates` depois de mandar uma mensagem ao bot). O `gabi-finance-telegram.timer` (5 min) envia os avisos ainda não lidos dos últimos 2 dias, no máximo 10 por rodada, em português, só com nome, valor e datas (nunca CPF, conta ou chave PIX); marca `aviso.telegram_em` só depois do 200 e nunca reenvia. Para desligar: apague o arquivo. Teste à mão: `sudo systemctl start gabi-finance-telegram`.
**Aviso obsoleto não é enviado.** Antes de entregar, a condição é relida: `vale` (ainda verdadeira: o texto sai do estado ATUAL), `resolvido` (pago, débito automático, vencimento movido: o aviso é fechado sem envio; para ele `telegram_em`/`entregue_em` significam "fechado", não "enviado") ou `incerto` (compromisso `a_conferir`: não envia e não fecha, reavalia a cada rodada). Descartados e incertos não contam nos 10 por rodada; o log mostra só contagens.

## Moeda estrangeira: corrigir o histórico {#moeda-historico}
Só se os lançamentos antigos em USD/EUR/PEN ainda tiverem o valor da moeda da compra gravado como reais. Passo **só com o OK do Ricardo**:
1. `python -m tools.corrigir_moeda --dry-run`: só lê e imprime contagens (`mudariam`, `diferenca_centavos`, `sem_bruto`). Não migra.
2. `python -m tools.corrigir_moeda`: aplica, em transação única, a partir do bruto imutável (sem rede). Só toca lançamentos em moeda estrangeira; BRL nunca muda. Idempotente.
3. Conferir `sem_bruto`: ele conta TODA linha sem transação no bruto (BRL, lançamentos manuais ou importados também). No banco real deve ser 0; se não for, pare e investigue antes de rodar sem `--dry-run`.
(Na produção anterior o ensaio já foi feito; o banco copiado na virada vem com o histórico corrigido. O comando fica para o caso de reimportar.)

## Canal de decisão {#decisoes}
O serviço guarda **perguntas com opções numeradas**; o Hermes as mostra no Telegram/WhatsApp e, quando o Ricardo responde com um número, grava a decisão como dele (origem `canal`). O canal só **lê** perguntas (`decisoes_abertas`) e **grava o número** (`decisao_responder`); criar pergunta é da API (boss) e o efeito de cada opção vem de uma lista fechada no código (`registrar_nota`, `marcar_conta_nao`, `marcar_conta_sim`). Resposta só uma vez; repetir o mesmo número é inofensivo, outro número é recusado. Precisa do escopo `decisoes` no token e da skill de `docs/fontes/hermes-skill-decisoes.md` no Hermes.
**Criar uma pergunta (boss, à mão ou por script):** `POST /api/v1/decisoes/perguntas` com `{tipo, titulo, contexto, opcoes:[{n, rotulo, efeito, parametros}]}`; ver `GET /api/v1/decisoes/perguntas?estado=aberta`. Mensagens de terceiros nunca viram opção.

## Agentes externos: chaves e receitas de conexão {#agentes-externos}
Decisão: [`adr/036-agentes-externos.md`](adr/036-agentes-externos.md). Só agentes seus, dentro da Tailscale (URL padrão do `/conexao`: `https://gabi-finance.tail985643.ts.net:8443/mcp`, parâmetro `mcp.url`). Sem agentes em nuvem (precisam de URL pública).
- **Emitir:** painel › Gabi › Agentes › Nova chave. Nome obrigatório; vêm marcados os escopos do Hermes, sem `sensivel`. A chave aparece uma vez (botão Copiar); fechada a janela, não volta.
- **Editar escopos** não muda o segredo. **Revogar** vale na hora (a chamada seguinte dá `nao_autenticado`). **Rotacionar** emite outra com os mesmos escopos e revoga a antiga. **Ver chamadas** lista as 50 últimas (ferramenta, status, quando; nunca argumentos).
- **Conectar:** a tela mostra a receita pronta de cada cliente (Claude Code, Cursor, Codex CLI, Claude Desktop via `mcp-remote`, VS Code, Gemini CLI) com a URL e, logo depois de emitir, a chave preenchida. A sintaxe dos clientes muda: reconfira a receita antes de usar um cliente novo. Teste: pedir ao agente o saldo.
- **Risco aceito:** rotacionar ou revogar a chave do Hermes derruba o Telegram e o WhatsApp dele até o `~/.hermes/.env` (`GABI_FINANCE_TOKEN`) receber a nova e o `hermes-gateway` reiniciar.

## Hermes: lista de ferramentas, SOUL e vigia {#hermes}
- **Lista de ferramentas:** em `~/.hermes/config.yaml`, `mcp_servers › gabi_finance › tools › include` deve ser exatamente a lista oficial de [`fontes/hermes.md`](fontes/hermes.md) (33 ferramentas, sem curinga), gerada por `python -m tools.gerar_hermes` e testada. Depois de mudar: `sudo systemctl restart hermes-gateway` e `/new` no Telegram **e** no WhatsApp.
- **SOUL** (instruções do Hermes, só financeiro): `bash <clone>/deploy/instalar-hermes-soul.sh`, como o usuário do Hermes (sem sudo). Guarda um backup `SOUL.md.bak-<data>` se já havia um diferente e **não** reinicia o gateway.
- **Auditar promessas:** `python -m tools.auditar_promessas --desde AAAA-MM-DD` acha respostas do Hermes que disseram "anotado" sem uma chamada de escrita bem-sucedida (ADR-028).

## Vigia semanal (cron `no_agent` do Hermes) {#vigia}
Sem modelo, toda segunda às 09h: unidades `gabi-finance-*` e `hermes-*` em `failed`, fontes de dados em `erro` ou `parada` (envelope do `financeiro_saldo`) e promessas do Hermes sem escrita nos últimos 7 dias. Tudo certo = uma linha "tudo ok"; senão uma linha por problema. Falha (serviço fora, sem token) = "Falhou: vigia semanal (...)".
1. `cp -p ~/gabi-finance/deploy/hermes/scripts/vigia_semanal.py ~/.hermes/scripts/` (o clone do repositório precisa estar em `~/gabi-finance` do usuário do Hermes).
2. `hermes cron create '0 9 * * 1' --name vigia-semanal --script vigia_semanal.py --no-agent --deliver telegram --failure-deliver whatsapp`
3. Teste: `python3 ~/.hermes/scripts/vigia_semanal.py`.
- **Desfazer:** `hermes cron remove <id>` (id em `hermes cron list`).

## O que não é gasto e rol de assinaturas {#nao-gasto}
Decisão: [`adr/029-nao-gasto-e-rol-de-assinaturas.md`](adr/029-nao-gasto-e-rol-de-assinaturas.md).
- **Empresa sua:** no cadastro de empresas, `relacao: "pj_titular"` (sem isso o Pix para ela continua contando como gasto).
- **Reaplicar no histórico** (a captura reaplica sozinha a cada rodada; isto só antecipa e imprime o total de Gastos antes e depois): `cd /opt/gabi-finance && sudo -u gabifinance $PY -m gabi.dinheiro.nao_gasto --banco $BANCO`.
- **Corrigir um caso:** Gastos › Lançamentos, "é gasto / não é gasto" em cada saída ("deixar a Gabi decidir" tira a marcação), ou pelo Hermes (`financeiro_marcar_gasto`, `assinaturas_listar`, `assinatura_marcar`).

## Quem gastou (portadores) {#gastador}
Decisão: [`adr/030-gastadores.md`](adr/030-gastadores.md).
- **Portadores:** em Cadastros › Contas, "Quem usa" de cada cartão. Cartão com portador único preenche o gastador sozinho.
- **Histórico:** `cd /opt/gabi-finance && sudo -u gabifinance $PY -m gabi.dinheiro.gastador --banco $BANCO` (imprime contagens e o total por quem gastou; a captura repete sozinha).
- **Hermes:** `financeiro_indicar_gastador`.

## Reembolso por compra {#reembolso}
Decisão: [`adr/031-reembolso-por-compra.md`](adr/031-reembolso-por-compra.md). Pelo Hermes: `financeiro_marcar_reembolso`.

## Despesas: criar, mudar, dispensar e encerrar {#despesas}
Decisão: [`adr/032-despesas-crud.md`](adr/032-despesas-crud.md). Pelo painel (Caixa › A pagar e Cadastros › Despesas) ou pelo Hermes (`despesa_criar`, `despesa_mudar`, `despesa_mes`, `despesa_encerrar`, `despesa_excluir`, `despesas_listar`; ele mostra o que muda e só grava depois do sim).
- Encerrada não reabre: para voltar a pagar, crie uma despesa nova. No painel, encerrar pede confirmação e não tem desfazer; dispensar um mês tem "Desfazer".

## Assistente proativo: olhar à frente {#assistente}
Decisão: [`adr/037-assistente-proativo.md`](adr/037-assistente-proativo.md). Das quatro ferramentas desse pacote ficou só `olhar_a_frente` (só leitura, escopo `fin`): o que vem aí em caixa, recebimentos e vencimentos. As demais (promessas, preparar reunião, revisão da semana) dependiam de e-mail, agenda e documentos e saíram no corte. O resumo das 07:05 mostra "Olhando à frente" quando há caixa negativo ou recebimento atrasado há 10 dias ou mais.

## Ferramentas de administração (`tools/`)
Instaladas em `/opt/gabi-finance/tools/`: `semear_categorias`, `semear_donos`, `marcar_padroes`, `corrigir_moeda`, `comparar_agenda` e `conferir_virada`. As demais (`demo`, `gerar_amostras`, `gerar_docs_api`, `gerar_hermes`, `capturas`, `aceite`, `auditar_promessas`, `golden`, `grafo_imports`, `commitar.sh`) são de desenvolvimento e rodam no clone. Resumo de cada uma:

| Ferramenta | Para quê |
|---|---|
| `tools.conferir_virada` | Imprime saldos, A pagar do mês e projeção de 30 dias de UM banco (só leitura); a conferência da virada compara dois bancos com `diff` |
| `tools.corrigir_moeda` | Corrige o histórico em moeda estrangeira a partir do bruto (veja acima) |
| `tools.semear_donos`, `semear_categorias`, `marcar_padroes` | Aplicam seeds e corrigem origens, idempotentes |
| `tools.comparar_agenda` | Compara a agenda de compromissos com a do serviço financeiro antigo (critério de corte G21; só leitura) |
| `tools.gerar_docs_api` | Regera `docs/api.md` e `docs/openapi.json` (um teste falha se ficarem velhos) |
| `tools.gerar_hermes` | Regera a lista `tools.include` do Hermes em `docs/fontes/hermes.md` |
| `tools.auditar_promessas` | Respostas do Hermes que prometeram gravar sem gravar |
| `tools.aceite` | Mede o aceite da Fase 1 (7 dias conferidos, 90% classificado) |
| `tools.demo`, `gerar_amostras`, `capturas` | Banco sintético, amostras do painel e capturas de tela |
| `tools.grafo_imports` | Grafo de imports de `gabi/` (usado no corte, ver `docs/corte/`) |
| `tools.golden` | Gerava as saídas de referência do porte do módulo financeiro (histórico; precisa do `gabi-fin` antigo) |
