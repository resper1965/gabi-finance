# gabi.brain · STATUS (retomada rápida)

> **Direção definitiva (10–11/10/2026): só Hermes + gabi.brain. Ver `docs/PLANO-DEFINITIVO.md`.** Nada novo no OpenClaw nem no gabi-fin.
Atualizado: 10/10/2026. Se a máquina caiu, leia só este arquivo e `.superpowers/sdd/progress.md`.

## Onde estamos
- **Código da Fase 1 pronto, commitado e instalado na VPS** (641 testes: `.venv/bin/pytest -q`). Api, mcp, backup e timers de captura ativos.
- Repos: `/home/ricardo/gabi-brain` (app), `/home/ricardo/gabi-brain-migracao` (export/staging/congelar). Docs: `/home/ricardo/handoff/docs/superpowers/{specs,plans}/` (plano mestre com R1–R17, G1–G14).
- Painel: `painel/` (React). `npm run build` → `gabi/painel/`. Ver sem dado real: `python -m tools.demo 8099` (+ `python -m tools.capturas`, ver `docs/runbook.md#telas-dinheiro`).
- Cuidado: `pkill -f` mata o próprio shell; use PID guardado.

## Esperando o Ricardo (nesta ordem)
1. **G2** aprovar `gabi-brain-migracao/staging/RELATORIO.md`.
2. ~~**G1**~~ **FEITO 09/10/2026** (pacote gpg gerado, baixado e hash conferido, snapshot Contabo). Referência: `sudo bash gabi-brain-migracao/tools/exportar.sh` → scp para a máquina local → conferir hash → snapshot Contabo. Backup na VPS: `/var/backups/gabi-brain-migracao/2026-10-08/`.
3. **G14** aprovar capturas `docs/design/*-{prototipo,app}-*.png`, tela a tela.
4. **G3** login Tailscale (`boss`) + `tailscale serve`; ordem "congelar" dos timers do gabi-fin.
5. **G4** `MCPAI_KEY` em `/etc/gabi/brain.env` → ligar timers de captura. **G5** escolher contas do caixa único.
Depois: instalar (`deploy/instalar.sh`), importar staging, T1.14 (aceite com dados reais).

## Regras que não mudam
Não mexer em segredos (o Ricardo coloca). Nada no claude.ai. Dados nunca chumbados. Só desenvolver/validar com dado real fase a fase.
**Hermes+OpenRouter e desinstalar OpenClaw: SÓ depois de o gabi.brain inteiro terminar.**

## Pendências conhecidas (minors)
Ver `.superpowers/sdd/progress.md` (faixa sem "rodada das 07h", sino sem contador, custo em US$, Fase 2 em diante não iniciada).

## Progresso 09/10/2026
- G2 aprovado. Instalado (`deploy/instalar.sh`): api+mcp+backup ativos. Staging importado no banco real (/var/lib/gabi-brain/gabi.db): 6 pessoas, 50 compromissos, 88 faturas, 7.438 memórias. Cópia temporária do staging removida.
- Próximo: G3 `sudo tailscale serve --bg --https=443 unix:/run/gabi-brain/api.sock`, cadastrar login do Ricardo como boss, ver painel real; depois G14, G4, G5.
- 09/10 01:05 G3 feito (https://gabi.tail985643.ts.net, login resper@bekaa.eu = boss). G4 feito (MCPAI_KEY em /etc/gabi/brain.env). Captura de saldos de teste OK: 9 contas (Santander e Itaú; **C6 PJ não apareceu**), todas a_decidir; demora ~3,5 min.
- Próximo: G5 (escolher contas no painel > Cadastros), investigar ausência do C6 PJ, ligar timers (`sudo systemctl enable --now gabi-brain-saldos.timer gabi-brain-extratos.timer`), G14.
- 09/10 01:10 timers de captura LIGADOS (saldos horário, extratos 06h/14h BRT (adiantados em 09/10: dados prontos antes do briefing das 07:30)). Unit saldos: TimeoutStartSec 300→900 no repo; aplicar com `sudo bash deploy/instalar.sh --confirmo-backup-exportado`.

## Progresso 09/10/2026 (tarde)
- **Bug: botão "Entra no caixa único" recusado ("outra origem")** — atrás do `tailscale serve` o `Host` não é o nome público, e o guarda de CSRF barrava toda escrita do painel. Correção: `GABI_ORIGENS_CONFIAVEIS` (unit da api, `https://gabi.tail985643.ts.net`); o resto segue barrado. Confirmado funcionando pelo Ricardo.
- **`deploy/instalar.sh` agora reinicia api e mcp.** Antes, `enable --now` não reiniciava serviço ativo: o código novo ficava no disco e o processo seguia com o antigo (perdemos tempo com isso). Conferir sempre: `systemctl show gabi-brain-api -p ActiveEnterTimestamp`. `systemctl show -p Environment` mostra a unit, não o processo.
- **Faturas de cartão:** fatura `PAST_DUE_UNCONFIRMED` com débito de mesmo valor em conta BANK (de vencimento−7d até hoje) não conta em "faturas abertas" (`contas_pagar.faturas_abertas`). `OPEN` e `PAST_DUE_UNPAID` seguem abertas até o banco dizer `PAID`. A tela Cartões (`rotas/gastos.py`) usa a mesma regra (alinhada depois).
- **Contas capturadas (15):** Santander (BANK 2; CREDIT 1, 3, 4), Itaú (BANK 6; CREDIT 5, 7, 8, 9), XP Investimentos (CREDIT 10), C6 Bank Empresas (CREDIT 11, **BANK 12**: o C6 PJ apareceu), XP Banking (BANK 14, 15; CREDIT 13). Cartões 1/3/5/7 são distintos (vencimentos e totais diferentes), não há duplicata entre contas.
- **G5 em andamento:** só a conta 1 (Santander CREDIT) está liberada (`sim`); as outras 14 seguem `a_decidir`. Cartão só entra em "faturas abertas", nunca no saldo; para saldo, liberar as contas BANK (em especial a 12).
- Próximo: Ricardo libera as contas BANK em Cadastros; G14 (capturas); T1.14 (aceite com dados reais).
- **Faixa "sem dados conferidos ainda / open-finance parou" (diagnóstico):** a rodada de extratos das 07h BRT terminou `ok` mas `conferida=0`; 5 conferências falharam (contas 5, 6, 7, 12: `dias_sem_buraco`; conta 6: `saldo_final` com −R$ 4.016,63 = débito da fatura do cartão 7, ainda sem lançamento no extrato). Uma falha em qualquer conta bloqueava o `dados_ate`. **Correção:** só conferências de contas liberadas (`sim`) travam a rodada (as demais seguem registradas); `dias_sem_buraco` não vale para cartão. Sem conta liberada, nada é conferido. `saldo_final` inalterado.
- **Open Finance (log do extratos 12:10):** C6 Bank Empresas "não atualizou em 5 min" (última 06:40 UTC) e **XP Investimentos parado desde 12/08** (conexão/consentimento no provedor: ação do Ricardo, não do código). Reconectar/aguardar a rodada das 15h antes de liberar a conta 12 (C6 BANK).
- Atenção: a regra de fatura paga (débito BANK de mesmo valor) só reconhece quando o *lançamento* chega; enquanto o banco não publica, a fatura segue aberta.

## Progresso 09/10/2026 (noite)
- **G14 APROVADO pelo Ricardo em 09/10/2026** (galeria `docs/design/GALERIA.md`, 9 telas × claro/escuro/celular, protótipo × app). Plano de execução: `docs/superpowers/plans/2026-10-09-gabi-brain-execucao-restante.md` (F1.A–G feitas; F1.I = aceite T1.14 em contagem).
- Rodadas de extratos agora 06h e 14h BRT. Conferência calibrada (ADR-009). Sino/menu com contadores, rodadas em A pagar, categoria editável na sugestão, filtro só assinatura. Custo da Gabi segue em US$ (decisão do Ricardo).
- Pendente do Ricardo: reconectar C6 e XP Investimentos no mcp.ai (issue 0001).

## Progresso 09/10/2026 (fim do dia): Fase 2 (Cobrar) — código pronto e instalado
- **Instalado** (migração 0009 aplicada; api+mcp reiniciados 16:15): T2.1 cliente Paperless + extrator; T2.2 vínculo de comprovantes (proposto/confirmado); T2.3 cliente Nibo SÓ LEITURA; T2.4 lote do Nibo (única gravação externa, confirmação textual, idempotente por `reference`); T2.5 reembolsos de contratantes; T2.6 rascunho de cobrança (envio desabilitado, ADR-006); T2.7 pedidos do canal; T2.8 MCP (16 ferramentas: propostas, pedidos, documentos, dado sensível com liberação única); T2.9 API `/api/v1/cobrar/*` e telas Cobrar + Pedidos. 777 testes pytest + 42 vitest.
- **Migração 0009 está congelada** (em produção): esquema novo vai em 0010+.
- **Falta para ACEITAR a Fase 2 (T2.10), tudo com dado real e gates do Ricardo:** G7 (token admin do Paperless → `Paperless.preparar_usuario`), G8 (`NIBO_TOKEN`; conferir rotas /partners, /customers, /categories e formato `items`), cadastros que ainda não têm tela: `empresa.relacao` (contratante | pj_titular), `empresa.dados.email_cobranca`, `categoria.nibo_category_id`, `parametro nibo_socio_id`, `pessoa.canais/pode_pedir`; ingestão dos comprovantes do Paperless (`registrar_comprovante`) ainda NÃO escrita (precisa ver documentos reais); aba "Notas a receber" (NFS-e) sem backend; G14 da Fase 2 (capturas das telas novas). Aceite: ≥ 80% dos itens com comprovante casado; lote do Nibo 2× sem duplicar; pedido real pelo canal aparece em Pedidos.
- Plano de execução e ledger: `docs/superpowers/plans/2026-10-09-gabi-brain-execucao-restante.md`.

## 09/10/2026 (noite): Fase 2 revisada e instalada de novo
- Revisão independente da Fase 2 feita; 10 achados corrigidos com teste (atomicidade, lote do Nibo × Paperless, créditos de reembolso, baixa duplicada, validação de pedidos, liberação sensível, vínculos). Instalado: migração **0010** (remove colunas redundantes; relação da empresa, canais e permissão de pedido ficam no JSON `dados` do cadastro). **0009 e 0010 congeladas**; esquema novo = 0011+.
- **Cadastros agora tem a tela da cobrança:** relação e e-mail das empresas, quem pode pedir (canais), id da categoria no Nibo, sócio do Nibo, liberação de dado sensível. Reembolsos tem "Baixar nos itens cobrados" para créditos recebidos na PJ. 801 pytest + 47 vitest.
- **Falta para aceitar a Fase 2 (T2.10), todos com o Ricardo ou dado real:** G7 (token admin do Paperless), G8 (`NIBO_TOKEN` no arquivo de ambiente; conferir rotas `/partners`, `/customers`, `/categories` e o formato `items`), preencher os Cadastros acima, **ingestão dos comprovantes do Paperless** (`registrar_comprovante` ainda sem job, precisa de documentos reais), aba "Notas a receber" (NFS-e, sem backend), G14 da Fase 2 (capturas das telas novas).

## 09/10/2026 (noite): Fase 3 (Trabalho) — código pronto contra servidor falso
- Trilha até o fim em `docs/TRILHA.md` (pista minha x pista do Ricardo).
- **Migração 0011** (caixa_email, item_email, regra_expurgo, evento, tarefa, frente, item_frente). `gabi/trabalho/{email,agenda,tarefas,frentes,hoje}.py`; clientes `gabi/fontes/{graph,google}.py` (só leitura + rascunho + concluir tarefa; sem envio nem exclusão); rotas `/api/v1/{hoje,frentes,agenda,mensagens,tarefas,caixas-email}`; MCP `hoje_resumo`, `frentes_listar`, `frentes_itens` (escopo `trabalho`); telas Hoje, Frentes, Agenda, Mensagens, Tarefas e Cadastros › Caixas de e-mail.
- **Falta para ACEITAR a Fase 3 (T3.7), tudo com o Ricardo ou dado real:** G11 (Entra ID IONIC, certificado + aprovação do admin), G12 (Google: OAuth ness/Gmail, conta de serviço bekaa.eu/esper.ws), cadastrar as 7 caixas em Cadastros e liberar (`sim`), **job de rodada** que chama os clientes com o token do ambiente (não escrito: precisa das credenciais reais para validar), "faixa vermelha com Reconectar" (T3.6, depende do G11/G12), medir Hoje < 1 s no celular real, G14 da Fase 3 (capturas lado a lado das telas novas; `tools.capturas` ainda só cobre a Fase 1).
- Contatos (Mensagens) e Entregas · Linear (Tarefas) seguem "ainda não construída" (Fase 4/Linear).
- **Telas aprovadas pelo Ricardo (09/10 noite, mensagem "telas aprovadas")**: lido como G14 das telas da Fase 2 e da Fase 3 (sem capturas lado a lado geradas; aprovação no painel real).
- **BLOQUEIO DE ARQUITETURA (Fase 2):** a unit da API tem `RestrictAddressFamilies=AF_UNIX` e `IPAddressDeny=any` (testes de deploy exigem), então a API **não alcança o Paperless (127.0.0.1:8000) nem o Nibo (internet)**, e nem o MCP (só localhost, sem EnvironmentFile). Rotas /cobrar que chamam Paperless/Nibo não funcionam como instaladas. Decisão do Ricardo: (a) serviço separado `gabi-brain-fontes` (Paperless+Nibo, com `/etc/gabi/cobrar.env`, rede liberada) que a API chama por socket Unix — recomendado, mantém a API isolada; ou (b) afrouxar a unit da API. Tokens G7/G8 só depois disso; scripts `~/g7-paperless.sh` e `~/g8-nibo.sh` foram removidos até lá.

## 09/10/2026 (noite): aceites e aprovações do Ricardo
- **Ricardo declarou (09/10, "todas as fases e aprovações que demandavam minha aprovação e/ou aceite") aceitas:** Fases 1, 2 e 3 (T1.14, T2.10, T3.7) e todos os G14/aprovações pendentes. Registrado como **aceite por decisão do dono**, sem a evidência de dado real que a trilha previa (7 dias `conferida=1`, ≥80 % de comprovantes casados, 7 caixas com itens).
- **O aceite não destrava o que é técnico.** Seguem sem aceite de dado, por dependerem de credencial/ação externa: reconectar C6/XP (issue 0001), G7/G8 (tokens Paperless/Nibo), G11/G12 (Entra ID, Google), cadastros, job de rodada do Trabalho. Os tokens o Ricardo coloca (regra de segredos).
- **Decisão de arquitetura ainda aberta (Fase 2):** serviço `gabi-brain-fontes` (recomendado) x afrouxar a unit da API. Sem ela, rotas /cobrar que chamam Paperless/Nibo não funcionam.

## 09/10/2026 (noite): bloqueio de rede da Fase 2 RESOLVIDO (opção a)
- **Serviço `gabi-brain-fontes`** (user `gabibrain-fontes`, grupo `gabibrain`, único com rede e tokens, `/etc/gabi/cobrar.env` 0600 root). Ponte Unix `/run/gabi-brain-fontes/fontes.sock` (0660); API e MCP seguem com `IPAddressDeny=any` e usam `GABI_FONTES_SOCKET`. Código: `gabi/fontes/{ponte,servico,ambiente}.py`; lista branca de métodos (sem `preparar_usuario`). 858 testes.
- Provado em produção: sandbox idêntico ao da API alcança o Paperless pela ponte (docs e download de PDF) e não tem rede direta. Backup pré-instalação: `/var/backups/gabi-brain/pre-fontes-2026-10-09.sqlite`.
- Paperless configurado com o token do usuário `resper` (dado pelo Ricardo, que autorizou). Nibo ainda NÃO configurado (G8: acrescentar `NIBO_TOKEN` em `/etc/gabi/cobrar.env` e `sudo systemctl restart gabi-brain-fontes`).
- Próximo: ingestão de comprovantes (job que lê o Paperless pela ponte), cadastros da cobrança, G8.

## 09/10/2026 (noite): decisões
- **Fase 3 (Trabalho) congelada** (ver TRILHA.md). Nada novo é desenvolvido nela até as Fases 1 e 2 estarem em uso diário.
- Rodada de extratos conferida pela 1ª vez (rodada 43): o relógio de 7 dias do T1.14 começou em 09/10. Regra de buraco revista para contas de movimento irregular (ADR-009, item 6).
- NFS-e do Nibo importadas (243 notas, 193 PDF/XML em /var/lib/gabi-brain/notas) e previsão de caixa de entradas (GET /api/v1/cobrar/previsao).
- 26 categorias do Nibo criadas com `nibo_category_id`. Falta a taxonomia pessoal e a equivalência das 82 categorias do banco (próximo item).

## 09/10/2026 (noite, fim do dia): classificação em massa e donos padrão
- **Classificação:** 4.136/4.656 com categoria (equivalência do banco → categorias pessoais, `seeds/categorias-pessoais.csv`). **"Para quem": 4.331/4.656 (93%)**, 325 sem dono (Drogaria São Paulo 22, L'Occitane 8, ~140 lojas de 1 lançamento).
- **Donos padrão** (`seeds/donos-padrao.json`, carregador `tools/semear_donos.py`, aplicar com `sudo ~/aplicar-donos.sh`): quem usa cada cartão/conta, dono por categoria, padrão por compromisso, responsável (Carla→Giovanna, Adriana→Louise; favorecido ≠ para quem), regras por loja (com `empresa` para reembolso: IONIC e NESS; Bekaa), parâmetros (`categorias_assinatura`, `categorias_habito`). Origem `fonte` = padrão do cadastro (uma regra por loja vence; `voce`/`regra` nunca são sobrescritos). Memória do projeto: pets-e-donos-padrao.
- **Pendente de código:** regras com condição (cartão, valor, dia da semana) — proposta aprovada em conversa, ainda não feita; vigia/avisos por Telegram (o brain não envia nada); previsão de saídas (impostos, faturas); gabi-agent (Hermes) ainda sem plano; Fase 3 congelada.
- **Assinaturas:** lista = detector (sem hábito) + categorias de assinatura; BrandYourself marcado para cancelar (renovou em 16/09/2026); 44 a conferir.
- **Reembolsos a cobrar:** NESS 34 itens (R$ 7,9 mil), IONIC 12 (R$ 5,9 mil); falta comprovante p/ lote do Nibo.
- **Aceite T1.14:** rodada conferida desde 09/10; relógio de 7 dias roda até ~16/10 (precisa de 7 rodadas seguidas conferidas; XP Investimentos segue parada, issue 0001).


## Progresso 10/10/2026 (plano de finalização)
Plano: `docs/superpowers/plans/2026-10-10-gabi-brain-finalizacao.md` (execução nativa; ledger em `.superpowers/sdd/2026-10-10-gabi-brain-finalizacao/progress.md`). Suíte: 1018 pytest + 70 vitest verdes.
- Feito: backup corrigido e chave mcp.ai trocada; extratos conferidos; NFS-e da Bekaa importadas; previsão de caixa (aba Previsão, ADR-013) e recebimentos propostos (ADR-012); donos padrão (96% classificados, ADR-010/011); avisos (sino + `OnFailure`); `tools.aceite`; exportação semanal criptografada (`gabi-brain-exportacao.timer`); `tools.comparar_agenda`; dívidas de `gabi/cobrar` (util comum, cobrar só itens selecionados, `tipo_documento(texto, hoje)`).
- Esperando o Ricardo: **G15** exceção R2 para aviso por Telegram; **G16** XP Investimentos parada desde 12/08 (até 17/10); **G17** colocar `/etc/gabi/backup.pub` e puxar o 1º pacote (runbook "Backup fora da VPS"); **G18/G19** comprovantes reais e lote Nibo em conta real; **G20** aceitar a Fase 2 sem "pedido real pelo canal" (adiado ao gabi-agent); **G21** corte do gabi-financeiro após 7 dias de `tools.comparar_agenda` vazio (ler `/var/lib/gabi-fin/compromissos.json` exige permissão); cancelar BrandYourself; 145 lançamentos sem dono.
- Aceite Fase 1 (T1.14): rodar `python -m tools.aceite` quando houver 7 rodadas conferidas seguidas (~16/10) e classificação ≥ 90% (hoje 86,9%).
- Tag `v1.0-gabi-brain` só depois de G20 e dos dois aceites. Fase 3 congelada; Fase 4 por pedido; Hermes/OpenClaw só no plano gabi-agent, depois.

## 10/10/2026 (tarde): instalação final da pista A
- Commit 4494f54 (avisos `exportacao_parada`, projeção sem dupla contagem de fatura, sugestão de regra não reaparece após rejeitada). 1024 pytest + vitest verdes. Instalado (`deploy/instalar.sh --confirmo-backup-exportado`); api, mcp e fontes ativos desde 15:34, 6 timers agendados, nenhuma unit em falha.
- Pista A sem trabalho de código restante: o que falta depende do Ricardo ou do relógio (G16–G21, comprovante Pix real, ~16/10 para o aceite da Fase 1, 145 lançamentos sem dono). Fase 3 segue congelada; Fase 4 por pedido; tag só após G20 e os dois aceites.
- Não verificado em produção nesta data (bloqueado por permissão): `tools.aceite`, `gabi.avisos`, contagem de lançamentos sem dono. Saúde da api: rota `/api/saude` exige login de boss (a rota `/api/v1/saude` não existe).
- Retomada em ~16/10: rodar `python -m tools.aceite`, depois `tools.comparar_agenda`, depois tag.

## 10/10/2026 (fim da tarde): código do módulo — pista A fechada
- **Ingestão de comprovantes Pix** (`gabi/cobrar/ingestao.py`, `gabi-brain-comprovantes.timer` 07h BRT): escrita contra servidor falso; propõe vínculos, nunca confirma; idempotente; etiqueta `gabi:comprovante`.
- **Job do Trabalho** (`python -m gabi.trabalho`, `gabi-brain-trabalho.timer` 15 min, 06h–22h): lê e-mail/agenda/tarefas das caixas `sim`, tokens do ambiente (`gabi/fontes/tokens.py`, `/etc/gabi/trabalho.env`), aviso **"Reconectar a caixa"** no sino (fecha sozinho), conclui na origem a tarefa pedida no painel (migração **0015**: `tarefa.pedido_concluir_em`; a API não tem rede). Esquema novo = 0016+.
- 1046 pytest + 70 vitest verdes; instalado (commit 7adad28); sem credenciais e com todas as caixas `a_decidir` o job não faz nada (rodou, `Result=success`).
- **Não escrito por falta de spec/decisão (não por dado):** regras com condição (cartão/valor/dia: só proposta oral, sem spec), Fase 4 (T4.1–T4.6, cada uma abre com mini-spec aprovado), aviso por Telegram (G15, exceção à R2), Canal/Hermes (depois do gabi.brain).

## 10/10/2026 (noite): Fase 4 codificada (T4.1–T4.6) e regras com condição
- **Regras com condição** (migração 0016): `regra.condicao` JSON (conta, faixa de valor absoluto em centavos, dias da semana); vale no classificador, prévia, aprovação e tela Regras.
- **T4.1/T4.2 saúde e exames:** `gabi/familia/{saude,exames,ambiente}.py`, cofre `saude.enc` AES-256-GCM só em memória (ADR-014), exame só com a pessoa confirmada, log de leitura, rotas `/api/v1/familia/*` por `matriz_acesso` (total/parcial/nenhum), tela Família. **Falta:** `/etc/gabi/saude.key` (você cria; sem ela 503).
- **T4.3:** `GET /api/v1/rumo` (entradas, saídas, poupança, gasto por pessoa/frente, patrimônio); cliente Linear só leitura + tabela `entrega` (0017) + tela Entregas; `LINEAR_API_KEY` em `/etc/gabi/trabalho.env`.
- **T4.4:** `identidade.grau`/`exigir_informacao`; teste de que nenhuma rota do app abre para familiar/terceiro. **Falta (seu):** G13, ACL e convites no Tailscale.
- **T4.5:** `/api/v1/setup` (7 passos, teste na hora, progresso em `setup_passo` 0019) e tela Configuração (ADR-015).
- **T4.6:** `python -m gabi.familia.obsidian --destino X --para p1` (pasta por pessoa, determinística, edição externa vira `edicao_externa` 0018) + rotas de edições.
- Esquema novo = **0020+**. 1143 pytest + 78 vitest verdes; instalado (ae4a763).
- **Sem código restante no módulo, exceto o que depende de decisão:** aviso por Telegram (G15), Canal/Hermes (depois do gabi.brain), Fase 3 segue descongelada só no que foi feito (job + credenciais).

## 10/10/2026 (fim): lado gabi.brain do Canal e Telegram
- **Avisos no Telegram (G15):** `gabi/telegram.py` + `gabi-brain-telegram.timer` (5 min), migração **0020** (`aviso.telegram_em`). DESLIGADO até existir `/etc/gabi/telegram.env` com `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` (a sua exceção à R2). Instalado; sem o arquivo roda e não envia nada.
- **Canal (TC.2–TC.4, só o que é do repositório):** ferramenta MCP `resumo_manha` (≤5 linhas, 1ª linha "⚠ Dados desatualizados" quando for o caso), lista explícita `tools.include` do Hermes testada (`tests/mcp/test_hermes.py`, `python -m tools.gerar_hermes`), `docs/fontes/hermes.md`, ADR-007 (só o Ricardo com escopo completo no canal). Esquema novo = **0021+**.
- **Continua fora do repositório, por ordem sua (08/10):** instalar o Hermes/OpenRouter (TC.1), WhatsApp (TC.5) e desligar o OpenClaw (TC.6, só após 7 dias de Hermes estável e backup exportado).

## Escuta do WhatsApp (11/10/2026): código completo, aguardando os passos do Ricardo
- **Existe (Tasks 1–12, ADR-016):** migração 0021 (`escuta_msg`, `escuta_remetente`, `contato_google`), ingestão do spool, classificação por modelo barato (JSON validado), palavras de risco, destinos (pedido, Paperless, aviso de crise), tela Escuta no painel (aprovação de remetentes e grupos, parâmetros, contatos), contatos do Google (2 contas, pela ponte), ouvinte Node/Baileys só de leitura e o comparador `python -m tools.comparar_escuta`.
- **Instalado mas DESLIGADO:** `gabi-brain-escuta.timer`/`.path`, `gabi-brain-contatos.timer`, `escuta-ouvinte.service`. Padrão `escuta.modo='registro'` (classifica e registra; não cria pedido, não avisa crise, não entrega anexo).
- **Só o Ricardo faz:** parear o ouvinte (QR), G12 (`contacts.readonly` nas duas contas, `/etc/gabi/google-contatos.env`), `openrouter.env` com limite de crédito na chave, aprovar remetentes/grupos na tela, ligar os timers, trocar o modo para `ativo`, aposentar o antigo. Passo a passo em `docs/runbook.md#escuta-paralelo`.
- **Paralelo:** com o agente antigo ainda ativo, rodar o comparador todo dia; gate = N dias seguidos sem divergência (`so_no_brain`, `so_no_agente`, `tipo_diferente` = 0). Antes de `ativo`, limpar os anexos mantidos em registro (runbook). **Em registro a crise é só registrada: NÃO desligar o OpenClaw antes de `ativo`.**
- **Correções da revisão final (11/10, onda única):** o spool não guarda mais texto (json apagado após o commit, sem `lidos/`; `invalidos/` limpo em 24 h; **purgar os `lidos/`/`invalidos/` antigos uma vez**, runbook `#escuta`); passada de risco ANTES do modelo e orçamento de tempo por rodada (`escuta.tempo_max_s`, 420); crise do modelo rápido não vai ao forte; `escuta_atencao` vai primeiro no Telegram e não expira; remetente sem telefone (LID) pelo id cru; celular antigo ganha o 9; grupo visto aparece na tela; pedido sem `pode_pedir` fica retido com aviso `escuta_sem_permissao`; pedidos da escuta com `canal='escuta'` (nunca respondem ao terceiro); falha temporária com até 8 tentativas e espera (migração **0023**, aviso `escuta_falhou`); custo de chamada que falhou gravado (`escuta-falha`); teto de anexo 25 MB nos dois lados (aviso `escuta_anexo_grande`); sem áudio/vídeo nem mídia de grupo; espaço mínimo no ouvinte; anexo apagado após o envio; retidas de não aprovados somem em `escuta.retida_dias` (14) e linhas de grupo/"nada" em `escuta.retencao_dias` (30); `OnFailure` no ouvinte; gatilho no máx. 1/min.
- **Gates da aposentadoria (agente `escuta`, `escuta.py`, `gabi-wa-docs`):** modo `ativo` estável por alguns dias, Hermes no ponto (Task 15 do fechamento) e um aviso de crise de TESTE recebido no Telegram/Hermes (`python -m gabi.escuta --teste-crise`). **`gabi-reembolso.path` e o resto do `gabi-reembolso*` NÃO saem com a escuta:** o porte de `reembolso_fila.py`/`reembolso_segunda` (spec §3.6) não foi feito; item aberto em `docs/PLANO-DEFINITIVO.md`.
- **Limitações conhecidas:** o anexo de um pedido vai ao Paperless (`gabi:entrada-whatsapp`) mas não fica ligado ao pedido (o Paperless devolve o UUID da tarefa; vínculo adiado, não afeta `registro`); remetente que chega só como LID fica pelo id cru (não casa com o telefone da mesma pessoa; a tela não tem campo de nome para aprovar um id cru: use a API com `nome`); o comparador só enxerga o agente antigo pelo NOME do contato; **saúde SÓ DE TEXTO não vai ao cofre** (desvio do spec §3.4, ADR-016): em `ativo` gera `escuta_saude` e o texto é apagado, o original continua no WhatsApp (aceitar isso é gate de `ativo`).
- **Pendências conhecidas sem decisão (M7 da revisão final):** a lista de candidatos (pessoa com canal WhatsApp e sem aprovação) não é mostrada na tela; não há extração de texto de PDF para a classificação (spec §3.3); editar as contas de contatos (`escuta.contas_contatos`) só pelo banco, não pelo painel.
- Anexos da escuta: só lidos de dentro do spool, arquivo regular, teto de 25 MiB (`escuta.anexo_max_mb`; o ouvinte usa o mesmo teto), leitura limitada ao teto. Caminho fora do spool: a mensagem falha e o arquivo fica. Acima do teto: `falhou`, aviso `escuta_anexo_grande` e o arquivo é apagado.

- **Frescor por fonte (11/10):** `envelope()` tratava toda fonte como se precisasse de `conferida=1`, mas só `open-finance` (extratos) tem conferência; notas-nibo, comprovantes e trabalho ficavam `nao_conferida` para sempre e todo `resumo_manha`/painel levava "dados desatualizados" falso. Regra agora (`gabi/envelope.py`, `COM_CONFERENCIA`/`LIMITE_FONTE`): extratos valem pela última rodada conferida (limite 3 dias); as demais, pela última rodada `ok` (notas-nibo e comprovantes 36 h, trabalho 12 h). Última tentativa com erro = `erro`; passou do limite = `parada`; nunca rodou ok = `nao_conferida`. `erro` e `parada` desatualizam (nos extratos, `erro` só desatualiza passado o limite de 3 dias). `trabalho` só entra se houver `caixa_email` (ou `agenda_fonte`) com estado `sim`. `open-finance-saldos`, `backup`, `importacao-staging` e `exportacao` (semanal) não entram.
