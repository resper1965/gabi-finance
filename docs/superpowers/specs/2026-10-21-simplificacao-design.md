# Simplificação do gabi.brain (21/10/2026)

## Por quê
A revisão de 21/10 (uso real no banco de produção) mostrou que cerca de um terço a 40% do código atende funcionalidades que nunca rodaram: 13 tabelas vazias, timers que não produzem nada, 19 das 36 ferramentas do MCP nunca chamadas. O núcleo usado (extratos, regras, a receber, agenda, e-mail, Teams, avisos, painel de decisão, Hermes) fica. Esta rodada corta o que não é usado e troca duas heurísticas que geram ruído por regras simples.

## Decisões do Ricardo (21/10)
1. Cortar: **saúde inteira**, **módulo Trabalho**, **cobrança/reembolso PJ**, **escuta do WhatsApp**, e as **limpezas pequenas**.
2. **"Para quem"**: aplicar sozinho quando for certeiro (flexibiliza R1 só neste ponto, com registro e desfazer).
3. **Conferência de saldo**: vira aviso, não trava o `dados_ate`.

## Regras que valem durante o corte
- **Dado nunca se perde.** Só são removidas tabelas **vazias** (conferidas no banco de produção antes do deploy). Tabela com linha fica no banco, sem código que a use, e é listada como "legada" em `docs/ARQUITETURA.md`.
- **Segredos e cofre intactos**: `/etc/gabi/*.env`, `/etc/gabi/saude.key`, `saude.enc` e o pareamento do WhatsApp não são apagados (o Ricardo decide depois).
- **Nada sai em produção sem o Ricardo autorizar** o `instalar-brain.sh` e os comandos de parada de serviço (listados em "Produção").
- O `git` guarda tudo: qualquer corte volta com `git revert`.

## 1. Escuta do WhatsApp — CORTAR
**Antes de cortar, mover o que outros usam:**
| Hoje em | Vai para | Usado por |
|---|---|---|
| `escuta/contatos.py`, `contatos_propostas.py`, `contatos_gravar.py`, `interacao.py` | `gabi/contatos/` (mesmos nomes; `interacao.py` só se ainda tiver leitor) | timer de contatos, painel de propostas (ADR-020/021/022) |
| `escuta/caixa.normalizar_telefone` | `gabi/contatos/telefone.py` | decisoes, contatos, tools |
| `escuta/classificar.Falha`, `_chamar` | `gabi/correio/modelo.py` | correio |
| `escuta/__main__.ModeloComCusto`, `cliente_da_ponte` | `gabi/correio/modelo.py` | correio |
| rotas `/escuta/contatos/*` (`rotas/escuta.py:245-405`) | `gabi/rotas/contatos.py`, prefixo `/api/v1/contatos` | telas Cadastros e ContatosPropostas |

O `gabi-brain-contatos.service` passa a rodar `-m gabi.contatos.contatos` e `-m gabi.contatos.contatos_gravar`.

**Sai:** `gabi/escuta/` inteiro (processar, caixa, classificar, crise, destinos, remetentes, spool_seguro, `__main__`), o resto de `rotas/escuta.py`, a tela `Escuta.tsx` e a aba "Escuta" de Cadastros, `ouvinte/` (app Node), `tools/comparar_escuta.py`, as units `gabi-brain-escuta.{service,timer,path}` e `escuta-ouvinte.service`, os usuários/grupos/pastas da escuta no `instalar.sh`, os tipos de aviso `escuta_*`, os testes `tests/escuta/` (menos os de contatos, que vão para `tests/contatos/`).
**Tabelas:** `escuta_msg`, `escuta_grupo` (vazias) saem; `escuta_remetente` (9 linhas) fica como legada.

## 2. Saúde — CORTAR
**Sai:** `gabi/familia/` (exames, saude, extrair, marcadores, rodada_exames, ambiente, `__main__`, obsidian), `gabi/reembolso_saude/`, `gabi/visao_pdf.py` se só a saúde o usar, `rotas/familia.py`, `rotas/reembolso_saude.py`, `mcp/ferramentas_reembolso.py`, telas `Familia.tsx`, `FamiliaSaude.tsx`, `Reembolso.tsx` e a área "Família" do menu, `api.py:68-69` (`app.state.saude`, o cofre; a rota `/api/saude` é a saúde do sistema e fica), as units `gabi-brain-exames.*` e `gabi-brain-reembolso-saude.*`, `tools/medir_exames.py`, `tools/gerar_amostras.py` (partes de saúde), testes `tests/familia/`, `tests/reembolso_saude/`, `tests/test_saude_blindagem.py`, `tests/rotas/test_familia.py`, `tests/rotas/test_reembolso_saude.py`.
**Obsidian por pessoa** (`familia/obsidian.py`) sai junto: era decisão aberta ("ligar ou remover") e nunca foi ligada.
**Tabelas:** `exame_doc`, `reembolso_saude_*`, `edicao_externa`, `liberacao_sensivel` (vazias) saem. O cofre `saude.enc` (arquivo fora do banco) e a chave ficam.
**Acesso por pessoa** (`identidade.py`, `acesso.py`, `matriz_acesso`): fica (é usado pelo login), mas o nível "sensível" deixa de ter o que liberar; as rotas de liberação saem.

## 3. Módulo Trabalho — CORTAR (preservando Hoje e Agenda)
As telas **Hoje** e **Agenda** e a configuração de caixas são usadas e moram hoje em `rotas/trabalho.py`. Elas ficam:
- `GET /api/v1/hoje` → `gabi/hoje.py` (junta com o arquivo atual), sem o bloco `emails_importantes` (lia `item_email`, vazia) e sem o filtro por frente.
- `GET /api/v1/agenda` → `rotas/agenda.py`.
- `class Conflito` → `gabi/agenda/consulta.py`.
- `resumo_manha`, `agenda_listar`, `email_listar` (MCP) → `mcp/ferramentas_trab.py` renomeado `mcp/ferramentas_dia.py`, sem depender de `gabi.trabalho`.

**Sai:** `gabi/trabalho/` inteiro (rodada, email, agenda legada, frentes, tarefas, entregas Linear, contatos em aberto, hoje), rotas `/frentes*`, `/mensagens`, `/contatos` (em aberto), `/tarefas*`, `/entregas`, `/caixas-email*`; telas `Frentes`, `Mensagens`, `Contatos`, `Tarefas`, `Entregas`, `CadastrosCaixas`, a área "Frentes" e a área "Tarefas" do menu, a aba "E-mails" de Mensagens; units `gabi-brain-trabalho.*`; `tools/demo.py` (partes do Trabalho); testes correspondentes.
O "bug" de `trabalho/contatos.py:129` (reunião lida de `evento`, vazia) some com o módulo: a agenda nova só guarda a contagem de participantes (ADR-017), então esse sinal não tem como existir; a tela "Prioridades" do correio já cobre "e-mail sem resposta".
**Tabelas:** `item_email`, `item_frente`, `frente`, `evento`, `tarefa`, `entrega`, `regra_expurgo` (vazias) saem. `caixa_email` (8 linhas) fica como legada; `envelope.py:64` e `rotas/setup.py` deixam de lê-la.

## 4. Cobrança / reembolso PJ — CORTAR, com consulta no lugar
**Fica em `gabi/cobrar/`:** `cadastro.py`, `util.py`, `notas.py`, `notas_importar.py`, `recebimentos.py`, `previsao.py`, `a_receber.py` (NFS-e e "a receber": usados).
**Sai:** `reembolso.py`, `cobranca.py`, `lote_nibo.py`, `comprovantes.py`, `ingestao.py`, `extrator.py`, `pedidos.py`; as rotas correspondentes em `rotas/cobrar.py`; telas `Cobrar/Reembolsos`, `Cobrar/Comprovantes`, `Cobrar/EmailCobranca`, `Caixa/Pedidos`; em `CadastrosCobranca` saem só as partes de liberação de sensível e "pode pedir" (empresas, categorias e sócio do Nibo ficam); ferramentas MCP `cobranca_rascunho`, `reembolsos_listar`, `reembolsos_preparar_email`, `pedidos_registrar`, `pedidos_estado`; `dinheiro/cobranca_atraso.py`; units `gabi-brain-comprovantes.*`; testes correspondentes.
**Entra:** ferramenta MCP `despesas_por_empresa(mes)` (escopo `fin`): lançamentos de saída com `empresa_id` preenchido, pagos em conta que não é PJ, no mês, agrupados por empresa (total e itens). O Ricardo cobra ou lança na PJ ele mesmo (R2 intacta: nada é enviado).
**Tabelas:** `cobranca`, `cobranca_item`, `comprovante`, `comprovante_vinculo`, `reembolso`, `reembolso_item`, `reembolso_baixa`, `lote_nibo`, `lote_nibo_item`, `pedido` (vazias) saem.

## 5. Limpezas pequenas
- `dinheiro/perfil.py` (sem importador em produção) e seus testes saem.
- `dinheiro/condicao.py` e o uso em `regras.py`/`classificar.py` saem (nenhuma das 64 regras usa condição). A coluna `regra.condicao` fica (SQLite exige recriar a tabela para tirar coluna; não compensa).
- Índice FTS da memória (`memoria_fts` e gatilhos) sai por migração; a tabela `memoria` fica.
- Tela "Configuração" (`Configuracao.tsx`, `rotas/setup.py`) e a tabela `setup_passo` (vazia) saem.
- **MCP**: ficam 16 ferramentas — `financeiro_saldo`, `financeiro_lancamentos`, `financeiro_contas_a_pagar`, `financeiro_para_onde_vai`, `financeiro_recorrentes`, `financeiro_previsao`, `agenda_financeira`, `fechamento_dia`, `despesas_por_empresa` (nova), `documentos_buscar`, `documentos_baixar`, `classificar_lancamento`, `regras_sugerir`, `resumo_manha`, `agenda_listar`, `email_listar`. Saem 21 (as 5 de saúde, as 5 de cobrança/pedidos acima, `hoje_resumo`, `frentes_listar`, `frentes_itens`, `contatos_em_aberto`, `tarefas_propor`, `financeiro_vazamentos`, `financeiro_rumo`, `decisoes_abertas`, `decisao_responder`, `avisos_pendentes`, `avisos_confirmar_entrega`, `pessoas_dado`). Mantidas sem uso: `agenda_listar` e `financeiro_para_onde_vai` (são as perguntas centrais "onde preciso estar" e "para onde vai") e `documentos_baixar` (par do buscar). As funções Python de `vazamentos`/`rumo` ficam se o painel as usar (`rumo` é usada por `rotas/gastos.py:317`). Depois do corte, `tools/gerar_hermes.py` regenera a lista do Hermes.
- **Docs**: `PROGRESSO-GOAL.md`, `RELATORIO-2026-10-16.md`, `TRILHA.md`, `aceite-fase-2.md` vão para `docs/historico/`; os specs e planos já executados de `docs/superpowers/` (todos menos os desta simplificação) e `docs/design/` (PNGs) também. Ficam na raiz de `docs/`: `STATUS.md`, `BACKLOG.md`, `PLANO-DEFINITIVO.md`, `ARQUITETURA.md`, `runbook.md`, `api.md`/`openapi.json` (gerados), `adr/`, `fontes/`.

## 6. "Para quem" certeiro — aplicar sozinho
**Hoje:** `classificar._sugerir_por_cache` (`gabi/dinheiro/classificar.py:53`) cria sugestão pendente quando todas as decisões anteriores do Ricardo (`para_quem_origem='voce'`) para o mesmo estabelecimento dão a mesma pessoa. As 113 pendentes são todas desse tipo (32 estabelecimentos); nenhuma foi decidida.
**Passa a ser:** para o campo `para_quem`, quando o critério acima vale **e há pelo menos 2 decisões anteriores do Ricardo**, preenche o lançamento com `para_quem_origem='gabi'` em vez de criar sugestão. Com 1 decisão só, continua sugestão. Categoria continua só sugestão.
- **Registro e desfazer:** cada aplicação grava em `decisao` (`quem='gabi (para quem certeiro)'`, `origem='classificacao'`). O painel já mostra a origem; trocar a pessoa no painel grava `voce` e passa a mandar.
- **Fila atual:** uma rodada única aplica, pelo mesmo critério, as sugestões `para_quem` pendentes e marca-as `aprovada` (`motivo` acrescido de "aplicada sozinha"); as que não passam (1 decisão só) ficam pendentes.
- **Sem conflito com regras:** `voce`, `regra` e `fonte` nunca são sobrescritos (a ordem atual em `classificar()` não muda).

## 7. Conferência de saldo — aviso, não trava
**Hoje:** `conferencia.py` (192 linhas, 11 constantes, três heurísticas) decide se a rodada é `conferida`; rodada não conferida trava o `dados_ate` e gera `rodada_parada`.
**Passa a ser:**
- `marcar_conferida(rodada)` = a rodada terminou `ok` e sem `erro`. As checagens não decidem mais.
- Fica uma checagem por conta bancária (cartão fora): **saldo × lançamentos** — variação do saldo entre o último fechamento de dia e o atual comparada à soma dos lançamentos postados; diferença de até 1 centavo é arredondamento. Divergência grava a linha em `conferencia` (`ok=0`, com o detalhe) e gera o aviso `saldo_divergente` (um por conta por dia), só informativo.
- Saem: `_dias_sem_buraco`, `_volume_proximo`, `_maior_sequencia`, `_saldo_igual`, a soma de subconjuntos, o dia-base e a explicação por fatura, e as constantes de calibração. ADR-009 ganha nota "substituída por ADR-023".
- `avisos.py`: `rodada_parada` passa a significar só "a rodada falhou/não terminou" (as duas últimas sem `ok`, ou nenhuma `ok` em `HORAS_DADOS_ANTIGOS`).

## Migração
Uma migração nova (`00NN_simplificacao.sql`) remove **só** as tabelas vazias listadas acima (`drop table if exists`) e o FTS da memória (gatilhos + tabela virtual). O teste da migração confere que nenhuma das tabelas legadas com dado (`escuta_remetente`, `caixa_email`, `memoria`) é tocada. **Antes do deploy**, uma consulta só leitura no banco de produção confirma que cada tabela a remover está com 0 linhas; se alguma tiver linha, ela sai da migração.

## ADR e documentos
- **ADR-023 "Simplificação de 21/10"**: o que saiu, por quê (uso zero), o que ficou legado, a flexibilização de R1 no "para quem" e a conferência informativa. ADRs afetadas (009, 014, 016, 018 no que toca Trabalho, e as da escuta) recebem nota "substituída/encerrada por ADR-023".
- `BACKLOG.md`: tiram-se os itens de escuta (E2–E4), saúde, cobrança (C1, C2), Obsidian, Linear e `gabi-brain-escuta.path`; D2 vira "resolvido por ADR-023"; H7 deixa de depender de E4.
- `STATUS.md`, `ARQUITETURA.md`, `runbook.md`: atualizados (seções de escuta, saúde, Trabalho e cobrança saem; tabelas legadas listadas).

## Testes
- Cada corte remove os testes do que saiu e mantém verdes os que ficam: `.venv/bin/python -m pytest -q` (suíte inteira, lendo o resumo do pytest, não o código de saída) e `cd painel && npx vitest run && npm run build`.
- Testes novos: `despesas_por_empresa`; "para quem" certeiro (aplica com ≥2 decisões, sugere com 1, não sobrescreve `voce/regra/fonte`, registra em `decisao`, rodada única da fila); conferência (rodada ok = conferida mesmo com divergência; divergência gera `saldo_divergente` uma vez por dia; 1 centavo não diverge); migração (tabelas vazias somem, legadas ficam).
- `tests/test_deploy.py` e `tests/test_docs_api.py` atualizados para as units e rotas que saem; `tools/gerar_docs_api.py` regenera `api.md`/`openapi.json`.

## Produção (só com autorização do Ricardo, no fim)
1. Consulta só leitura confirmando 0 linhas nas tabelas a remover.
2. `sudo systemctl disable --now escuta-ouvinte gabi-brain-escuta.timer gabi-brain-escuta.path gabi-brain-trabalho.timer gabi-brain-comprovantes.timer gabi-brain-exames.timer gabi-brain-reembolso-saude.timer`, e remover essas units de `/etc/systemd/system`.
3. `sudo ~/instalar-brain.sh` (migração, código, painel).
4. Conferir: API, MCP e painel no ar; Hermes chama `resumo_manha`; rodada de extratos `conferida=1`; nenhuma unit em `failed`.
5. **Fica para o Ricardo decidir depois** (não fazemos): desparear o aparelho do WhatsApp, apagar `/var/lib/escuta-ouvinte`, `/opt/escuta-ouvinte` e o spool, o cofre `saude.enc` e a chave, e o arquivo `~/saude.key.COPIE-E-APAGUE`.

## Fora do escopo (sugeridos na revisão, não escolhidos agora)
Achatar compromissos/conciliação (gabi-fin portado), enxugar a lixeira do e-mail, congelar a rodada diária de propostas de contatos, tirar e-mails do próprio sistema do alerta "emergencial", reduzir a frequência dos timers de Teams e agenda, revisar o custo do modelo de reserva do e-mail.
