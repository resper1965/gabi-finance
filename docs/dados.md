# Dados: as tabelas do banco

O banco é um arquivo SQLite (`/var/lib/gabi-finance/gabi.db`, modo WAL, chaves estrangeiras ligadas). O esquema é criado e mantido só pelas migrações numeradas em `migrations/` (`python -m gabi.db` ou o `instalar.sh` as aplicam em ordem; `schema_versao` guarda as já aplicadas). **Esta página lista todas as 42 tabelas do banco migrado**, geradas do próprio esquema; `tests/test_docs.py` falha se uma tabela nova não for descrita aqui.

Convenções que valem em todas as tabelas:

- **Dinheiro em centavos inteiros** (`*_centavos`, sempre `INTEGER`). Nunca `float`. A API devolve string decimal.
- **Datas** em texto ISO (`AAAA-MM-DD` ou instante UTC). Os vencimentos de contas são datas locais de São Paulo.
- **Exclusão lógica** onde existe `excluido_em`; nada financeiro é apagado de verdade.
- **Origem de cada decisão** (`*_origem`, `origem`): quem decidiu (regra, Ricardo, modelo, importação). A Gabi sugere e o Ricardo decide (R1).
- "Lê" e "Grava" vêm das instruções SQL de cada módulo; veja [`modulos.md`](modulos.md) para o que cada um faz. As linhas marcadas "carregador" são gravadas pelo `gabi.importar` (carga única do staging, ver `docs/virada.md`).

## De onde vieram as tabelas

A base é a do `gabi-brain` na migração 0089. A **0090** derrubou as tabelas das áreas que saíram (agenda e e-mail sincronizados, Teams, contatos, envios, escuta, documentos e bens de família, projetos, atividades, anexos). A **0091** derrubou `pet`, `allowlist_vip` e `memoria` (minimização de dados: só o carregador as gravava). A **0092** não mexe em tabela: limpa as **linhas** que a cópia do brain traz e o gabi-finance não usa (avisos de tipos que ele não gera e `servico_falhou` de unidade do brain; perguntas abertas com efeito fora de `gabi.decisoes.EFEITOS`, que viram `expirada`; `pessoa.telefone` e tudo de `pessoa.dados` menos `responsavel_por` e `beneficiario`; eventos de agenda passados, privados, cancelados ou de calendário não liberado, e link, organizador e resposta dos que ficam; parâmetros dos módulos que saíram e o `mcp.url` do brain). As listas explícitas do que fica e do que sai estão em `tests/test_migracao_corte.py`. A decisão está em [`adr/039-corte-gabi-finance.md`](adr/039-corte-gabi-finance.md).


## Base: acesso, auditoria e controle

### `acesso`
Quem pode entrar: login do Tailscale, pessoa e nível (`terceiros`, `familia_vip`, `boss`).

- **Colunas** (4): `login`*, `pessoa_id`, `nivel`, `criado_em` (`*` = chave primária)
- **Lida por:** `gabi.api`, `gabi.identidade`
- **Gravada por:** `gabi.acesso`

### `aviso`
Fila de avisos a mostrar no painel e a mandar pelo Telegram (`entregue_em`, `telegram_em`).

- **Colunas** (6): `id`*, `tipo`, `payload`, `criado_em`, `entregue_em`, `telegram_em` (`*` = chave primária)
- **Lida por:** `gabi.mcp.ferramentas_ver`, `gabi.rotas.contagens`
- **Gravada por:** `gabi.avisos`, `gabi.rotas.avisos`, `gabi.telegram`

### `chamada`
Registro de toda chamada `/api/*` (R4): quando, login, método, caminho e status.

- **Colunas** (6): `id`*, `quando`, `login`, `metodo`, `caminho`, `status` (`*` = chave primária)
- **Lida por:** —
- **Gravada por:** `gabi.api`

### `chamada_mcp`
Registro de toda chamada de ferramenta MCP: token, ferramenta, escopo, status e duração.

- **Colunas** (7): `id`*, `quando`, `token_id`, `ferramenta`, `escopo`, `status`, `duracao_ms` (`*` = chave primária)
- **Referências:** `token_id` → `token_agente`
- **Lida por:** `gabi.agentes`
- **Gravada por:** `gabi.mcp.servidor`

### `decisao`
Trilha de auditoria de decisões e mudanças feitas por pessoa ou agente (`quem`, `o_que`, `origem`). Só cresce.

- **Colunas** (5): `id`*, `quando`, `quem`, `o_que`, `origem` (`*` = chave primária)
- **Lida por:** `gabi.mcp.ferramentas_ver`
- **Gravada por:** `gabi.acesso`, `gabi.agentes`, `gabi.api`, `gabi.cobrar.receber_manual`, `gabi.cobrar.recebimentos`, `gabi.decisoes`, `gabi.dinheiro.classificar`, `gabi.dinheiro.contas_pagar`, `gabi.dinheiro.despesas`, `gabi.dinheiro.regras`, `gabi.mcp.ferramentas_agir`, `gabi.rotas.avisos`, `gabi.rotas.cadastros`

### `matriz_acesso`
Qual nível enxerga qual informação (`informacao` × `boss`/`familia_vip`/`terceiros`). Semeada pelas migrações.

- **Colunas** (4): `informacao`*, `boss`, `familia_vip`, `terceiros` (`*` = chave primária)
- **Lida por:** `gabi.identidade`
- **Gravada por:** `gabi.importar`

### `parametro`
Pares chave/valor de configuração e de estado (por exemplo teto de custo do modelo, marcas de captura).

- **Colunas** (2): `chave`*, `valor` (`*` = chave primária)
- **Lida por:** `gabi.avisos`, `gabi.dinheiro.modelo`, `gabi.envelope`, `gabi.rotas.gastos`
- **Gravada por:** `gabi.dinheiro.captura`, `gabi.dinheiro.repositorio`, `gabi.rotas.cadastros`

### `pergunta`
Canal de decisão: perguntas que a Gabi faz ao Ricardo (com `opcoes`) e as respostas (`escolha`).

- **Colunas** (10): `id`*, `tipo`, `titulo`, `contexto`, `opcoes`, `estado`, `criada_em`, `respondida_em`, `escolha`, `origem` (`*` = chave primária)
- **Lida por:** `gabi.dinheiro.sugestoes_agenda`, `gabi.dinheiro.sugestoes_dono`
- **Gravada por:** `gabi.decisoes`

### `rodada`
Uma rodada de captura/conferência por fonte (`fonte`, `inicio`, `fim`, `status`, contagens). `conferida` marca a última rodada confiável: `dados_ate` dos envelopes vem dela.

- **Colunas** (10): `id`*, `fonte`, `inicio`, `fim`, `status`, `lidos`, `novos`, `alterados`, `erro`, `conferida` (`*` = chave primária)
- **Lida por:** `gabi.api`, `gabi.avisos`, `gabi.envelope`, `gabi.rotas.dinheiro`
- **Gravada por:** `gabi.dinheiro.captura`, `gabi.dinheiro.conferencia`, `gabi.rodada`

### `schema_versao`
Migrações já aplicadas (`nome`, `aplicada_em`). `gabi.db.migrar` aplica as pendentes em ordem.

- **Colunas** (2): `nome`*, `aplicada_em` (`*` = chave primária)
- **Lida por:** `gabi.api`
- **Gravada por:** `gabi.db`

### `token_agente`
Tokens dos agentes externos do MCP: só o hash fica guardado; `escopo` limita as ferramentas; `revogado_em` corta o acesso.

- **Colunas** (6): `id`*, `nome`, `escopo`, `hash`, `criado_em`, `revogado_em` (`*` = chave primária)
- **Lida por:** `gabi.agentes`
- **Gravada por:** `gabi.api`, `gabi.mcp.tokens`


## Cadastros

### `categoria`
Árvore de categorias (`pai_id`), com `dono_padrao` e a ligação com a categoria do Nibo.

- **Colunas** (6): `id`*, `nome`, `pai_id`, `excluido_em`, `nibo_category_id`, `dono_padrao` (`*` = chave primária)
- **Referências:** `dono_padrao` → `pessoa`, `pai_id` → `categoria`
- **Lida por:** `gabi.dinheiro.assinaturas`, `gabi.dinheiro.classificar`, `gabi.dinheiro.consultas`, `gabi.dinheiro.modelo`, `gabi.dinheiro.repositorio`, `gabi.rotas.gastos`
- **Gravada por:** `gabi.rotas.cadastros`

### `empresa`
Empresas (as do Ricardo e as contrapartes). Carregada do staging.

- **Colunas** (6): `id`*, `nome`, `cnpj`, `dados`, `origem`, `excluido_em` (`*` = chave primária)
- **Lida por:** `gabi.cobrar.cadastro`, `gabi.dinheiro.consultas`, `gabi.dinheiro.despesas_empresa`, `gabi.dinheiro.nao_gasto`, `gabi.mcp.ferramentas_agir`, `gabi.mcp.ferramentas_ver`
- **Gravada por:** `gabi.importar`

### `equivalencia_categoria`
De-para da categoria do Open Finance (Pluggy) para a categoria do gabi-finance.

- **Colunas** (2): `origem_pluggy`, `categoria_id`
- **Referências:** `categoria_id` → `categoria`
- **Lida por:** `gabi.dinheiro.classificar`
- **Gravada por:** `gabi.rotas.cadastros`

### `pessoa`
Pessoas (o Ricardo, a família, favorecidos que viraram "para quem"). Todas as linhas ficam; desde a 0092 sem telefone e com `dados` reduzido a `responsavel_por` e `beneficiario` (o que o dinheiro lê).

- **Colunas** (7): `id`*, `nome`, `papel`, `telefone`, `dados`, `origem`, `excluido_em` (`*` = chave primária)
- **Lida por:** `gabi.decisoes`, `gabi.dinheiro.classificar`, `gabi.dinheiro.consultas`, `gabi.dinheiro.gastador`, `gabi.dinheiro.modelo`, `gabi.dinheiro.repositorio`, `gabi.dinheiro.sugestoes_dono`, `gabi.mcp.ferramentas_agir`, `gabi.rotas.cadastros`, `gabi.rotas.dinheiro`
- **Gravada por:** `gabi.importar`


## Dinheiro: contas, extrato, classificação

### `assinatura`
Estado do rol de assinaturas por estabelecimento (`status`, `lembrar_ate_cancelar`) e o "reembolso por" (`empresa_id`: a empresa que reembolsa as cobranças dela; vazio = pessoal).

- **Colunas** (6): `id`*, `estabelecimento`, `status`, `lembrar_ate_cancelar`, `status_em`, `empresa_id` (`*` = chave primária)
- **Referências:** `empresa_id` → `empresa`
- **Lida por:** `gabi.avisos`, `gabi.dinheiro.assinaturas`
- **Gravada por:** `gabi.mcp.ferramentas_agir`, `gabi.rotas.gastos`

### `assinatura_reembolso`
Os lançamentos que uma assinatura com "reembolso por" marcou sozinha (origem `regra`), para desfazer só esses quando a empresa muda ou volta a pessoal.

- **Colunas** (3): `lancamento_id`*, `assinatura_id`, `empresa_id` (`*` = chave primária)
- **Referências:** `lancamento_id` → `lancamento`, `assinatura_id` → `assinatura`
- **Lida e gravada por:** `gabi.dinheiro.assinaturas`

### `captura_conta`
O que cada rodada leu de cada conta (`lidos`, `novos`, `concluida_em`).

- **Colunas** (6): `rodada_id`*, `account_id`*, `dia`, `lidos`, `novos`, `concluida_em` (`*` = chave primária)
- **Referências:** `rodada_id` → `rodada`
- **Lida por:** —
- **Gravada por:** `gabi.dinheiro.captura`

### `conciliacao`
Liga um lançamento (`tx_id`) ao compromisso que ele pagou, com o método e a diferença em centavos.

- **Colunas** (5): `tx_id`*, `compromisso_id`, `metodo`, `diferenca_centavos`, `criado_em` (`*` = chave primária)
- **Lida por:** `gabi.avisos`, `gabi.dinheiro.classificar`, `gabi.dinheiro.despesas`
- **Gravada por:** `gabi.dinheiro.captura`, `gabi.dinheiro.repositorio`, `gabi.importar`

### `conferencia`
Resultado das conferências automáticas por rodada (tipo, conta, `ok`, detalhe).

- **Colunas** (7): `id`*, `rodada_id`, `tipo`, `conta_id`, `ok`, `detalhe`, `criado_em` (`*` = chave primária)
- **Referências:** `conta_id` → `conta`, `rodada_id` → `rodada`
- **Lida por:** `gabi.avisos`, `gabi.rotas.dinheiro`
- **Gravada por:** `gabi.dinheiro.conferencia`

### `conta`
Contas e cartões (Open Finance e manuais): instituição, tipo, apelido, se é PJ, titular, limite e vencimento da fatura.

- **Colunas** (14): `id`*, `externo_id`, `instituicao`, `tipo`, `apelido`, `pj`, `estado`, `nibo_account_id`, `excluido_em`, `titular`, `limite_centavos`, `disponivel_centavos`, `vencimento_fatura`, `usuarios` (`*` = chave primária)
- **Lida por:** `gabi.avisos`, `gabi.cobrar.a_receber`, `gabi.cobrar.receber_manual`, `gabi.cobrar.recebimentos`, `gabi.dinheiro.classificar`, `gabi.dinheiro.conferencia`, `gabi.dinheiro.consultas`, `gabi.dinheiro.contas_pagar`, `gabi.dinheiro.despesas_empresa`, `gabi.dinheiro.esperados`, `gabi.dinheiro.fechamento`, `gabi.dinheiro.gastador`, `gabi.dinheiro.nao_gasto`, `gabi.dinheiro.repositorio`, `gabi.dinheiro.rodar`, `gabi.dinheiro.rumo`, `gabi.dinheiro.sugestoes_agenda`, `gabi.dinheiro.sugestoes_dono`, `gabi.rotas.contagens`, `gabi.rotas.dinheiro`, `gabi.rotas.gastos`
- **Gravada por:** `gabi.decisoes`, `gabi.dinheiro.captura`, `gabi.rotas.cadastros`

### `conta_estado`
Estado da conexão por conta no staging: último lançamento real, última sincronização, status e saldo.

- **Colunas** (10): `account_id`*, `banco`, `nome`, `tipo`, `pj`, `ult_tx_real`, `ult_sync_ok`, `status_conexao`, `saldo_centavos`, `atualizado_em` (`*` = chave primária)
- **Lida por:** `gabi.dinheiro.repositorio`
- **Gravada por:** `gabi.dinheiro.captura`, `gabi.importar`

### `fatura`
Faturas de cartão: vencimento, total, mínimo e situação do pagamento.

- **Colunas** (7): `id`*, `account_id`, `vencimento`, `total_centavos`, `minimo_centavos`, `pagamento_status`, `conta_id` (`*` = chave primária)
- **Referências:** `conta_id` → `conta`
- **Lida por:** `gabi.dinheiro.contas_pagar`, `gabi.dinheiro.nao_gasto`, `gabi.dinheiro.projecao`, `gabi.dinheiro.repositorio`, `gabi.rotas.gastos`
- **Gravada por:** `gabi.dinheiro.captura`, `gabi.importar`

### `gastador_regra`
Regras de "quem gastou" por conta e estabelecimento.

- **Colunas** (5): `id`*, `conta_id`, `estabelecimento`, `pessoa_id`, `criado_em` (`*` = chave primária)
- **Referências:** `pessoa_id` → `pessoa`, `conta_id` → `conta`
- **Lida por:** —
- **Gravada por:** `gabi.dinheiro.gastador`

### `lancamento`
O extrato: um lançamento por movimento, com valor em centavos, classificação (categoria, para quem, empresa, gastador, natureza), parcela e a origem de cada decisão (`*_origem`).

- **Colunas** (31): `id`*, `conta_id`, `externo_id`, `data`, `valor_centavos`, `descricao_original`, `estabelecimento`, `forma`, `categoria_id`, `categoria_origem`, `para_quem_id`, `para_quem_origem`, `empresa_id`, `empresa_origem`, `frente_id`, `fatura_id`, `parcela`, `parcelas`, `data_compra`, `status`, `bruto_ref`, `natureza`, `operacao`, `categoria_banco`, `moeda`, `valor_original_centavos`, `convertido`, `natureza_manual`, `natureza_regra`, `gastador_id`, `gastador_origem` (`*` = chave primária)
- **Referências:** `gastador_id` → `pessoa`, `empresa_id` → `empresa`, `para_quem_id` → `pessoa`, `categoria_id` → `categoria`, `conta_id` → `conta`
- **Lida por:** `gabi.avisos`, `gabi.cobrar.a_receber`, `gabi.cobrar.receber_manual`, `gabi.cobrar.recebimentos`, `gabi.dinheiro.assinaturas`, `gabi.dinheiro.conferencia`, `gabi.dinheiro.consultas`, `gabi.dinheiro.contas_pagar`, `gabi.dinheiro.despesas_empresa`, `gabi.dinheiro.esperados`, `gabi.dinheiro.favorecidos`, `gabi.dinheiro.fechamento`, `gabi.dinheiro.modelo`, `gabi.dinheiro.para_quem_fila`, `gabi.dinheiro.repositorio`, `gabi.dinheiro.rumo`, `gabi.dinheiro.sugestoes_dono`, `gabi.mcp.ferramentas_prop`, `gabi.rotas.cadastros`, `gabi.rotas.cobrar`, `gabi.rotas.contagens`, `gabi.rotas.gastos`
- **Gravada por:** `gabi.decisoes`, `gabi.dinheiro.captura`, `gabi.dinheiro.classificar`, `gabi.dinheiro.gastador`, `gabi.dinheiro.nao_gasto`, `gabi.dinheiro.regras`, `gabi.mcp.ferramentas_agir`, `gabi.rotas.dinheiro`

### `regra`
Regras de classificação e de destino (`padrao`, `acao`, `condicao`). Só o Ricardo liga uma regra (R1/R13).

- **Colunas** (7): `id`*, `padrao`, `acao`, `ativa`, `criado_em`, `criada_por`, `condicao` (`*` = chave primária)
- **Lida por:** `gabi.dinheiro.classificar`, `gabi.dinheiro.favorecidos`, `gabi.mcp.ferramentas_ver`, `gabi.rotas.dinheiro`
- **Gravada por:** `gabi.dinheiro.regras`

### `saldo`
Saldo de cada conta por instante (`conta_id`, `em`, `saldo_centavos`). Base do caixa e da projeção.

- **Colunas** (3): `conta_id`*, `em`*, `saldo_centavos` (`*` = chave primária)
- **Referências:** `conta_id` → `conta`
- **Lida por:** `gabi.dinheiro.conferencia`, `gabi.dinheiro.contas_pagar`, `gabi.dinheiro.repositorio`, `gabi.dinheiro.rumo`, `gabi.rotas.dinheiro`, `gabi.rotas.gastos`
- **Gravada por:** `gabi.dinheiro.captura`

### `sugestao`
Sugestões da Gabi esperando decisão (por exemplo `para_quem`, `regra`, `valor`): `estado`, `motivo`, `payload`.

- **Colunas** (8): `id`*, `tipo`, `lancamento_id`, `payload`, `estado`, `motivo`, `criado_em`, `decidida_em` (`*` = chave primária)
- **Referências:** `lancamento_id` → `lancamento`
- **Lida por:** `gabi.dinheiro.favorecidos`, `gabi.rotas.contagens`, `gabi.rotas.dinheiro`
- **Gravada por:** `gabi.dinheiro.classificar`, `gabi.dinheiro.modelo`, `gabi.dinheiro.para_quem_fila`, `gabi.dinheiro.regras`


## A pagar (compromissos)

### `compromisso`
Contas a pagar de um mês: nome, vencimento, valor, estado (aberto, pago, atrasado, a conferir) e a linha de origem.

- **Colunas** (14): `id`*, `origem`, `linha_id`, `nome`, `vencimento`, `vencimento_util`, `valor_centavos`, `valor_fonte`, `forma`, `account_id`, `estado`, `motivo`, `dados`, `atualizado_em` (`*` = chave primária)
- **Lida por:** `gabi.avisos`, `gabi.dinheiro.classificar`, `gabi.dinheiro.contas_pagar`, `gabi.dinheiro.despesas`, `gabi.dinheiro.projecao`, `gabi.mcp.ferramentas_despesas`, `gabi.rotas.dinheiro`
- **Gravada por:** `gabi.dinheiro.repositorio`, `gabi.importar`

### `compromisso_fixo`
Compromissos fixos como vieram do staging (descrição, periodicidade, dia). Só o carregador grava; a rotina nova usa `compromisso_linha`.

- **Colunas** (9): `id`*, `descricao`, `pessoa_id`, `valor_texto`, `periodicidade`, `dia_vencimento`, `vigencia_ate`, `dados`, `origem` (`*` = chave primária)
- **Lida por:** —
- **Gravada por:** `gabi.importar`

### `compromisso_linha`
Cadastro das linhas que geram compromissos todo mês (como a planilha antiga): vencimento, tipo de valor, forma, conta, vigência.

- **Colunas** (20): `id`*, `nome`, `extrato`, `apelidos`, `vencimento`, `ajuste_dia_util`, `valor_tipo`, `valor_padrao_centavos`, `forma`, `conta`, `cartao`, `documento`, `pix`, `ativo`, `valido_de`, `valido_ate`, `obs`, `linha_planilha`, `excluido_em`, `tipo` (`*` = chave primária)
- **Lida por:** `gabi.dinheiro.contas_pagar`, `gabi.dinheiro.sugestoes_agenda`, `gabi.importar`
- **Gravada por:** `gabi.dinheiro.despesas`, `gabi.dinheiro.repositorio`, `gabi.importar`, `gabi.rotas.cadastros`

### `compromisso_padrao`
Padrão por linha: para quem e categoria que os lançamentos dela herdam.

- **Colunas** (3): `linha_id`*, `para_quem_id`, `categoria_id` (`*` = chave primária)
- **Referências:** `categoria_id` → `categoria`, `para_quem_id` → `pessoa`
- **Lida por:** `gabi.dinheiro.classificar`
- **Gravada por:** — (só a migração ou nenhum código)

### `valor_do_mes`
Valor efetivo de cada linha em cada mês (`mes`, `compromisso`, `valor_centavos`, `data_pagamento`).

- **Colunas** (9): `id`*, `mes`, `compromisso`, `tipo`, `valor_centavos`, `vencimento`, `data_pagamento`, `origem`, `linha_planilha` (`*` = chave primária)
- **Referências:** `compromisso` → `compromisso_linha`
- **Lida por:** —
- **Gravada por:** `gabi.dinheiro.contas_pagar`, `gabi.dinheiro.despesas`, `gabi.dinheiro.repositorio`, `gabi.importar`


## A receber (notas e valores)

### `nota_fiscal`
Notas fiscais emitidas (NFS-e): números, tomador, valores bruto e líquido, retenções, vencimento e a situação do pagamento no Nibo.

- **Colunas** (28): `id`*, `numero`, `rps_numero`, `rps_serie`, `codigo_verificacao`, `emitente_cnpj`, `emissao`, `status`, `valor_bruto_centavos`, `deducoes_centavos`, `descontos_centavos`, `tomador_nome`, `tomador_doc`, `tomador_email`, `descricao`, `retencoes`, `agendamento_id`, `vencimento`, `valor_liquido_centavos`, `nibo_pago`, `nibo_pago_centavos`, `pdf_id`, `xml_id`, `pdf_arquivo`, `xml_arquivo`, `nibo_atualizado_em`, `importado_em`, `atualizado_em` (`*` = chave primária)
- **Lida por:** `gabi.cobrar.a_receber`, `gabi.cobrar.previsao`, `gabi.cobrar.recebimentos`, `gabi.rotas.cobrar`
- **Gravada por:** `gabi.cobrar.notas`

### `receber_manual`
Valores a receber ditados pelo Ricardo (pagador, valor, vencimento).

- **Colunas** (11): `id`*, `pagador`, `valor_centavos`, `vencimento`, `conta`, `observacao`, `estado`, `lancamento_id`, `criado_em`, `quem`, `atualizado_em` (`*` = chave primária)
- **Referências:** `lancamento_id` → `lancamento`
- **Lida por:** `gabi.cobrar.a_receber`, `gabi.cobrar.recebimentos`
- **Gravada por:** `gabi.cobrar.receber_manual`

### `receber_manual_proposta`
Proposta de baixa de um a receber manual contra um lançamento.

- **Colunas** (7): `id`*, `receber_id`, `lancamento_id`, `confianca`, `motivo`, `estado`, `criado_em` (`*` = chave primária)
- **Referências:** `lancamento_id` → `lancamento`, `receber_id` → `receber_manual`
- **Lida por:** `gabi.cobrar.a_receber`
- **Gravada por:** `gabi.cobrar.receber_manual`, `gabi.cobrar.recebimentos`

### `recebimento_nota`
Proposta ou vínculo entre uma nota e o lançamento que a pagou (confiança, motivo, estado).

- **Colunas** (7): `id`*, `nota_id`, `lancamento_id`, `confianca`, `motivo`, `estado`, `criado_em` (`*` = chave primária)
- **Referências:** `lancamento_id` → `lancamento`, `nota_id` → `nota_fiscal`
- **Lida por:** `gabi.cobrar.a_receber`, `gabi.cobrar.previsao`, `gabi.rotas.cobrar`
- **Gravada por:** `gabi.cobrar.receber_manual`, `gabi.cobrar.recebimentos`


## Resíduo do corte (ficam por decisão)

### `agenda_estado`
Estado do staging da agenda financeira. Só o carregador grava.

- **Colunas** (7): `chave`*, `item`, `emissor`, `vencimento`, `valor_centavos`, `status`, `visto_em` (`*` = chave primária)
- **Lida por:** —
- **Gravada por:** `gabi.importar`

### `agenda_evento`
Eventos de agenda. **Congelada**: `dinheiro.sugestoes_agenda` ainda lê, mas nada alimenta mais. A 0092 deixou só os futuros, não privados, não cancelados e de calendário liberado, sem `link_reuniao`, `organizador_nome` e `resposta`.

- **Colunas** (20): `id`*, `fonte_id`, `externo_id`, `inicio_utc`, `fim_utc`, `dia_local`, `dia_fim_local`, `dia_inteiro`, `titulo`, `link_reuniao`, `participantes_qtd`, `status`, `etag`, `atualizado_origem`, `privado`, `ical_uid`, `livre`, `resposta`, `organizador_nome`, `serie_id` (`*` = chave primária)
- **Referências:** `fonte_id` → `agenda_fonte`
- **Lida por:** `gabi.dinheiro.sugestoes_agenda`
- **Gravada por:** — (só a migração ou nenhum código)

### `agenda_eventos`
Eventos do staging da agenda financeira. Só o carregador grava.

- **Colunas** (8): `chave`*, `em`, `item`, `emissor`, `vencimento`, `valor_centavos`, `evento`, `detalhe` (`*` = chave primária)
- **Lida por:** —
- **Gravada por:** `gabi.importar`

### `agenda_fonte`
Fontes de agenda. **Congelada** depois do corte (ver `operacao.md`).

- **Colunas** (11): `id`*, `conta`, `provedor`, `calendario_id`, `nome`, `estado`, `auth`, `sync_token`, `sincronizada_em`, `recarga_em`, `ultimo_erro` (`*` = chave primária)
- **Lida por:** `gabi.dinheiro.sugestoes_agenda`
- **Gravada por:** — (só a migração ou nenhum código)

### `custo_modelo`
Gasto em dólares com o modelo, por tarefa. Lido só pelo cartão "Custo da Gabi"; sem gravador depois do corte.

- **Colunas** (4): `id`*, `em`, `custo_usd`, `tarefa` (`*` = chave primária)
- **Lida por:** `gabi.dinheiro.modelo`
- **Gravada por:** — (só a migração ou nenhum código)

