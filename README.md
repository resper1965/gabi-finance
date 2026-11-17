# gabi-finance

Serviço **só financeiro** da Gabi, a assistente pessoal agêntica do Ricardo Esper. Lê extratos e saldos pelo Open Finance (mcp.ai) e as notas fiscais pelo Nibo, guarda tudo num banco SQLite e responde a perguntas como "tenho caixa?", "o que vence esta semana?", "para onde foi o dinheiro?" e "quem me deve?", por um **painel web** (atrás da Tailscale) e por um **servidor MCP** que o agente de conversa (Hermes, no Telegram e no WhatsApp) usa.

> **Estado (17/11/2026): corte pronto, virada pendente.** O código, o banco, o painel, o MCP, o deploy e esta documentação estão prontos na branch `corte`; ainda não foi feito o merge na `main` nem a instalação na VPS. O roteiro para colocar no ar, com verificação em cada passo e a volta, é o [`docs/virada.md`](docs/virada.md). Situação e pendências: [`docs/STATUS.md`](docs/STATUS.md).

## Índice

- [Por que existe](#por-que-existe) · [O que faz](#o-que-faz) · [Como funciona](#como-funciona) · [Princípios](#princípios)
- [Estrutura do repositório](#estrutura-do-repositório) · [Instalação](#instalação) · [Operação](#operação)
- [Desenvolvimento](#desenvolvimento) · [Mapa da documentação](#mapa-da-documentação)

## Por que existe

O `gabi-brain` concentrava tudo: dinheiro, agenda, e-mail, Teams, contatos, família, documentos, projetos. Na reescrita da Gabi (projeto **esper-brain**), o contexto da vida passa a viver num **segundo cérebro em markdown** (`resper1965/esper-brain`), e só o que precisa de banco e de conta exata fica como serviço. Este repositório é esse serviço: nasceu como cópia do `gabi-brain` (com todo o histórico) e foi cortado até ficar só com o dinheiro. O comportamento financeiro não mudou.

| Etapa | O quê | Estado |
|---|---|---|
| 1 | Migrar o contexto (família, pessoas, projetos, empresas) para o `esper-brain` | concluída |
| 2 | Quebrar o `gabi-brain`: nasce o **gabi-finance** | **corte pronto; virada pendente** |
| 3 | Migrar a VPS: coletor, digestão e Hermes lendo o `esper-brain` | a fazer |
| 4 | Testar GBrain e Honcho sobre o markdown | a fazer |

A decisão e tudo o que saiu: [`docs/adr/039-corte-gabi-finance.md`](docs/adr/039-corte-gabi-finance.md).

## O que faz

- **Extratos e saldos** do Open Finance (mcp.ai): captura incremental, com o dado bruto guardado antes de processar; saldos de hora em hora e rodada completa duas vezes por dia.
- **Conferência:** cada rodada compara saldo e contagem com a fonte; só a rodada conferida atualiza o "dados até" que o painel e o Hermes mostram.
- **Classificação:** categoria, "para quem", empresa, "quem gastou" (portador do cartão), gasto ou não gasto, reembolso, assinaturas, parcelas e moeda estrangeira. Regras e padrões editáveis; cada decisão guarda a origem.
- **A pagar:** compromissos do mês a partir das despesas cadastradas, vencimentos, atrasos, débito automático, conciliação com o extrato.
- **Projeção de caixa** (30 dias) e agenda financeira pronta para o celular.
- **A receber:** notas fiscais (NFS-e) e valores do Nibo, previsão de entradas, e baixas **propostas** (o Ricardo confirma).
- **Avisos:** vence hoje, vence em breve, valor diferente, conta atrasada, saldo divergente, banco desatualizado; sino do painel e, se ligado, Telegram. Resumo financeiro da manhã (07:05, pelo Hermes).
- **Painel:** [Caixa, Gastos, Cobrar, Regras, Cadastros e Agentes](docs/painel.md).
- **MCP:** [33 ferramentas](docs/mcp.md) de leitura, de proposta e de gravação pequena a pedido do Ricardo, com token e escopo por agente.
- **Backup** diário com teste de restauração e exportação semanal criptografada para fora da VPS.

## Como funciona

```
mcp.ai (Open Finance) ─┐  (extratos e saldos chamam direto, com MCPAI_KEY)
                       │
Nibo (NFS-e) ──────► ponte `fontes` (único processo com o token do Nibo)
                       │
                       ▼
            gabi-finance: banco SQLite (WAL) + bruto imutável
     ┌───────────────┼────────────────┐
     ▼               ▼                ▼
 painel web      MCP gabi_finance    timers (saldos, extratos, notas,
 (Tailscale)     (Hermes)            avisos, Telegram, backup)
```

Um banco SQLite num arquivo só; uma API FastAPI em **socket Unix** (sem porta TCP) exposta apenas pelo `tailscale serve`, que injeta a identidade de quem entra; um servidor MCP em `127.0.0.1:8082` com token por agente; e tarefas curtas disparadas por timers do systemd. Só um processo tem rede e o token do Nibo. Detalhes, diagrama completo e fronteira de confiança: [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md).

**Tecnologia:** Python 3 (FastAPI, SQLite, uvicorn), painel React 19 + TypeScript + Vite, systemd, Tailscale. Código e comentários em português.

## Princípios

- **A Gabi sugere, o Ricardo decide** (R1). Sugestões, regras e baixas ficam pendentes até o clique.
- **Nada sai sozinho** (R2): nada paga, envia ou apaga automaticamente. A única exceção, escolhida por ele, é o aviso no Telegram. O MCP não tem ferramenta de pagar, enviar, apagar, aprovar nem ligar regra (R13).
- **Segredos só no ambiente** (R5): nunca no repositório, no banco ou em log; só a ponte tem o token do Nibo.
- **Dinheiro em centavos inteiros** (R7); a API devolve string decimal.
- **Texto de terceiros é dado, nunca instrução** (R14).

## Estrutura do repositório

| Pasta | O que tem |
|---|---|
| `gabi/` | O código Python: `dinheiro/` (núcleo financeiro), `cobrar/` (notas e a receber), `fontes/` (mcp.ai, Nibo e a ponte), `mcp/` (servidor MCP), `rotas/` (rotas HTTP) e os módulos de base. Mapa: [`docs/modulos.md`](docs/modulos.md) |
| `painel/` | O painel React/Vite; a saída compilada vai para `gabi/painel/` (ignorada pelo git). Ver [`docs/painel.md`](docs/painel.md) |
| `migrations/` | As migrações SQL numeradas (até a 0091). Tabelas: [`docs/dados.md`](docs/dados.md) |
| `seeds/` | Dados editáveis fora do código (categorias, donos padrão) |
| `deploy/` | Unidades systemd e timers, `instalar.sh`, o SOUL e o vigia do Hermes |
| `tools/` | Utilitários de administração e de desenvolvimento ([lista](docs/runbook.md#ferramentas-de-administração-tools)) |
| `tests/` | A suíte Python; `tests/test_docs.py` falha se a documentação ficar para trás |
| `docs/` | Toda a documentação (mapa abaixo) |

## Instalação

A instalação é feita pelo Ricardo, como `root`, numa VPS Linux com systemd, Python 3 com `venv`, Node para compilar o painel e Tailscale; o Claude guia. O passo a passo exato, com verificação em cada passo, é o [`docs/virada.md`](docs/virada.md). Em resumo:

```bash
cd painel && npm ci && npm run build        # o instalador copia gabi/ (com o painel compilado) e não roda npm
cd .. && sudo bash deploy/instalar.sh --confirmo-backup-exportado
```

O instalador cria os usuários (`gabifinance`, `gabifinance-fontes`), as pastas (`/opt/gabi-finance`, `/var/lib/gabi-finance`, `/var/backups/gabi-finance`, `/etc/gabi-finance`), o ambiente Python e as unidades `gabi-finance-*`, e **não liga nada**: quem liga é a virada, na ordem certa, depois da conferência. Os segredos (`MCPAI_KEY`, `NIBO_TOKEN`, Telegram) vão em `/etc/gabi-finance/*.env`, criados à mão, modo 600.

## Operação

Tudo roda no `systemd`: serviços `fontes`, `api` e `mcp` sempre ligados, e tarefas de timer para saldos (de hora em hora), extratos (06:00 e 14:00), notas (06:40), avisos (15 min), Telegram (5 min), backup (03:30) e exportação semanal (domingo 04:00).

```bash
systemctl is-active gabi-finance-fontes gabi-finance-api gabi-finance-mcp
systemctl list-timers 'gabi-finance-*'
journalctl -u gabi-finance-extratos -n 30 --no-pager -o cat
```

Horários, logs, avisos, rotação de segredos e falhas comuns: [`docs/operacao.md`](docs/operacao.md). Procedimentos (acesso, restaurar o banco, backup fora da VPS, tokens do MCP, Hermes): [`docs/runbook.md`](docs/runbook.md).

## Desenvolvimento

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.lock pytest ruff
.venv/bin/python -m pytest -q                  # a suíte inteira (Python)
.venv/bin/ruff check gabi tools tests          # lint
cd painel && npm ci && npx vitest run && npm run build
```

- Esquema só muda por **migração nova** em `migrations/` (nunca editar uma antiga). `tests/test_migracao_corte.py` obriga decidir se uma tabela nova fica no inventário.
- `docs/api.md` e `docs/openapi.json` são **gerados** (`python -m tools.gerar_docs_api`); um teste falha se ficarem velhos. A lista de ferramentas do Hermes em `docs/fontes/hermes.md` também (`python -m tools.gerar_hermes`).
- `tests/test_docs.py` confere que todo módulo de `gabi/`, toda ferramenta MCP e toda tabela do banco aparecem em [`modulos.md`](docs/modulos.md), [`mcp.md`](docs/mcp.md) e [`dados.md`](docs/dados.md).
- **Regra de ouro:** nenhum teste financeiro é apagado ou enfraquecido para o código passar.

## Mapa da documentação

| Quero... | Leia |
|---|---|
| Entender o desenho em uma página | [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) |
| Saber por que o repositório existe e o que saiu | [`docs/adr/039-corte-gabi-finance.md`](docs/adr/039-corte-gabi-finance.md) e [`docs/corte/costuras.md`](docs/corte/costuras.md) |
| Colocar no ar (a virada) | [`docs/virada.md`](docs/virada.md) |
| Ver a situação e as pendências | [`docs/STATUS.md`](docs/STATUS.md) |
| Operar no dia a dia | [`docs/operacao.md`](docs/operacao.md) e [`docs/runbook.md`](docs/runbook.md) |
| Achar o que cada módulo faz | [`docs/modulos.md`](docs/modulos.md) |
| Entender as tabelas | [`docs/dados.md`](docs/dados.md) |
| Ver as ferramentas do agente | [`docs/mcp.md`](docs/mcp.md), [`docs/fontes/hermes.md`](docs/fontes/hermes.md) |
| Ver as rotas da API | [`docs/api.md`](docs/api.md) (gerado) e [`docs/openapi.json`](docs/openapi.json) |
| Entender as telas | [`docs/painel.md`](docs/painel.md) |
| Conhecer as fontes externas | [`docs/fontes/mcpai.md`](docs/fontes/mcpai.md), [`docs/fontes/nibo.md`](docs/fontes/nibo.md) |
| Ler as decisões antigas | [`docs/adr/`](docs/adr/README.md) |
| Ver o desenho e o plano do corte | [`docs/superpowers/specs/2026-11-17-gabi-finance-design.md`](docs/superpowers/specs/2026-11-17-gabi-finance-design.md) e [`docs/superpowers/plans/2026-11-17-gabi-finance-corte.md`](docs/superpowers/plans/2026-11-17-gabi-finance-corte.md) |
| Consultar o histórico do tempo do `gabi-brain` | [`docs/historico/`](docs/historico/) |
