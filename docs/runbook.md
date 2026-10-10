# gabi.brain · Runbook
Convenção: `BANCO=/var/lib/gabi-brain/gabi.db`. Comandos como usuário `gabibrain` (`sudo -u gabibrain …`) e `PY=/opt/gabi-brain/venv/bin/python`.

## Subir e parar
- Status: `systemctl is-active gabi-brain-api` → `active`.
- Reiniciar: `sudo systemctl restart gabi-brain-api`. Parar: `sudo systemctl stop gabi-brain-api`.
- Logs: `journalctl -u gabi-brain-api -n 50 --no-pager`.
- Socket: `ls -ld /run/gabi-brain` → `drwx------ gabibrain`; `ss -ltn | grep 8080` → **vazio** (não há porta TCP). Se aparecer qualquer `:8080`, **pare o serviço** e investigue.
- Chamar a API à mão (como root ou `gabibrain`): `curl --unix-socket /run/gabi-brain/api.sock http://localhost/api/eu -H 'Tailscale-User-Login: <login>'`.

## Acesso (quem entra)
- Listar: `$PY -m gabi.acesso --banco $BANCO listar`.
- Adicionar: `$PY -m gabi.acesso --banco $BANCO adicionar <login-tailscale> <pessoa_id> boss|familia_vip|terceiros`.
- Remover acesso: apagar a linha de `acesso` (sqlite3) e conferir `listar`. Sem login em `acesso`, a pessoa recebe 403.

## Revogar tudo (tokens de agentes)
- `curl --unix-socket /run/gabi-brain/api.sock -X POST http://localhost/api/revogar-tudo -H 'Tailscale-User-Login: <seu-login>' -H 'Content-Type: application/json' -d '{"confirmo": true}'` → `{"revogados": N}`. Sem `confirmo: true` → 400 e nada muda.

## Carregar o staging
- `$PY -m gabi.importar --banco $BANCO --staging /home/ricardo/gabi-brain-migracao/staging` → imprime contagens. Pode rodar de novo: não duplica. Registra uma rodada `importacao-staging`.

## Backup e restauração
- Diário 03:30 (`gabi-brain-backup.timer`), com teste de restauração. À mão: `$PY -m gabi.backup --banco $BANCO --destino /var/backups/gabi-brain --testar`.
- Resultado: `gabi-brain-AAAA-MM-DD.sqlite` (600) e uma rodada `backup`. Falha de integridade → rodada `erro` e código de saída 1.
- **Restaurar:** `sudo systemctl stop gabi-brain-api`; copiar o backup desejado para `$BANCO`; apagar `gabi.db-wal` e `gabi.db-shm`; `sudo systemctl start gabi-brain-api`; conferir `/api/saude`.
- Cópia fora da VPS: ver "Backup fora da VPS" abaixo (a VPS não guarda a única cópia).

## Backup fora da VPS {#backup-fora}
Pacote semanal criptografado, para o Ricardo puxar; a chave privada nunca fica na VPS.
1. **Uma vez, na sua máquina:** `gpg --quick-generate-key ricardo-gabi-backup` e `gpg --armor --export ricardo-gabi-backup > backup.pub`. Copie só a **pública** para a VPS: `sudo install -m 644 backup.pub /etc/gabi/backup.pub`. Guarde a privada (e uma cópia dela) fora da VPS.
2. Domingo 04:00 BRT (`gabi-brain-exportacao.timer`) gera `/var/backups/gabi-brain/exportacao/gabi-brain-AAAA-MM-DD.sqlite.gpg` (600; guarda os 8 últimos) e uma rodada `exportacao`. Sem `/etc/gabi/backup.pub` a unidade nem roda; se o teste de restauração falhar, nada é exportado e o sino avisa. À mão: `sudo systemctl start gabi-brain-exportacao`.
3. **Puxar (G17):** `scp vps:/var/backups/gabi-brain/exportacao/*.gpg ./` e conferir com `gpg --decrypt gabi-brain-AAAA-MM-DD.sqlite.gpg > teste.sqlite && sqlite3 teste.sqlite 'pragma integrity_check'` (deve dar `ok`).
4. **Restaurar a partir do pacote:** decifrar na sua máquina, copiar para a VPS e seguir "Restaurar" acima.

## Alertas
| Sinal | Significa | Ação |
|---|---|---|
| `/api/saude` com `db != "ok"` | banco corrompido | parar a API e restaurar o último backup |
| rodada `backup` com `status=erro` | backup ou restauração falhou | rodar à mão com `--testar` e ler a mensagem |
| `ultimo_backup` nulo ou com mais de 2 dias | timer parado | `systemctl status gabi-brain-backup.timer` |
| 403 para alguém que deveria entrar | login fora de `acesso` | `gabi.acesso adicionar` |

## Verificação dos comandos (08/10/2026, banco temporário)
`importar` 2× → 18 novas, depois 0 · `acesso adicionar/listar` ok (login normalizado em minúsculas) · `backup --testar` → arquivo 600 e contagens iguais às da origem · 2º backup no mesmo dia → "FALHOU", código 1 · rodadas `importacao-staging` e `backup` gravadas. Os comandos de `systemctl`, `ss` e `tailscale` só são verificados após a implantação (T0.8).

## Servidor MCP e tokens de agentes (Fase 1)
- O MCP escuta **só em 127.0.0.1:8081** (`gabi-brain-mcp.service`), Streamable HTTP em `/mcp`, e exige `Authorization: Bearer <token>`. Para agentes fora da VPS (Claude Code no seu Windows): `sudo tailscale serve --bg --https=8443 http://127.0.0.1:8081` (TLS na rede privada; o token continua obrigatório).
- Emitir (o token aparece **uma vez**; o banco guarda só o hash): `sudo -u gabibrain /opt/gabi-brain/venv/bin/python -m gabi.mcp.tokens emitir hermes fin` (escopos: `fin,docs,trabalho,pedidos,propostas,sensivel`). Você cola o token no agente; eu não o vejo.
- Listar: `... -m gabi.mcp.tokens listar` · Revogar um: `... revogar <id>` · Revogar todos: `POST /api/revogar-tudo` (ver acima).
- Cada chamada fica em `chamada_mcp` (token, ferramenta, escopo, status `ok|sem_escopo|erro|nao_autenticado`). Para ver: `sqlite3 $BANCO "select quando, ferramenta, status from chamada_mcp order by id desc limit 20"`.
- Só existem ferramentas de **leitura** (`docs/api.md#mcp`). Não há como enviar, pagar, apagar, aprovar nem ligar regra por MCP (R13).
- Se um agente receber `sem_escopo`, o token não tem o escopo da ferramenta: emita outro com o escopo certo (não amplie o de outro agente).

## Telas de dinheiro (Fase 1) {#telas-dinheiro}
O painel é `painel/` (React + Vite); `npm run build` gera `gabi/painel/` e a API serve em `/`. Comandos e regras: `painel/README.md`. Cada tela responde uma pergunta:

| Tela | Pergunta | De onde vem |
|---|---|---|
| Caixa · Resumo | Tenho caixa? | `GET /caixa/resumo` (saldos do caixa único, faturas, assinaturas, atenção) |
| Caixa · Semanas | Como o caixa anda, semana a semana? | `GET /caixa/semanas` + `GET /lancamentos` da semana clicada |
| Caixa · A pagar | O que vence, e quando? | `GET /contas-pagar`; "Já paguei" = `POST /contas-pagar/{id}/paga`; bloco "Rodadas" = `GET /rodadas` (2 últimas de extrato, com contas reprovadas quando não conferida) |
| Gastos · Lançamentos | De quem é cada gasto? | `GET /lancamentos?pendente=para_quem`, `PATCH /lancamentos/{id}`, sugestões |
| Gastos · Para onde vai | Para onde vai o dinheiro? | `GET /destino`, `GET /destino/agrupado` |
| Gastos · Cartões | Quanto já foi no cartão? | `GET /cartoes` + lançamentos, edição em lote `POST /lancamentos/lote` |
| Gastos · Parcelas | Quanto já está comprometido? | `GET /parcelas` |
| Gastos · Assinaturas | O que é assinatura esquecida? | `GET /assinaturas`, `PATCH /assinaturas/{id}` |
| Regras | O que a Gabi sugere classificar? | `GET /regras`, `GET /sugestoes`, aprovar (com `edicao` da categoria)/rejeitar/ligar |
| Sino e menu | Quantos itens pedem decisão? | `GET /contagens` (`sino` e `menu` por área: caixa, gastos, regras) |
| Cobrar · Reembolsos | Quem me deve? | `GET /cobrar/reembolsos`; `POST /cobrar/reembolsos` + `/{id}/cobrado`; Bekaa = lote (`POST /cobrar/lote/montar` e `/{id}/executar` com a confirmação exata) |
| Cobrar · Comprovantes | O que o Paperless já tem? | `GET /cobrar/comprovantes`; `POST /cobrar/vinculos/{id}/confirmar\|rejeitar` |
| Cobrar · E-mail de cobrança | O que vou cobrar, e de quem? | `GET /cobrar/cobrancas`, `POST /cobrar/cobrancas` (rascunho); enviar = 403 (ADR-006) |
| Caixa · Pedidos | O que me pediram para pagar? | `GET /cobrar/pedidos`, `POST /cobrar/pedidos/{id}/decidir` |
| Cadastros · Contas | Quais contas entram no caixa único? | `GET/PATCH /cadastros/contas` |

**Ver sem dados reais:** `python -m tools.demo 8099` sobe a API com banco sintético (relógio fixo em 08/10/2026) e o painel compilado; mande o cabeçalho `Tailscale-User-Login: boss@x.com`.
**Comparar com o protótipo (G14):** `python -m tools.capturas` grava `docs/design/<tela>-{prototipo,app}-{claro,escuro,celular}.png` (precisa do demo em :8099, do protótipo servido por `python -m http.server 8098` em `prototipo/` e de `playwright install chromium`).
**Testes das telas** usam respostas reais da API (`painel/tests/amostras`, geradas por `python -m tools.gerar_amostras`); `tests/test_amostras_painel.py` falha se a API mudar e as amostras não.

## Reembolsos {#reembolsos}
Despesa paga no PF para uma **empresa contratante** (ness, IONIC; `empresa.relacao='contratante'`, cadastro do Ricardo) vira item de reembolso. Estados: `a_cobrar → cobrado → parcialmente_recebido → quitado` (`cobrar/reembolso.py`).
1. `criar_reembolso(con, empresa_id)` junta os itens ainda sem cobrança (a Bekaa, `relacao='pj_titular'`, **nunca** entra: vai ao lote do Nibo).
2. `marcar_cobrado` quando o Ricardo cobra (o e-mail é só rascunho, ADR-006).
3. `conciliar_recebimento(con, empresa_id, credito_id)`: entrada em conta PJ baixa os itens **já cobrados**, do mais antigo ao mais novo; a sobra volta no resultado; o mesmo crédito não baixa duas vezes (`reembolso_baixa`).
4. Para a Gabi propor o vínculo de um comprovante ao item, ver `#comprovantes`.

## Lote do Nibo {#lote-nibo}
Despesa da **Bekaa** (`empresa.relacao='pj_titular'`) paga em conta PF vira um agendamento a pagar ao sócio no Nibo. É a **única gravação externa** do app.
1. `montar_lote(con, dia)` lista as despesas ainda sem agendamento ok e gera o texto `Lançar no Nibo da Bekaa: N despesas, R$ X.` (N e X calculados no servidor). Montar de novo no mesmo dia refaz o lote aberto.
2. O Ricardo confirma **com esse texto exato**; texto diferente (um centavo) = 409 `confirmacao_divergente` e nada é gravado.
3. `executar_lote` cria, por item, o agendamento com `reference gabi:<lancamento_id>` (antes consulta a `reference`: se já existe, pula) e anexa o comprovante confirmado (Paperless). Erro num item não desfaz os outros.
4. **Reprocessar:** o item fica `erro` (veja `lote_nibo_item.erro`); o próximo `montar_lote` o inclui de novo. Se o agendamento já foi criado mas o anexo falhou, o reprocesso só anexa. Repetir é seguro: nunca duplica.
5. **Baixa:** quando a PJ reembolsa o sócio (Pix C6 PJ → Itaú PF de valor igual), `texto_baixa` gera `Baixar no Nibo: <despesa>, R$ X, pelo Pix de DD/MM.` e `executar_baixa` só baixa com esse texto, uma vez por crédito.
6. **Desfazer no Nibo (manual):** o app não apaga nada. Localize o agendamento pela `reference gabi:<id>` e exclua pela tela do Nibo; depois marque o item para reprocessar apagando a linha de `lote_nibo_item` correspondente.
7. **Pré-requisitos (cadastros):** `parametro nibo_socio_id` (stakeholderId do sócio), `categoria.nibo_category_id` em cada categoria usada, `empresa.relacao`. Sem a categoria equivalente o item vira erro, nunca adivinha.

## Rotina de dinheiro (donos, rodada, notas, avisos) {#rotina-dinheiro}
- **Aplicar donos padrão** (depois de editar `seeds/donos-padrao.json`): `sudo ~/aplicar-donos.sh`. Idempotente e auditado; não sobrescreve decisão do Ricardo (`voce`) nem regra (`regra`).
- **Rodar a rodada à mão:** `sudo systemctl start gabi-brain-extratos` (captura, conferência, classificação, compromissos e recebimentos propostos); ler com `journalctl -u gabi-brain-extratos -n 20 --no-pager -o cat`. Saldos: `gabi-brain-saldos`.
- **Importar notas (NFS-e da Bekaa):** `sudo ~/instalar-notas.sh` (instala e roda `gabi-brain-notas`); o timer `gabi-brain-notas.timer` repete sozinho. Os recebimentos casados aparecem em Cobrar → Notas a receber para confirmar ou rejeitar.
- **Ler avisos:** sino do painel; por linha de comando `sudo -u gabibrain /opt/gabi-brain/venv/bin/python -m gabi.avisos`. Tipos: `rodada_parada`, `conta_atrasada`, `cobrada_apos_cancelar`, `vence_hoje`, `servico_falhou` (qualquer unit com `OnFailure`), `exportacao_parada` (sem pacote há mais de 9 dias).
- **Restaurar backup:** ver "Backup e restauração" e "Backup fora da VPS".
- **Comparar com o gabi-financeiro (G21):** `python -m tools.comparar_agenda --mes AAAA-MM`; saída vazia por 7 dias é o critério de corte.

## Trabalho: credenciais e rodada {#trabalho-credenciais}
O job `gabi-brain-trabalho.timer` (a cada 15 min, 06h–22h BRT) lê e-mail, agenda e tarefas das caixas com estado `sim` (Cadastros › Caixas de e-mail) e conclui na origem as tarefas que você mandou concluir no painel. Só lê; nunca envia nem apaga (R2). As credenciais ficam **só** em `/etc/gabi/trabalho.env` (0600, legível pelo usuário `gabibrain`; colocadas por você, R5). Sem elas, cada caixa vira o aviso **"Reconectar a caixa …"** no sino, que fecha sozinho quando a leitura volta.

| Variável | Para quê |
|---|---|
| `GRAPH_TENANT`, `GRAPH_CLIENT_ID`, `GRAPH_CERT_KEY_FILE`, `GRAPH_CERT_X5T` | Graph (IONIC; ness depois da migração). `GRAPH_CERT_KEY_FILE` = caminho da chave privada PEM. Aprovação do admin: `link_aprovacao_admin` (docs/fontes/graph.md). |
| `GOOGLE_SA_EMAIL`, `GOOGLE_SA_KEY_FILE`, `GOOGLE_SA_DOMINIOS` | Conta de serviço com delegação (ex.: `bekaa.eu,esper.ws`); a caixa é o `sub`. |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_REFRESH_<ENDEREÇO>` | OAuth próprio (ness, Gmail). O nome é o endereço em maiúsculas com `_` (ex.: `GOOGLE_REFRESH_RICARDO_NESS_COM_BR`). |

| `LINEAR_API_KEY` | Linear (somente leitura): alimenta Tarefas › Entregas. Chave pessoal criada em Linear › Settings › API. |

Rodar à mão: `sudo systemctl start gabi-brain-trabalho`; ler: `journalctl -u gabi-brain-trabalho -n 20 --no-pager -o cat`. Concluir tarefa no painel registra o pedido (`tarefa.pedido_concluir_em`); a tarefa só aparece como concluída depois que o job conclui na origem.

## Comprovantes Pix {#comprovantes-ingestao}
`gabi-brain-comprovantes.timer` (07h BRT) lê o texto dos documentos do Paperless pela ponte do serviço de fontes, grava o comprovante, **propõe** vínculos aos lançamentos (nunca confirma, R1) e acrescenta a etiqueta `gabi:comprovante`. Idempotente por documento. Rodar à mão: `sudo systemctl start gabi-brain-comprovantes`.

## Saúde, Família e Rumo {#saude-familia}
- **Chave da saúde:** crie `/etc/gabi/saude.key` (32 bytes crus, 64 hex ou base64; `root:gabibrain` 0640) e reinicie a api. Sem ela, `/api/v1/familia/*` responde 503. O cofre é `/var/lib/gabi-brain/saude.enc` (AES-256-GCM, ADR-014). **Guarde a chave fora da VPS: sem ela os exames não abrem.**
- **Quem vê:** pela linha `saúde` da matriz de acesso (`total` = todos, `parcial` = só a própria pessoa, `nenhum`/sem linha = ninguém além do boss). Cadastre o login de cada familiar: `python -m gabi.acesso adicionar login pessoa_id familia_vip`.
- **Laudo:** Família › "Ler laudo" (nº do documento no Paperless) grava só PROPOSTAS; "Confirmar e registrar" exige escolher de quem é o laudo.
- **Rumo:** `GET /api/v1/rumo?ano=AAAA` (entradas, saídas, poupança, gasto por pessoa/frente, patrimônio mês a mês).
- **Tailscale (G13):** convide cada familiar e limite por ACL ao `gabi:443` (sem SSH nem outras máquinas); confira o limite de usuários do plano.

## Cofre Obsidian {#obsidian}
`python -m gabi.familia.obsidian --destino /pasta/do/cofre --para p1` exporta os `.md` (família com CPF, saúde, frentes, decisões, memória) **de uma pessoa**, na pasta `<destino>/<id da pessoa>/`; cada um recebe só o que a matriz de acesso libera (`parcial` = só o que é dele). Saída idêntica se nada mudou. Se você editar um arquivo no Obsidian, a próxima exportação grava a edição como pendente (`edicao_externa`) e **não** sobrescreve o arquivo nem muda o banco; ao rejeitar a edição, o arquivo volta ao exportado. Sincronize **só** por Tailscale/Syncthing ou nuvem criptografada ponta a ponta: a pasta contém CPF e saúde.
