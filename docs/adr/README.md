# Decisões de arquitetura (ADRs)

Uma decisão por arquivo, numerada. Os números **005 e 008 não existem** (a numeração não é reaproveitada).

**Atenção ao ler as ADRs 001–038:** foram escritas no tempo do `gabi-brain` e estão **preservadas como foram escritas**, porque são o registro histórico. Onde dizem `gabi-brain`, `gabi.brain`, `/opt/gabi-brain`, `gabibrain` ou `mcp__gabi_brain__`, leia o equivalente do `gabi-finance` (`/opt/gabi-finance`, `gabifinance`, `mcp__gabi_finance__`; tabela de nomes em [`../virada.md`](../virada.md#mapa)). Várias tratam de áreas que **saíram no corte** (agenda, correio, contatos, documentos, projetos...): continuam valendo como história, não como descrição do que existe; a ADR-039 diz o que saiu.

## O que está valendo para o dinheiro

| ADR | Decisão |
|---|---|
| [001](001-ids-inteiros.md) | IDs inteiros e texto em vez de uuid v7 |
| [002](002-sqlite.md) | SQLite (WAL) no lugar de Postgres dedicado |
| [003](003-tailscale-serve.md) | `tailscale serve` + socket Unix no lugar de Cloudflare Access e nginx |
| [004](004-sem-fila-sem-lake.md) | Sem fila, sem data lake, sem pgvector |
| [006](006-cobranca-so-rascunho.md) | Cobrança por e-mail: só rascunho (o envio saiu no corte) |
| [007](007-identidade-por-remetente.md) | Identidade por remetente no canal |
| [009](009-regra-de-buraco.md) | Regra de "buraco" e saldo na conferência |
| [010](010-donos-padrao-e-origem-fonte.md) | Donos padrão e a origem `fonte` |
| [011](011-favorecido-nao-e-para-quem.md) | Favorecido não é "para quem" |
| [012](012-nfse-previsao-e-nibo-defasado.md) | NFS-e, previsão e Nibo defasado |
| [013](013-aba-previsao-no-caixa.md) | Aba Previsão no Caixa |
| [015](015-aba-configuracao-em-cadastros.md) | Aba "Configuração" em Cadastros |
| [023](023-simplificacao.md) | Simplificação: cortar o que não é usado |
| [026](026-conciliacao-achatada.md) | Conciliação achatada (4 estados, centavos) |
| [028](028-hermes-completo.md) | Hermes completo: honestidade, família e frescor por ferramenta |
| [029](029-nao-gasto-e-rol-de-assinaturas.md) | O que não é gasto e rol de assinaturas |
| [030](030-gastadores.md) | Quem gastou (portadores) |
| [031](031-reembolso-por-compra.md) | Reembolso por compra |
| [032](032-despesas-crud.md) | Despesas: criar, mudar, dispensar e encerrar |
| [036](036-agentes-externos.md) | Agentes externos: chaves e receitas de conexão |
| [037](037-assistente-proativo.md) | Assistente proativo (só `olhar_a_frente` ficou) |

## Históricas (áreas que saíram no corte)

[014](014-saude-em-arquivo-proprio.md) saúde em arquivo próprio (já encerrada pela 023) · [016](016-escuta-no-brain.md) escuta · [017](017-agenda-no-brain.md) agenda · [018](018-correio-no-brain.md) correio · [019](019-graph-ness.md) Graph · [020](020-escrita-contatos-graph.md) e [021](021-limpeza-contatos-graph.md) contatos · [022](022-enriquecer-contatos-email.md) contatos por e-mail · [024](024-envios-com-anuencia.md) envios · [025](025-cadastro-familiar.md) família · [027](027-documentos.md) documentos · [033](033-atividades.md) atividades · [034](034-projetos.md) projetos · [035](035-convites-agenda.md) convites de agenda · [038](038-projetos-no-linear.md) projetos no Linear.

## O corte

| ADR | Decisão |
|---|---|
| [039](039-corte-gabi-finance.md) | Corte do `gabi-brain`: nasce o `gabi-finance` |
