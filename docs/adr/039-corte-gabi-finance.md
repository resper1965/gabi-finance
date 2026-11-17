# ADR-039 · Corte do gabi-brain: nasce o gabi-finance

Data: 17/11/2026 · Estado: **implementado** na branch `corte` (merge e virada pendentes: [`../virada.md`](../virada.md)) · Spec: [`../superpowers/specs/2026-11-17-gabi-finance-design.md`](../superpowers/specs/2026-11-17-gabi-finance-design.md) · Plano: [`../superpowers/plans/2026-11-17-gabi-finance-corte.md`](../superpowers/plans/2026-11-17-gabi-finance-corte.md) · Registro módulo a módulo: [`../corte/costuras.md`](../corte/costuras.md)

## Contexto

O `gabi-brain` concentrava tudo: dinheiro, agenda, e-mail, Teams, contatos, família, documentos, projetos, atividades e envios, num só serviço com 71 ferramentas MCP e um painel de mais de vinte telas. Na reescrita da Gabi (projeto `esper-brain`), o contexto da vida passa a viver num segundo cérebro em **markdown** (repositório `resper1965/esper-brain`), e só o que **precisa de banco e de conta exata** (extratos, conciliação, compromissos, projeção, notas fiscais) continua como serviço. Este é o passo 2 do desenho do `esper-brain`: quebrar o `gabi-brain` e tirar dele o financeiro.

## Decisão

Criar o repositório `gabi-finance`, nascido **com o histórico inteiro** do `gabi-brain` (a partir do código que rodava em produção em 17/11/2026) e cortá-lo até ficar só com o dinheiro. O `gabi-brain` **não muda** até a virada. As decisões do spec:

| # | Decisão | Onde está feito |
|---|---|---|
| F1 | Repositório próprio com o histórico do `gabi-brain`; o corte é feito aqui | este repositório |
| F2 | **Painel mantido, só financeiro:** Caixa, Gastos, Cobrar, Regras, Cadastros (contas, despesas, cobrança, equivalências) e Gabi › Agentes | [`../painel.md`](../painel.md) |
| F3 | **Banco = cópia da produção** + migração que apaga as tabelas não financeiras; ids, histórico, regras e decisões ficam | migrações 0090 e 0091, [`../dados.md`](../dados.md) |
| F4 | **Troca direta**, com conferência lado a lado (saldos, A pagar do mês, projeção) e volta em um passo | [`../virada.md`](../virada.md), `tools/conferir_virada.py` |
| F5 | **Ponte própria** (único processo com rede e token do Nibo, R5). **Ajuste:** o mcp.ai **fica fora da ponte**, como em produção hoje | [`../operacao.md`](../operacao.md), `deploy/` |
| F6 | **Pessoas ficam** (`pessoa`, portadores dos cartões, `gastador_regra`, "para quem"); ficha da família, documentos, pets e bens saem | `migrations/0090`, `0091` |
| F7 | **Avisos só financeiros** e resumo da manhã financeiro | `gabi/avisos.py`, `gabi/telegram.py`, `resumo_manha` |
| F8 | **MCP** com servidor `gabi_finance` e os **mesmos nomes de ferramenta** das financeiras; o prefixo muda de `mcp__gabi_brain__` para `mcp__gabi_finance__` | [`../mcp.md`](../mcp.md), `deploy/hermes/SOUL.md` |
| F9 | **VPS:** usuário `gabifinance`, `/opt/gabi-finance`, `/var/lib/gabi-finance`, `/var/backups/gabi-finance`, `/etc/gabi-finance/`, unidades `gabi-finance-*`, host `gabi-brain.tail985643.ts.net` (a mesma máquina do brain) com o painel na porta **8444** e o MCP externo na **8445** (a 8443 é do brain) | `deploy/`, [`../virada.md`](../virada.md) |

### Decisões tomadas durante o corte (fora do spec)

1. **Minimização de dados.** `gabi.importar` fica (é a carga do staging financeiro), mas deixa de gravar pets, lista de números autorizados e memória de conversas, e a migração **0091** derruba as tabelas `pet`, `allowlist_vip` e `memoria`. Nada financeiro as lia.
2. **mcp.ai fora da ponte** (ajuste de F5). Pôr o mcp.ai na ponte seria mudar o fluxo financeiro, que é funcionalidade nova e fora de escopo. As unidades de extratos e saldos leem `MCPAI_KEY` do próprio `/etc/gabi-finance/mcpai.env`; a ponte tem só o token do Nibo.
3. **`olhar_a_frente` fica** como ferramenta financeira (caixa projetado e a receber atrasado); as outras do assistente proativo saem.
4. **Nomes limpos:** comentários, textos e padrões que citavam o `gabi-brain` ou o prefixo antigo do Hermes foram trocados em `gabi/` e `deploy/`; as menções históricas ficam só em `docs/historico/` e `docs/corte/` (e nas ADRs antigas, preservadas como foram escritas).
5. **Porta do MCP 8082** (a do `gabi-brain` é 8081), para os dois conviverem durante a conferência e a volta ser possível.
6. **Hermes com token novo** (`GABI_FINANCE_TOKEN`); os tokens herdados na cópia do banco são revogados no passo 4 da virada, e o token antigo do brain fica intocado no brain para a volta.
7. **Degradação aceita:** `agenda_evento` e `agenda_fonte` ficam porque `dinheiro.sugestoes_agenda` as lê, mas nada as alimenta depois do corte; as sugestões de compromisso vindas da agenda degradam até a etapa 3 decidir uma fonte. Registrado em [`../operacao.md`](../operacao.md#limitação-conhecida-agenda-financeira).

## O que saiu

Os módulos e tabelas de **agenda e e-mail sincronizados** (Google e Graph), **Teams**, **contatos**, **envios** (com anuência), **família** (cadastro, documentos, pets, bens), **documentos** (Paperless), **projetos** e **atividades** (com o Linear), **anexos**, **escuta**, **qualidade** do assistente e as fontes Google, Graph, Linear, Paperless e OpenRouter, mais as telas correspondentes do painel e as unidades de systemd dessas áreas. As ferramentas MCP caíram de 71 para **33**. A lista completa, com o motivo de cada decisão duvidosa, está em [`../corte/costuras.md`](../corte/costuras.md) e `docs/corte/saem.txt`. O contexto que saiu vive no `esper-brain` (etapa 1, concluída).

## O que ficou, sem mudar

Todo o comportamento financeiro: captura incremental, conferência, classificação, regras, gastadores, não-gasto, reembolso, compromissos e A pagar, despesas, projeção, assinaturas, a receber e notas, avisos de vencimento, resumo da manhã, backup e exportação. **Nenhum teste financeiro foi apagado ou enfraquecido**; os testes das áreas que saíram foram apagados junto com elas. A migração 0090 tem a lista **explícita** de tabelas que ficam e que saem (`tests/test_migracao_corte.py`), e o teste obriga a decidir sobre tabela nova.

## Consequências

- (+) Um serviço pequeno, com superfície de ataque e de manutenção muito menor, que dá para entender e documentar inteiro.
- (+) Os dados que saíram deixam de morar num banco com segredos e passam para o markdown, onde o Ricardo os controla.
- (+) A volta é barata: o `gabi-brain` continua instalado e só perde o dinheiro depois da conferência.
- (−) Até a etapa 3 o `gabi-brain` e o `gabi-finance` convivem: o Hermes passa a falar com dois servidores MCP, o SOUL do Hermes é editado (prefixo `mcp__gabi_finance__` nas ferramentas de dinheiro) e o brain, com `GABI_SEM_FINANCEIRO=1`, deixa de falar de dinheiro (sem aviso duplicado no Telegram).
- (−) Agenda financeira degradada (item 7 acima).
- (−) O finance não tem nome próprio no Tailscale: usa portas da máquina do brain (8444 e 8445).

## Fora de escopo

Coletor e digestão (etapa 3), integração com o `esper-brain`, Linear e qualquer funcionalidade financeira nova.
