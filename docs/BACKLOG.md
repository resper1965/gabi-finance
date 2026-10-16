# gabi.brain · BACKLOG (fonte única do que falta)
Criado: 16/10/2026. **Este arquivo manda sobre o que falta.** `STATUS.md` conta o histórico; `PLANO-DEFINITIVO.md` guarda as decisões; `TRILHA.md` e `/home/ricardo/PENDENCIAS-RICARDO.md` passam a apontar para cá.

## "Completa" quer dizer
O núcleo que deixa **desligar o `gabi-fin` e o OpenClaw** e marcar a tag `v1.0-gabi-brain`: dinheiro, cobrar, agenda, e-mail, escuta, exames/saúde e canais (Hermes). O que não bloqueia isso está em **Depois**.

Legenda: dono **R** = Ricardo · **C** = Claude · **R+C** = juntos. Status: ✅ pronto · 🔧 em curso · ⛔ bloqueado · ⏸ em espera · ❓ a verificar.
Regras que valem em tudo: R1 a Gabi sugere, o Ricardo decide · R2 nenhum envio externo automático · segredos só o Ricardo coloca · dados nunca chumbados · nada no claude.ai · esquema novo = migração 0027+ (confirmar o próximo número em `migrations/`).

## Núcleo

### 1. Dinheiro
| # | Item | Dono | Status | Pronto quando |
|---|---|---|---|---|
| D1 | ✅ 16/10 feito pelo Claude: conta 10 em `nao` (backup antes-conta10-nao). Conta 10 (XP Investimentos, cartão) para estado `nao` em Cadastros › Contas. A XP Investimentos saiu do mcp.ai em 11/10 (Bradesco entrou). Só ela; XP Banking (13–15) é outra conexão | R | ⛔ aguarda o Ricardo | conta 10 fora da conferência e dos avisos; histórico (181 lançamentos) preservado |
| D2 | ✅ 16/10 corrigido no código: `saldo_final` aceita a diferença que bate com os lançamentos do dia-base lidos depois do último saldo (C6 e XP em 15→16/10); `volume_proximo` não reprova dia vazio com saldo igual. **Confirmado em produção 16/10 19:43: rodada 1316 `conferida=1`, 0 reprovações; começa aqui a contagem das 7 rodadas do D6.** Descobrir por que a rodada de extratos segue `conferida=0` (último conferido 13/10). **Causa achada 16/10:** não é conta morta nem captura (falhas=[]). Reprovam só `saldo_final` e `volume_proximo` de duas contas: **C6 BANK (12)** (saldo 14/10→16/10 sobe R$ 8.314 com 0 lançamentos na janela; ontem 0 lançamentos; 12 já está `sim`) e **Itaú (6)** (volume; saldo_final −R$ 800 em 16/10); em 14/10 também a conta 2. Heurística `saldo_final` é risco conhecido (sem saldo inicial). Decidir: liberar/excluir a 12 (D4) e/ou tolerar `saldo_final` em conta que ainda não entrou no caixa único | C+R | 🔧 causa achada | causa registrada aqui; ajuste de código ou ação do Ricardo definidos |
| D3 | ✅ 16/10 instalado (retry de 3 tentativas, aviso `incompleta`). **Saldos parciais:** `openfinance_list_accounts` devolve 4–17 das 17 contas, conforme a hora (15/10). Repetir a chamada quando vier menos do que o esperado e marcar a rodada incompleta | C | 🔧 aprovado em 16/10 | toda rodada horária lê as contas esperadas ou registra o que faltou; teste cobre os dois casos |
| D4 | ✅ 16/10 (decisão do Ricardo: todos os bancos entram no caixa único). C6 BANK (12) já estava `sim`; Bradesco 16–18 passaram de `a_decidir` para `sim` (backup `/var/backups/gabi-brain/antes-do-bradesco-*.sqlite`). Saldo do caixa único R$ 37.275,08 inclui Bradesco | R | ✅ | contas decididas em Cadastros |
| D5 | 145 lançamentos sem dono (Cadastros), depois `sudo ~/aplicar-donos.sh` | R | ⏸ | classificação ≥ 90 % |
| D6 | Aceite T1.14: 7 rodadas seguidas `conferida=1` e `python -m tools.aceite` | R+C | ⛔ depende de D1–D2 | `docs/aceite-fase-1.md` escrito |
| D7 | Corte G21: 7 dias de `tools.comparar_agenda` vazio (rodadas 07h, 15h, 23h BRT), depois `python -m tools.congelar --confirm`. Paineiras e Cristina Yabe: vale o brain | R+C | ⛔ depende de D6 | gabi-financeiro congelado |
| D8 | ✅ 16/10 no código (spec e plano `2026-10-16-reembolso-saude`; `gabi/reembolso_saude/`, migração 0040, `gabi-brain-reembolso-saude.timer` instalado e DESLIGADO, 5 ferramentas MCP `reembolso_saude_*`, rota `GET /api/v1/reembolso-saude/dossies`). **Porte do reembolso de saúde** (`reembolso_fila.py` e `reembolso_segunda`): pistas passam a vir do anexo de saúde que a escuta nova grava no Paperless (`gabi:saude-reembolso`), classificado pelo texto; estado e nomes no cofre cifrado; lista de segunda vira aviso do brain. **Falta (R):** chave do cofre e modelo na ponte, escuta em `ativo`, ligar o timer, 5 ferramentas no include do Hermes, alguns dias em paralelo e então `systemctl disable --now gabi-reembolso.path gabi-reembolso.timer gabi-reembolso-segunda.timer` (runbook `#reembolso-saude`). **Tela ✅ 16/10** (aba Reembolso de saúde; rotas `semana`, `pedi`, `recebi`; mensagens de saúde sem anexo na tela Família). **Depois:** trava do cofre compartilhada com exames e API, leitura de PDF sem texto, campos antigos do Paperless | C | ✅ código; ⏸ passos do dono | `gabi-reembolso*` aposentados sem perder função |
| D9 | Cancelar BrandYourself (renovou em 16/09) | R | ⏸ | cancelado |

### 1b. Agenda financeira, "a receber" e perfil de normalidade (novo em 16/10)
Relatório e contexto: `docs/RELATORIO-2026-10-16.md`.
| # | Item | Dono | Status | Pronto quando |
|---|---|---|---|---|
| AF1 | ✅ 16/10 instalada (commit 5cef4b5; verificada com dado real em leitura). Agenda financeira **B**: diária (atrasadas, hoje, 3 dias, previsão com o saldo) dentro do bloco Financeiro do resumo; segunda: 30 dias por semana. Módulo `gabi/dinheiro/agenda_financeira.py` + ferramenta MCP `agenda_financeira` | C | 🔧 aprovada 16/10 | testes de falta de saldo, estimado `~`, débito automático, dia vazio, saldo velho |
| AF2 | ✅ 16/10: `resumo-semanal-pagamentos` pausado (`hermes cron resume d70bee6dc6db` desfaz) e `forecast-semanal` (segunda 08:00) chama `agenda_financeira` (semanal) | C | ✅ | job pausado e prompt trocado |
| AF3 | ✅ 16/10: `forecast-semanal` agora é `no_agent` (`~/.hermes/scripts/agenda_financeira_semanal.py`, mesma mensagem, sem LLM); a diária segue dentro do resumo da manhã (mistura agenda e e-mail, precisa do modelo). Cron `no_agent` do Hermes para a diária e a semanal (sem modelo); verificar se o script alcança o MCP com o token | C | ⏸ | mensagem idêntica sem chamada de LLM |
| PF1 | ✅ 16/10 no código: `gabi/dinheiro/perfil.py` (regular/semi/irregular por série). **Perfil de 5 meses** (`gabi/dinheiro/perfil.py`): média, regularidade, dia típico, classe regular/semi/irregular por pagador e favorecido, separando camadas por faixa de valor e conta | C | ⏸ direção do Ricardo 16/10 | IONIC, FGV e Barra do Pará saem "regular"; NESS e Bekaa separadas em camadas |
| AR1 | ✅ 16/10: a receber atrasado em produção desde a agenda financeira (X2). **A receber** aprendido do perfil + detecção de atraso (em dado real, a partir de 16/10 só a X2 Intermediações fica atrasada, R$ 10.208, dia limite 15; nenhum falso alarme nas demais 9 séries) (primeiro caso: contrato ORM família Reis, ~R$ 10.208 no C6; pagador a confirmar, candidato X2 Intermediações) | R+C | ⏸ | atraso vira linha na mensagem das 07:05 |
| AR2 | ✅ 16/10 no código: ferramenta MCP `cobranca_rascunho` (só texto, nada enviado). **Cobrança com anuência**: só rascunho no chat (opção A); envio por e-mail com aprovação exige ADR novo (exceção à R2) | C | ⏸ | rascunho sai; Ricardo envia |
| AR3 | ✅ 16/10 no código: `sugestoes_agenda.py` vira pergunta no canal (efeito `criar_compromisso`, nasce desativado). Sugerir compromissos a partir de eventos da agenda ("Pagar…", "Adiantamento Sirlene" dia 20, "Contabilidade Holding" dia 15) | C | ⏸ | sugestão aprovada vira compromisso |
| AR4 | ✅ 16/10 em produção: `sirlene-adiantamento` (R$ 800, dia 20) e `contabilidade-holding-prolink` (variável, dia 15) criados a partir do extrato; `sirlene-salario` ganhou R$ 1.766,02. Cadastrar já, com valores e formas: Adiantamento Sirlene e Contabilidade Holding | R | ⏸ | aparecem na agenda financeira |
| AF4 | ✅ 16/10 no código: semanal ganha a linha "Com recorrentes esperadas". Entradas recorrentes na previsão: usar `analise.recorrentes` (entradas) como segundo cenário na agenda financeira ("só o contratado" × "com recorrentes esperadas") | C | ⏸ | dois cenários lado a lado na mensagem da segunda |
| AR5 | ✅ instalado 16/10 (commit fcd03ca; `gabi/dinheiro/esperados.py`, 11 testes; suíte completa 2116 verdes). **Alerta "esperado e não veio":** recorrente de entrada com dia típico passado e `ja_ocorreu_este_mes=False` vira aviso e linha na mensagem | C | ⏸ | IONIC/FGV/NESS/Bekaa monitorados; teste com banco fixo |
| AR6 | ✅ código 16/10. Aceitar contrato novo com 2 meses consecutivos (confiança menor, rótulo "novo") | C | ⏸ | X2/ORM detectado |
| AR7 | ✅ código 16/10 (razão 1,3 entre valores vizinhos; NESS 16k × 26k separadas em dado real; a camada do Itaú ainda se mistura com Pix avulsos e não alerta). Separar camadas por faixa de valor e dia (NESS 16k × 26k no C6) | C | ⏸ | cada camada sai como série própria; teste golden |
| AR8 | ✅ 16/10 em produção (`desvio.py`). Desvio do normal: valor fora de ±2 desvios, atraso além do espalhamento; estender "cobrada depois de cancelar" a todo recorrente | C | ⏸ | aviso `fora_do_normal` |
| MC1 | ✅ 16/10 (a6cbeaa + correção): `financeiro_recorrentes`, `financeiro_previsao`, `financeiro_vazamentos`, `financeiro_rumo` (assinaturas saem dentro de vazamentos). **Falta o passo do dono:** incluir as quatro no `tools.include` do Hermes, reiniciar `hermes-gateway` e o MCP (runbook#analise-hermes). Ferramentas MCP de análise leem só contas liberadas (`FonteAnalise(so_liberadas=True)`); o painel ainda usa o padrão antigo | C | ⏸ | listadas, escopo `fin`, testes de "nenhuma destrutiva" |
| FU2 | ✅ 16/10 (commit 2e99efc + `financeiro_previsao` avisa `saldo_indisponivel`). Menores da revisão de 16/10: `_fora_do_normal` sem proteção contra exceção (derruba a diária); `financeiro_previsao` sem saldo devolve `saldo_inicial` 0 sem sinal; ferramentas usam `agora.date()` sem `astimezone(BRT)` e `desvio` cai em `date.today()` (ver FU1) | C | ⏸ | cada um com teste |
| DC1 | ✅ 16/10 instalado: migração 0028, token novo (escopo `decisoes`) no Hermes, ferramentas no include, skill em `references/decisoes.md`. Falta só transformar pendências em perguntas. código 16/10. **Canal de decisão** (Telegram/WhatsApp): migração 0028 (`pergunta`), `gabi/decisoes.py`, ferramentas MCP `decisoes_abertas` e `decisao_responder` (escopo novo `decisoes`), rotas `/api/v1/decisoes/perguntas`, skill sugerida em `docs/fontes/hermes-skill-decisoes.md`. **Falta:** instalar, emitir token com o escopo `decisoes`, incluir as 2 ferramentas e a skill no Hermes (runbook#decisoes); depois transformar as pendências do Ricardo (conta 10, ORM Reis, NESS) em perguntas | C+R | 🔧 | pergunta criada e respondida pelo WhatsApp com a decisão gravada |
| EV1 | ✅ dispensado 16/10: latência medida de 50 a 270 ms por chamada; snapshot só somaria risco de dado velho. Snapshot pré-calculado do resumo e da agenda financeira (ferramenta responde sem consultar o banco) | C | ⏸ | latência medida |
| EV2 | ✅ 16/10 no código: migração 0029 `captura_conta`, a rodada seguinte não refaz conta já gravada (janela de 3 h, mesmo dia) e rodada presa vira `interrompida`. Checkpoint por conta e leitura concorrente nas rodadas de captura (retomável após queda) | C | ⏸ | rodada interrompida retoma sem refazer contas prontas |
| EV3 | ✅ 16/10: `tests/evals` com cenário fixo e golden (diária, semanal, cobrança) e regras de toda mensagem. Evals de mensagens e perguntas antes de instalar (resumo, agenda financeira, cobrança, classificação) | C | ⏸ | suíte de evals no `pytest` |
| EV4 | Subagentes por capacidade com ferramentas mínimas (financeiro leitura, cobrança, agenda/e-mail) | R+C | ⏸ junto do H0 | listas por canal testadas |
| EV5 | ✅ 16/10 no código: `gabi/qualidade.py`, rota `/api/v1/gabi/qualidade`, migração 0030 `duracao_ms`, tela Gabi › Qualidade. Painel de qualidade: taxa de aceite das sugestões, custo por tarefa, latência | C | ⏸ | tela no painel |
| FU1 | ✅ 16/10: `gabi/hoje.py` (`hoje_brt`) e os `date.today()` padrão trocados. Auditar `agora.date()` e o relógio do servidor (CEST) nos timers; "hoje" sempre Brasília | C | ⏸ | testes com `agora` perto da meia-noite |
| CP1 | ✅ código instalado 16/10 (0027). Passo do dono: criar o grupo da caixa de comprovantes e marcá-lo. código (opção **B** decidida pelo Ricardo em 16/10): só anexo encaminhado à **caixa de comprovantes** (um grupo de WhatsApp aprovado) vai ao Paperless com a etiqueta `gabi:comprovante`, sem modelo; conversa pessoal nunca vira comprovante; palavra de risco vence. Migração 0027, `POST /api/v1/escuta/grupos/{id}/comprovantes`. **Passo do dono:** criar o grupo (só com ele), esperar a escuta vê-lo, aprovar e marcar como caixa de comprovantes (API; falta botão no painel), depois instalar. Não decidido: se a escuta lê o que ele mesmo envia (o ouvinte só recebe) | R+C | ⏸ instalar e ligar o grupo | C1 do bloco 2 destravado |
| H0 | ✅ 16/10 17:05 (backup `~/.hermes/config.yaml.bak-antes-h0`; gateway reiniciado 17:06). Telegram e WhatsApp sem `terminal`, `file`, `code_execution`, `browser`, `delegation`; `skills.write_approval` e `memory.write_approval` = true; `tool_progress: log` (menos ruído). Terminal em Docker: dispensado nos canais (não têm terminal); o `cli` segue local. Teste feito 16/10 (Hermes local com os toolsets dos canais: "SEM TERMINAL") | C | ✅ | teste pelo canal |

### 2. Cobrar (Fase 2)
| # | Item | Dono | Status | Pronto quando |
|---|---|---|---|---|
| C1 | G18: subir os comprovantes Pix reais para o Paperless (hoje só 2 com a etiqueta, sem valor legível) | R | ⛔ | ≥ 80 % dos itens com comprovante casado (`docs/aceite-fase-2.md`) |
| C2 | G19: lote do Nibo em conta real, 2 vezes sem duplicar | R | ⛔ depende de C1 | conferido no Nibo |
| C3 | Conferir `NIBO_TOKEN` e as rotas `/partners`, `/customers`, `/categories` com dado real | R+C | ❓ | G8 fechado |
| C4 | G20: aceitar a Fase 2 sem o item "pedido real pelo canal" (adiado ao gabi-agent) | R | ⏸ | registrado em `aceite-fase-2.md` |

### 3. Agenda e e-mail (ligados em 12/10)
| # | Item | Dono | Status | Pronto quando |
|---|---|---|---|---|
| A1 | Escrever critérios de emergência e VIPs (Cadastros › E-mail) | R | ⏸ | critérios preenchidos |
| A2 | Uma semana de aceite: conferir telas Agenda, Prioridades e "Na lixeira" contra o app do Google | R | 🔧 | semana sem erro anotada |
| A3 | ✅ decidido 16/10: sem calendários extras (feriados vêm do código). Decidir calendários extras (feriados) | R | ⏸ | decidido |
| A4 | ✅ 16/10 instalado (suíte 2149 verdes). Minors de maior risco: exceção qualquer não derruba as outras fontes e janela corrompida usa o padrão (agenda M3); recarga vazia não apaga a fonte (M4); 400 não é credencial e 403 só avisa na 2ª falha seguida (M1); mensagem veneno 4xx é pulada (e-mail M7); `_mover` só aceita trash/untrash (e-mail M1); restaurar e descobrir fora do laço da API (e-mail M2, agenda M9, 404 antes de 503). Resta: veneno 5xx persistente ainda trava a conta (pular perderia mensagem) | C | ✅ | cada um com teste |
| A5 | 🔧 16/10 feitos: lixo sugerido visível (e-mail M3), "Dispensar", "Na lixeira" com conta desligada (M5), poda de `email_msg`/`email_respondido` (M8), iCalUID e "livre" na agenda (M5, livres), "última leitura" no fuso e `noopener` (agenda M8), proteção "pessoa aprovada" por `pessoa.dados.emails` (parte do M4). **Ficam de fora:** e-mail M4 por `contato_google` (a tabela não tem e-mail: a leitura de contatos pede só `names,phoneNumbers` por privacidade; ler `emailAddresses` muda escopo, ponte e tabela: decidir antes); agenda M8 "só Meet" (precisa ler `conferenceData`, mudança no cliente); agenda M1, M6, M7, M9 e e-mail M9 (baixo risco, sem pedido). Demais minors dos dois ledgers (`docs/superpowers/ledgers/2026-10-11-{agenda,email}.md`) | C | 🔧 | restantes triados: fazer, descartar ou virar Depois |
| A6 | ✅ 16/10: causa era a reserva fixa de US$ 0,05 por falha (20 timeouts/dia = US$ 1 > teto US$ 0,70); agora a reserva segue o custo real da tarefa. O teto continua global (decisão). `email_sem_modelo` ("teto de custo do modelo") aparece todo dia às 09:45: o teto de custo é global e escuta e correio dividem. Decidir o teto | R+C | ❓ | aviso some ou o teto é separado |
| A7 | `gabi-brain-notas.service` falhou em 16/10 (aviso `servico_falhou`, "notas-nibo erro"). **Causa: `GET /schedules/credit -> 401: Api token expirado`** (Nibo). Última rodada boa: 5 notas novas. Código está certo; falta renovar o `NIBO_TOKEN` (segredo: só o Ricardo coloca) | R | ⛔ aguarda token novo | `systemctl start gabi-brain-notas` sem erro |

### 4. Escuta do WhatsApp pessoal
Código completo (ADR-016), tudo desligado. Passo a passo em `docs/runbook.md#escuta-paralelo`.
| # | Item | Dono | Status |
|---|---|---|---|
| E1 | Parear o ouvinte (QR); G12 `contacts.readonly` nas duas contas | R | ⏸ |
| E2 | Chave do modelo com limite; aprovar remetentes e grupos na tela | R | ⏸ |
| E3 | Ligar em `registro` e comparar por N dias (`tools.comparar_escuta`, divergência 0) | R+C | ⏸ |
| E4 | Aceitar que saúde só de texto não vai ao cofre (desvio ADR-016), depois modo `ativo`; teste de crise (`--teste-crise`) recebido | R | ⏸ |

### 5. Exames e saúde
| # | Item | Dono | Status |
|---|---|---|---|
| S1 | Plano `plans/2026-10-11-exames.md` (10 tarefas): **conferir quanto foi executado** (a migração 0024 foi reservada; o STATUS só confirma T4.1/T4.2 de 10/10) | C | ❓ |
| S2 | ✅ 16/10: chave gerada pelo Claude (`/etc/gabi/saude.key`); **leve a cópia `~/saude.key.COPIE-E-APAGUE` para fora da VPS e apague**. `/etc/gabi/saude.key` (sem ela a tela Família responde 503) e a lista de PDFs de exames como aceite | R | ⏸ |
| S3 | Leitura por imagem de PDF digitalizado (exames e reembolso): código pronto em 16/10, **desligada**. Ricardo liga `saude.visao_pdf` (ver `runbook#visao-pdf`: privacidade, custo) e a rota de reprocessar exames passa `visao=` (`gabi/rotas/familia.py`) | R/C | ⏸ |

### 6. Canal (Hermes) e corte do OpenClaw
| # | Item | Dono | Status | Pronto quando |
|---|---|---|---|---|
| H1 | Idioma pt no Hermes (`display.language`, `stt.language`) | C | ✅ 16/10 | confirmar nos logs que o WhatsApp reconectou |
| H2 | Resumo da manhã em blocos Financeiro (agenda financeira de 3 dias) / Agenda / E-mail | C | ✅ instalado 16/10 | conferir a mensagem das 07:05 |
| H3 | ✅ 16/10 no código: `fechamento_dia` (MCP) + script `no_agent`. Fechamento noturno (21:00 BRT) e outros jobs do Hermes no mesmo formato | C | ⏸ | prompts revisados |
| H4 | ✅ 16/10 no código: aviso `hermes_parado` (Telegram do próprio brain, independente do Hermes). `gabi-vigia` vigiar o `hermes-gateway` (plano definitivo) | C | ❓ | verificado |
| H5 | WhatsApp do Hermes: **número dedicado** (hoje a conversa usa o seu) | R | ⏸ | número pareado |
| H6 | Backup fora da VPS (G17): `backup.pub` e primeiro pacote | R | ⏸ | pacote baixado e hash conferido |
| H7 | 7 dias de Hermes estável + backup exportado → `--dry-run` | R+C | ⛔ depende de E4 e H5 | sem queda em 7 dias |
| H8 | Desligar o OpenClaw (Task 15; o gateway já está parado e desabilitado desde 16/10 00:12) e arquivar o `gabi-fin`. **Não antes de `escuta.modo='ativo'`** | R+C | ⛔ | units removidas, restauração testada |

### 7. Fechamento
| # | Item | Dono | Status |
|---|---|---|---|
| F1 | Tag `v1.0-gabi-brain` (depois de D6, C4 e G20) | C | ⛔ |
| F2 | Encerramento e memória (Task 16 do fechamento) | C | ⛔ |

## Depois (não bloqueia a v1.0)
- Microsoft Graph (G11): DECISÃO 16/10 do Ricardo: NÃO mexer na conta ionic (Microsoft). Só quando a ness migrar para o MS: ler agenda/e-mail da ness e mandar e-mail para a lixeira (Itens Excluídos, recuperável; nunca apagar de vez, mesmas travas do Gmail).
- Marcação de agenda com anuência (exceção controlada à R2) e Teams.
- Tela Entregas (Linear, `LINEAR_API_KEY`) e Tailscale da família (G13, ACL, convites).
- Obsidian por pessoa (T4.6 está codificado; uso real fica para depois).
- Ideias do Vercel Eve, só como prática: evals de mensagem (resumo, fechamento, avisos), manifesto único por capacidade, retomada por passo nos jobs com modelo, aprovação explícita por ferramenta de escrita. Não reestruturar o brain nesse modelo.
- Fase 3 (Trabalho): Entregas segue "ainda não construída". Contatos (16/10) feita; ficou de fora: tarefa/frente por pessoa (`tarefa` e `item_frente` não têm vínculo com pessoa), reunião da agenda nova por participante (guarda só `participantes_qtd`, ADR-017), e "respondido" por conversa (o brain só sabe o endereço, `email_respondido`).

## Obsoleto (não fazer)
- **G16** reconectar XP Investimentos: a conexão saiu do mcp.ai em 11/10. Issue `docs/issues/0001` vale só para o C6.
- Qualquer "plano B" no OpenClaw; trabalho novo no `gabi-fin`, `gabi-app`, `gabi-fluxos-*`, `gabi-contas-cartoes`, `gabi-guarda-sessoes`.

## Achados de 16/10 (origem dos itens D2, D3, H1, H2, A6, A7)
- Saldos horários com 4–17 contas lidas: provedor devolve lista parcial e o código grava o que vem.
- Hermes sem idioma definido (mensagens fixas em inglês) e STT fixado em `en`.
- Resumo da manhã era texto corrido; passou a blocos.
- Conta 10 liberada (`sim`) e parada desde 12/08 ainda conta como fonte ativa.

## Como manter
Ao fechar um item: troque o status por ✅ com a data e a evidência (comando, número, commit). Item novo entra no bloco certo, com dono. Não duplique pendência em `STATUS.md`: lá fica só o histórico.
