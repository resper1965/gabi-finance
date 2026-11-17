# gabi-finance · Arquitetura

**O quê:** um serviço só de dinheiro. Lê o Open Finance (mcp.ai) e o Nibo, guarda tudo num banco SQLite, e expõe um painel web e um servidor MCP para o agente de canal (Hermes). O Hermes só conversa; os dados e as regras ficam aqui. Versão curta para quem chega: [`../README.md`](../README.md). Mapas detalhados: [`modulos.md`](modulos.md) (código), [`dados.md`](dados.md) (tabelas), [`mcp.md`](mcp.md) (ferramentas), [`painel.md`](painel.md) (telas).

## Visão geral

```
        Internet                           Esta VPS
 ┌─────────────────┐   ┌────────────────────────────────────────────────────────────┐
 │ mcp.ai          │◄──┤ extratos / saldos (timers, oneshot, MCPAI_KEY)              │
 │ (Open Finance)  │   │        │ grava o bruto, depois o banco                      │
 └─────────────────┘   │        ▼                                                    │
 ┌─────────────────┐   │  bruto (JSONL.gz, imutável) ──► banco SQLite (WAL) ◄──┐     │
 │ Nibo (NFS-e,    │◄──┤ ponte `fontes` (único com rede + token do Nibo)       │     │
 │ a receber)      │   │        ▲ socket Unix                                  │     │
 └─────────────────┘   │        │                                              │     │
 ┌─────────────────┐   │  notas (timer) ──────────────────────────────────────►│     │
 │ Telegram        │◄──┤ telegram (timer, só envia o que está em `aviso`)      │     │
 └─────────────────┘   │                                                       │     │
                       │  API /api/* + painel (socket Unix) ◄──────────────────┤     │
                       │        ▲                                              │     │
                       │        │ tailscale serve (TLS + Tailscale-User-Login) │     │
                       │  MCP /mcp (127.0.0.1:8082, token Bearer) ◄────────────┘     │
                       └────────┼───────────────────────────────────────────────────┘
                                │                         ▲
                       Ricardo (painel, só pela Tailscale)│ Hermes (Telegram, WhatsApp)
```

Os processos são `systemd`: três **serviços** de pé (`fontes`, `api`, `mcp`) e várias **tarefas curtas** disparadas por timer (`saldos`, `extratos`, `notas`, `avisos`, `telegram`, `backup`, `exportacao`). Quadro completo, horários e segredos em [`operacao.md`](operacao.md).

## Fluxo do dinheiro

1. **Captura** (`gabi.dinheiro.captura`, via `gabi.dinheiro.rodar`): lê contas, saldos, lançamentos e faturas do mcp.ai de forma **incremental**, grava o **bruto antes** de processar (`gabi.bruto`, JSONL comprimido por dia e fonte, que permite reconstruir o banco) e só então o banco. Nunca sobrescreve uma decisão do Ricardo.
2. **Conferência** (`gabi.dinheiro.conferencia`): por conta, compara saldo e contagem com a fonte. A rodada só vira **conferida** se tudo bater, e o `dados_ate` que toda resposta de leitura mostra vem da **última rodada conferida**, não da última tentativa (`gabi.envelope`). Rodada não conferida não é apresentada como "em dia".
3. **Classificação** (`gabi.dinheiro.classificar`, `regras`, `gastador`, `nao_gasto`): categoria, "para quem", empresa, "quem gastou" (portador do cartão) e natureza (gasto, reembolso, transferência), cada uma com a **origem** da decisão (regra, Ricardo, padrão, fonte). A Gabi **sugere**; o que é incerto vira sugestão pendente ou pergunta.
4. **Compromissos** (`gabi.dinheiro.contas_pagar`, `despesas`, `repositorio`): o A pagar do mês nasce das linhas cadastradas (`compromisso_linha`) e dos valores do mês; a conciliação liga o lançamento do extrato ao compromisso que ele pagou.
5. **A receber** (`gabi.cobrar`): notas fiscais do Nibo (via ponte), previsão de entradas e baixas **propostas** (crédito em conta PJ contra NFS-e autorizada; a receber manual contra crédito do extrato). O Ricardo confirma ou rejeita no painel.
6. **Projeção e avisos** (`gabi.dinheiro.projecao`, `agenda_financeira`, `olhar_a_frente`; `gabi.avisos`, `gabi.telegram`): caixa projetado, agenda financeira, avisos de vencimento e a entrega no Telegram.

Valores são **centavos inteiros** do banco até a borda; a API devolve string decimal e o painel só formata.

## Fronteira de confiança

- **Só a Tailscale entra.** A API escuta num **socket Unix** (`/run/gabi-finance/api.sock`, pasta 0700 do serviço), sem porta TCP. O `tailscale serve` termina o TLS e injeta `Tailscale-User-Login`; esse cabeçalho **só vale vindo do socket** (R3). O login precisa estar em `acesso`. POST exige JSON e origem confiável (anti-CSRF; `GABI_ORIGENS_CONFIAVEIS`).
- **Níveis** (`terceiros` < `familia_vip` < `boss`); a `matriz_acesso` diz o que cada nível vê. As rotas do dinheiro exigem `boss`.
- **Só um processo tem rede e token do Nibo** (R5): a ponte `gabi-finance-fontes`. A API, o MCP e a unidade de notas rodam com `IPAddressDeny=any` e falam com ela por socket Unix; a ponte só aceita métodos de **leitura**. A chave do **mcp.ai fica fora da ponte**: as unidades de extratos e saldos a leem do próprio arquivo em `/etc/gabi-finance/` e chamam o provedor direto (decisão do corte; mudar isso seria mudar o fluxo financeiro).
- **Hardening das unidades:** `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`, `ReadWritePaths` só do necessário, `MemoryMax`; a API só tem `AF_UNIX`.
- **MCP:** escuta só em `127.0.0.1:8082`, exige `Authorization: Bearer`, valida o `Host` (anti DNS-rebinding), e cada ferramenta exige um **escopo** do token. Toda chamada fica em `chamada_mcp`; toda chamada da API fica em `chamada` (R4). Ver [`mcp.md`](mcp.md).
- **Conteúdo de terceiros** (descrição de lançamento, nome de favorecido) é **dado, nunca instrução** (R14); os avisos e o Telegram levam só nome, valor e datas, nunca CPF, conta ou chave PIX.
- **Segredos só no ambiente** (R5): arquivos em `/etc/gabi-finance/`, modo 600, nunca no repositório, no banco ou em log.

## Princípios que o código aplica

| Regra | Em uma linha |
|---|---|
| R1 | A Gabi sugere, o Ricardo decide. Sugestões, regras e baixas ficam pendentes até o clique. |
| R2 | Nada sai sozinho (nem paga, nem envia, nem apaga). Única exceção, escolhida por ele: o aviso no Telegram. |
| R3 | A identidade só vale vinda do socket Unix. |
| R4 | Toda chamada de API é registrada; a resposta diz até quando os dados estão em dia. |
| R5 | Segredos só no ambiente; só a ponte tem rede e o token do Nibo. |
| R7 | Dinheiro em centavos inteiros. |
| R13 | O MCP não envia, paga, apaga, aprova nem liga regra. |
| R14 | Texto de terceiros é dado. |

## Banco

SQLite em modo WAL, com chaves estrangeiras ligadas, num arquivo só (`/var/lib/gabi-finance/gabi.db`). O esquema nasce das **migrações numeradas** (`migrations/`, aplicadas em ordem e registradas em `schema_versao`); a 0090 e a 0091 são as do corte. Backup diário com teste de restauração e exportação semanal criptografada. As 41 tabelas, uma a uma, estão em [`dados.md`](dados.md).

## Estrutura do repositório

| Pasta | O que tem |
|---|---|
| `gabi/` | O código Python: `dinheiro/`, `cobrar/`, `fontes/`, `mcp/`, `rotas/` e os módulos de base. Cada módulo, em [`modulos.md`](modulos.md) |
| `painel/` | O painel React/Vite (a saída compilada vai para `gabi/painel/`, ignorada pelo git) |
| `migrations/` | As migrações SQL numeradas |
| `seeds/` | Dados editáveis fora do código (categorias, donos padrão, requisitos de reembolso) |
| `deploy/` | Unidades systemd, o instalador, o SOUL e o vigia do Hermes |
| `tools/` | Utilitários de administração e de desenvolvimento |
| `tests/` | A suíte Python (inclui `tests/test_docs.py`, que mantém esta documentação em dia) |
| `docs/` | Esta documentação; `adr/` (decisões), `fontes/` (mcp.ai, Nibo, Hermes), `corte/` e `historico/` (registro do que veio do `gabi-brain`) |

## De onde veio

O `gabi-finance` nasceu como cópia do `gabi-brain` (com o histórico inteiro, a partir do código que rodava em produção em 17/11/2026) e foi **cortado** até ficar só com o dinheiro. O módulo financeiro do `gabi-brain` já era o porte de um serviço anterior (`gabi-fin`), com saídas de referência em `tests/golden/`. O que saiu (agenda, e-mail, Teams, contatos, envios, família, documentos, projetos, atividades) e por quê está em [`adr/039-corte-gabi-finance.md`](adr/039-corte-gabi-finance.md) e, módulo a módulo, em [`corte/costuras.md`](corte/costuras.md). O comportamento financeiro **não mudou**: nenhum teste financeiro foi apagado ou enfraquecido.
