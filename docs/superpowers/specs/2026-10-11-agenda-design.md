# Agenda no gabi.brain (somente leitura) — design

Data: 11/10/2026 · Estado: **rascunho para revisão do Ricardo** · Reabre **só a agenda** da Fase 3 (Trabalho). E-mail, tarefas e Teams seguem como estão.

## 1. Intenção (o que o Ricardo pediu)
- A agenda do Google do Ricardo passa a viver no **gabi.brain**, que é a fonte única (PLANO-DEFINITIVO). O Hermes só conversa: pergunta ao brain "o que tenho amanhã?" e recebe a resposta do brain.
- **Somente leitura.** Nunca cria, move, aceita nem apaga evento (R2).
- Primeiro o Google pessoal (`resper@gmail.com`, OAuth). A agenda da ness muda para a Microsoft: entra depois, por Graph, quando o G11 existir; o desenho já deixa o lugar.
- Sucesso: "o que tenho hoje/amanhã?" certo no Telegram e no WhatsApp; o resumo da manhã cita os compromissos no horário de Brasília; compromisso cancelado some; nada de agenda é enviado a terceiros.

## 2. Estado atual (verificado no código, 11/10)
- Tabela `evento` (migração 0011) existe, presa a `caixa_email` (e-mail e agenda compartilham a mesma "caixa"); `gabi/trabalho/agenda.py` ingere eventos; o timer `gabi-brain-trabalho` **já roda** a cada 15 min (06–22h BRT), mas nada lê porque não há credencial nem caixa em `sim`.
- Defeitos que impedem uso real: o sincronismo descarta o `syncToken` (toda rodada refaz a primeira página, sem janela, sem paginação); cancelado nunca é apagado; 410 (token expirado) derruba a rodada; `inicio`/`fim` guardam texto cru (`dateTime` com offset ou `date`), e `date()`, `[11:16]` e a comparação de conflitos dependem do formato (evento das 21–24h BRT cai no dia errado; dia inteiro dá horário vazio); sem tratamento de privacidade (título e e-mail dos participantes entram crus); `resumo_manha` leva o título ao Telegram.
- A rodada do trabalho chama o Google **direto** pela rede do próprio job, com o segredo no usuário dono do banco; o padrão adotado depois (contatos, escuta) é a **ponte** com o segredo só no serviço de fontes.
- Variáveis de OAuth divergem: `GOOGLE_OAUTH_CLIENT_*` (trabalho) e `GOOGLE_CLIENT_*` (contatos).
- Nada foi testado contra uma conta Google real.

## 3. Decisões de desenho
1. **A agenda ganha fonte e tabelas próprias**, separadas do e-mail. Liberar o Gmail pessoal na `caixa_email` ligaria também leitura de e-mail e tarefas; não é o que se quer. Novas tabelas: `agenda_fonte` e `agenda_evento`. O módulo e o timer do trabalho ficam como estão (e-mail segue congelado); `evento` fica legada.
2. **Pela ponte**, como contatos e escuta: fonte `google_agenda` no serviço de fontes com `listar_calendarios(conta)` e `listar_eventos(conta, calendario_id, sync_token, janela)`. O brain não tem rede nem segredo.
3. **Um token por conta, com os dois escopos** (`contacts.readonly` e `calendar.readonly`): o Ricardo refaz o consentimento uma vez e o mesmo refresh token serve a contatos e agenda. Variáveis canônicas: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_<CONTA>` em `/etc/gabi/google-contatos.env` (o nome do arquivo passa a ser `google.env` com compatibilidade para o antigo). O `TokenOAuth` de contatos é generalizado (escopo por fonte).
4. **Tempo sem ambiguidade:** cada evento guarda `inicio_utc` e `fim_utc` (instantes), `dia_local` (data em America/Sao_Paulo calculada na gravação) e `dia_inteiro` (booleano; `fim` exclusivo do Google tratado como último dia = fim−1). Nenhuma consulta nem tela fatia texto: tudo converte de UTC para o fuso `parametro agenda.fuso` (default America/Sao_Paulo).
5. **Sincronização correta:** carga inicial com janela (`agenda.janela_passado_dias` 7, `agenda.janela_futuro_dias` 90), `singleEvents=true`, todas as páginas, `syncToken` persistido por fonte (o Google não aceita `timeMin/timeMax` junto com `syncToken`: a janela vale na carga e nas recargas); **410** → recarga completa da janela; recarga completa semanal para a janela deslizar; evento `cancelled` **apaga** a linha.
6. **Privacidade por padrão:** não guardar e-mail de participantes (só a contagem); não guardar local; evento com `visibility` privado/confidencial entra como "Compromisso privado" (parâmetro `agenda.mostrar_privados`, default desligado); título nunca vai a log, aviso ou decisão; o título só sai por canal do dono (resumo da manhã, `agenda_listar`, painel).
7. **Fontes pelo painel, sem código:** em Cadastros, aba Agenda: contas, calendários (a lista vem de `listar_calendarios`), liberar/desligar. Padrão: calendário `primary` da conta; outros calendários só se o Ricardo marcar.
8. **Falhas por conta:** resultado por fonte (uma conta fora não derruba a outra); credencial recusada vira aviso `agenda_reconectar` que fecha sozinho quando volta; cancelado/erro de página não grava lista parcial.
9. **Provedores:** `agenda_fonte.provedor` é `google` ou `graph`. Só `google` é construído agora; o contrato `listar_eventos(...) -> (eventos, novo_token)` é o mesmo para o Graph (delta) quando o G11 existir. A ness entra como uma fonte `graph`, sem mudar telas nem tabelas.

## 4. Arquitetura
```
Google Calendar ◄─ bridge (gabi-brain-fontes: OAuth, rede) ◄─ timer gabi-brain-agenda (15 min, 06–22 BRT)
                                                              │ por fonte: listar_eventos → upsert/delete em agenda_evento (UTC + dia_local)
                                                              ▼
 gabi.db: agenda_fonte, agenda_evento ─► hoje / resumo_manha / agenda_listar (MCP) / painel Agenda / conflitos
```
- **Tabelas (migração nova, próxima livre na execução):** `agenda_fonte(id, conta, provedor, calendario_id, nome, estado ('a_decidir'|'sim'|'nao'), sync_token, sincronizada_em, recarga_em, ultimo_erro)`; `agenda_evento(id, fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_inteiro, titulo, link_reuniao, participantes_qtd, status, etag, atualizado_origem, privado)` com `unique(fonte_id, externo_id)` e índices em `(dia_local)` e `(inicio_utc)`.
- **Superfícies:** `hoje` e `resumo_manha` passam a ler `agenda_evento` (horário local, "dia inteiro" para eventos de dia inteiro); nova ferramenta MCP `agenda_listar(de, ate)` (escopo `trabalho`, só o dono); rota `/api/v1/agenda` e tela Agenda passam a mostrar horário local, dia inteiro e privados mascarados; conflitos calculados sobre instantes (dia inteiro não conflita com horário).
- **Cruzamento com dinheiro:** o resumo da manhã continua um texto só (compromissos + vencimentos), sem inventar aviso novo agora.
- **Hermes:** nenhum acesso próprio à agenda: usa `agenda_listar` e `resumo_manha`.

## 5. Erros, segurança e custo
- Sem token/segredo no brain; nada de segredo em log; erros tipados na ponte, sem corpo de resposta; sem texto de evento em log, aviso ou decisão.
- Só leitura: o escopo é `calendar.readonly`; o cliente não tem método de escrita (teste de varredura).
- Nenhuma IA nesta fatia (sem modelo, sem custo).
- Paginação com teto de páginas por rodada; recarga completa limitada à janela; timeout por fonte.

## 6. Testes e aceite
- Cliente do Google: paginação, `syncToken`, 410, cancelados, dia inteiro, `visibility`, janela, erro tipado sem segredo (servidor falso). Tempo: conversão de offset e de dia inteiro, evento 21–24h BRT no dia certo, virada de dia, DST ausente no Brasil mas fuso configurável, recorrência expandida dentro da janela.
- Sincronização: upsert, apagar cancelado, 410 → recarga, recarga semanal, lista parcial nunca gravada, resultado por fonte.
- Superfícies: `hoje`, `resumo_manha`, `agenda_listar`, rota e painel com dia inteiro/privado/horário local; contrato do painel.
- Privacidade: participantes não são gravados; privado mascarado; varredura de log.
- Aceite com dado real: depois do consentimento, conferir a semana inteira do Ricardo contra o app do Google; eventos de dia inteiro, de 22h e cancelados; resumo da manhã em horário correto.

## 7. Pendências do Ricardo (não bloqueiam o código)
Refazer o consentimento OAuth do `resper@gmail.com` incluindo `calendar.readonly` (além de `contacts.readonly`) e colocar o novo refresh token em `/etc/gabi/google.env` · decidir na aba Agenda quais calendários ler · confirmar a política de privados · G11 (Microsoft da ness) só quando for ligar a ness.

## 8. Fora de escopo
Escrever na agenda, responder convite, e-mail, tarefas, Teams, notificações de "evento em 30 minutos" (fica para depois, junto com o desenho de avisos), Graph/ness (depende do G11).
