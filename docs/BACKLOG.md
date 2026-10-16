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
| D1 | Conta 10 (XP Investimentos, cartão) para estado `nao` em Cadastros › Contas. A XP Investimentos saiu do mcp.ai em 11/10 (Bradesco entrou). Só ela; XP Banking (13–15) é outra conexão | R | ⛔ aguarda o Ricardo | conta 10 fora da conferência e dos avisos; histórico (181 lançamentos) preservado |
| D2 | Descobrir por que a rodada de extratos segue `conferida=0` (último conferido 13/10). **Causa achada 16/10:** não é conta morta nem captura (falhas=[]). Reprovam só `saldo_final` e `volume_proximo` de duas contas: **C6 BANK (12)** (saldo 14/10→16/10 sobe R$ 8.314 com 0 lançamentos na janela; ontem 0 lançamentos; 12 já está `sim`) e **Itaú (6)** (volume; saldo_final −R$ 800 em 16/10); em 14/10 também a conta 2. Heurística `saldo_final` é risco conhecido (sem saldo inicial). Decidir: liberar/excluir a 12 (D4) e/ou tolerar `saldo_final` em conta que ainda não entrou no caixa único | C+R | 🔧 causa achada | causa registrada aqui; ajuste de código ou ação do Ricardo definidos |
| D3 | ✅ 16/10 instalado (retry de 3 tentativas, aviso `incompleta`). **Saldos parciais:** `openfinance_list_accounts` devolve 4–17 das 17 contas, conforme a hora (15/10). Repetir a chamada quando vier menos do que o esperado e marcar a rodada incompleta | C | 🔧 aprovado em 16/10 | toda rodada horária lê as contas esperadas ou registra o que faltou; teste cobre os dois casos |
| D4 | ✅ 16/10 (decisão do Ricardo: todos os bancos entram no caixa único). C6 BANK (12) já estava `sim`; Bradesco 16–18 passaram de `a_decidir` para `sim` (backup `/var/backups/gabi-brain/antes-do-bradesco-*.sqlite`). Saldo do caixa único R$ 37.275,08 inclui Bradesco | R | ✅ | contas decididas em Cadastros |
| D5 | 145 lançamentos sem dono (Cadastros), depois `sudo ~/aplicar-donos.sh` | R | ⏸ | classificação ≥ 90 % |
| D6 | Aceite T1.14: 7 rodadas seguidas `conferida=1` e `python -m tools.aceite` | R+C | ⛔ depende de D1–D2 | `docs/aceite-fase-1.md` escrito |
| D7 | Corte G21: 7 dias de `tools.comparar_agenda` vazio (rodadas 07h, 15h, 23h BRT), depois `python -m tools.congelar --confirm`. Paineiras e Cristina Yabe: vale o brain | R+C | ⛔ depende de D6 | gabi-financeiro congelado |
| D8 | **Porte do reembolso de saúde** (`reembolso_fila.py` e `reembolso_segunda`) para o brain. Sem ele `gabi-reembolso.path` e `gabi-reembolso-segunda` não podem sair. Decidir de onde vêm as pistas do WhatsApp depois que o agente `escuta` sair | C | ⏸ sem spec | spec e plano próprios |
| D9 | Cancelar BrandYourself (renovou em 16/09) | R | ⏸ | cancelado |

### 1b. Agenda financeira, "a receber" e perfil de normalidade (novo em 16/10)
Relatório e contexto: `docs/RELATORIO-2026-10-16.md`.
| # | Item | Dono | Status | Pronto quando |
|---|---|---|---|---|
| AF1 | ✅ 16/10 instalada (commit 5cef4b5; verificada com dado real em leitura). Agenda financeira **B**: diária (atrasadas, hoje, 3 dias, previsão com o saldo) dentro do bloco Financeiro do resumo; segunda: 30 dias por semana. Módulo `gabi/dinheiro/agenda_financeira.py` + ferramenta MCP `agenda_financeira` | C | 🔧 aprovada 16/10 | testes de falta de saldo, estimado `~`, débito automático, dia vazio, saldo velho |
| AF2 | ✅ 16/10: `resumo-semanal-pagamentos` pausado (`hermes cron resume d70bee6dc6db` desfaz) e `forecast-semanal` (segunda 08:00) chama `agenda_financeira` (semanal) | C | ✅ | job pausado e prompt trocado |
| AF3 | Cron `no_agent` do Hermes para a diária e a semanal (sem modelo); verificar se o script alcança o MCP com o token | C | ⏸ | mensagem idêntica sem chamada de LLM |
| PF1 | **Perfil de 5 meses** (`gabi/dinheiro/perfil.py`): média, regularidade, dia típico, classe regular/semi/irregular por pagador e favorecido, separando camadas por faixa de valor e conta | C | ⏸ direção do Ricardo 16/10 | IONIC, FGV e Barra do Pará saem "regular"; NESS e Bekaa separadas em camadas |
| AR1 | **A receber** aprendido do perfil + detecção de atraso (em dado real, a partir de 16/10 só a X2 Intermediações fica atrasada, R$ 10.208, dia limite 15; nenhum falso alarme nas demais 9 séries) (primeiro caso: contrato ORM família Reis, ~R$ 10.208 no C6; pagador a confirmar, candidato X2 Intermediações) | R+C | ⏸ | atraso vira linha na mensagem das 07:05 |
| AR2 | **Cobrança com anuência**: só rascunho no chat (opção A); envio por e-mail com aprovação exige ADR novo (exceção à R2) | C | ⏸ | rascunho sai; Ricardo envia |
| AR3 | Sugerir compromissos a partir de eventos da agenda ("Pagar…", "Adiantamento Sirlene" dia 20, "Contabilidade Holding" dia 15) | C | ⏸ | sugestão aprovada vira compromisso |
| AR4 | Cadastrar já, com valores e formas: Adiantamento Sirlene e Contabilidade Holding | R | ⏸ | aparecem na agenda financeira |
| AF4 | Entradas recorrentes na previsão: usar `analise.recorrentes` (entradas) como segundo cenário na agenda financeira ("só o contratado" × "com recorrentes esperadas") | C | ⏸ | dois cenários lado a lado na mensagem da segunda |
| AR5 | ✅ instalado 16/10 (commit fcd03ca; `gabi/dinheiro/esperados.py`, 11 testes; suíte completa 2116 verdes). **Alerta "esperado e não veio":** recorrente de entrada com dia típico passado e `ja_ocorreu_este_mes=False` vira aviso e linha na mensagem | C | ⏸ | IONIC/FGV/NESS/Bekaa monitorados; teste com banco fixo |
| AR6 | ✅ código 16/10. Aceitar contrato novo com 2 meses consecutivos (confiança menor, rótulo "novo") | C | ⏸ | X2/ORM detectado |
| AR7 | ✅ código 16/10 (razão 1,3 entre valores vizinhos; NESS 16k × 26k separadas em dado real; a camada do Itaú ainda se mistura com Pix avulsos e não alerta). Separar camadas por faixa de valor e dia (NESS 16k × 26k no C6) | C | ⏸ | cada camada sai como série própria; teste golden |
| AR8 | Desvio do normal: valor fora de ±2 desvios, atraso além do espalhamento; estender "cobrada depois de cancelar" a todo recorrente | C | ⏸ | aviso `fora_do_normal` |
| MC1 | ✅ 16/10 (a6cbeaa + correção): `financeiro_recorrentes`, `financeiro_previsao`, `financeiro_vazamentos`, `financeiro_rumo` (assinaturas saem dentro de vazamentos). **Falta o passo do dono:** incluir as quatro no `tools.include` do Hermes, reiniciar `hermes-gateway` e o MCP (runbook#analise-hermes). Ferramentas MCP de análise leem só contas liberadas (`FonteAnalise(so_liberadas=True)`); o painel ainda usa o padrão antigo | C | ⏸ | listadas, escopo `fin`, testes de "nenhuma destrutiva" |
| FU2 | Menores da revisão de 16/10: `_fora_do_normal` sem proteção contra exceção (derruba a diária); `financeiro_previsao` sem saldo devolve `saldo_inicial` 0 sem sinal; ferramentas usam `agora.date()` sem `astimezone(BRT)` e `desvio` cai em `date.today()` (ver FU1) | C | ⏸ | cada um com teste |
| DC1 | ✅ código 16/10. **Canal de decisão** (Telegram/WhatsApp): migração 0028 (`pergunta`), `gabi/decisoes.py`, ferramentas MCP `decisoes_abertas` e `decisao_responder` (escopo novo `decisoes`), rotas `/api/v1/decisoes/perguntas`, skill sugerida em `docs/fontes/hermes-skill-decisoes.md`. **Falta:** instalar, emitir token com o escopo `decisoes`, incluir as 2 ferramentas e a skill no Hermes (runbook#decisoes); depois transformar as pendências do Ricardo (conta 10, ORM Reis, NESS) em perguntas | C+R | 🔧 | pergunta criada e respondida pelo WhatsApp com a decisão gravada |
| EV1 | Snapshot pré-calculado do resumo e da agenda financeira (ferramenta responde sem consultar o banco) | C | ⏸ | latência medida |
| EV2 | Checkpoint por conta e leitura concorrente nas rodadas de captura (retomável após queda) | C | ⏸ | rodada interrompida retoma sem refazer contas prontas |
| EV3 | Evals de mensagens e perguntas antes de instalar (resumo, agenda financeira, cobrança, classificação) | C | ⏸ | suíte de evals no `pytest` |
| EV4 | Subagentes por capacidade com ferramentas mínimas (financeiro leitura, cobrança, agenda/e-mail) | R+C | ⏸ junto do H0 | listas por canal testadas |
| EV5 | Painel de qualidade: taxa de aceite das sugestões, custo por tarefa, latência | C | ⏸ | tela no painel |
| FU1 | Auditar `agora.date()` e o relógio do servidor (CEST) nos timers; "hoje" sempre Brasília | C | ⏸ | testes com `agora` perto da meia-noite |
| CP1 | ✅ código (opção **B** decidida pelo Ricardo em 16/10): só anexo encaminhado à **caixa de comprovantes** (um grupo de WhatsApp aprovado) vai ao Paperless com a etiqueta `gabi:comprovante`, sem modelo; conversa pessoal nunca vira comprovante; palavra de risco vence. Migração 0027, `POST /api/v1/escuta/grupos/{id}/comprovantes`. **Passo do dono:** criar o grupo (só com ele), esperar a escuta vê-lo, aprovar e marcar como caixa de comprovantes (API; falta botão no painel), depois instalar. Não decidido: se a escuta lê o que ele mesmo envia (o ouvinte só recebe) | R+C | ⏸ instalar e ligar o grupo | C1 do bloco 2 destravado |
| H0 | Revisão de segurança do Hermes: `platform_toolsets` sem `terminal`/`write_file`/`execute_code` nos canais; `skills.write_approval` e `memory.write_approval`; terminal em Docker | R+C | ⏸ não aprovado | aprovação do Ricardo e teste |

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
| A3 | Decidir calendários extras (feriados) | R | ⏸ | decidido |
| A4 | ✅ 16/10 instalado (suíte 2149 verdes). Minors de maior risco: exceção qualquer não derruba as outras fontes e janela corrompida usa o padrão (agenda M3); recarga vazia não apaga a fonte (M4); 400 não é credencial e 403 só avisa na 2ª falha seguida (M1); mensagem veneno 4xx é pulada (e-mail M7); `_mover` só aceita trash/untrash (e-mail M1); restaurar e descobrir fora do laço da API (e-mail M2, agenda M9, 404 antes de 503). Resta: veneno 5xx persistente ainda trava a conta (pular perderia mensagem) | C | ✅ | cada um com teste |
| A5 | Demais minors dos dois ledgers (`docs/superpowers/ledgers/2026-10-11-{agenda,email}.md`) | C | ⏸ | triados: fazer, descartar ou virar Depois |
| A6 | `email_sem_modelo` ("teto de custo do modelo") aparece todo dia às 09:45: o teto de custo é global e escuta e correio dividem. Decidir o teto | R+C | ❓ | aviso some ou o teto é separado |
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
| S2 | `/etc/gabi/saude.key` (sem ela a tela Família responde 503) e a lista de PDFs de exames como aceite | R | ⏸ |

### 6. Canal (Hermes) e corte do OpenClaw
| # | Item | Dono | Status | Pronto quando |
|---|---|---|---|---|
| H1 | Idioma pt no Hermes (`display.language`, `stt.language`) | C | ✅ 16/10 | confirmar nos logs que o WhatsApp reconectou |
| H2 | Resumo da manhã em blocos Financeiro (agenda financeira de 3 dias) / Agenda / E-mail | C | ✅ instalado 16/10 | conferir a mensagem das 07:05 |
| H3 | Fechamento noturno (21:00 BRT) e outros jobs do Hermes no mesmo formato | C | ⏸ | prompts revisados |
| H4 | `gabi-vigia` vigiar o `hermes-gateway` (plano definitivo) | C | ❓ | verificado |
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
- Ação "Dispensar" no e-mail (precisa de coluna nova); lixeira "lixo sugerido" visível antes de ligar.
- Ideias do Vercel Eve, só como prática: evals de mensagem (resumo, fechamento, avisos), manifesto único por capacidade, retomada por passo nos jobs com modelo, aprovação explícita por ferramenta de escrita. Não reestruturar o brain nesse modelo.
- Fase 3 (Trabalho): contatos e Entregas seguem "ainda não construída".

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
