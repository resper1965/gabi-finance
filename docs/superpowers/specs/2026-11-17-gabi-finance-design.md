# gabi-finance · Desenho (2026-11-17)

Etapa 2 do desenho `esper-brain` (`resper1965/esper-brain`, `docs/superpowers/specs/2026-11-17-esper-brain-design.md`): quebrar o `gabi-brain` e tirar dele o financeiro, que precisa de banco, contas exatas e conciliação — o resto vai para o markdown.

## Objetivo

Um serviço só de dinheiro: extratos e saldos (mcp.ai), conciliação, compromissos e A pagar, projeção de caixa, gastos por pessoa, assinaturas, despesas por empresa, notas fiscais e a receber (Nibo), com painel financeiro e MCP para o Hermes. Ao fim da virada o `gabi-brain` não lê mais dinheiro.

## Decisões

| # | Decisão |
|---|---|
| F1 | Repositório `resper1965/gabi-finance`, nascido com o histórico inteiro do `gabi-brain` a partir de `backup-vps-2026-11-17` (`0422aad`, o código que roda em produção, com a ADR-038 e a migração 0089). O corte é feito aqui; o `gabi-brain` não muda até a virada. |
| F2 | **Painel mantido, só financeiro**: Caixa (A pagar, Projeção, Semanas, Resumo), Cobrar (A receber, Notas), Gastos (Lançamentos, Cartões, Parcelas, Assinaturas, Para onde vai), Cadastros de Despesas, Cobrança e Equivalências, Regras, Gabi › Agentes (emitir o token do Hermes). Atrás do Tailscale, como hoje. |
| F3 | **Banco = cópia da produção** + migração que apaga as tabelas não financeiras. Ids, histórico, regras e decisões de "para quem" ficam. |
| F4 | **Troca direta**, com uma conferência lado a lado na hora (saldos, A pagar do mês, projeção) e volta em um passo (religar timers do `gabi-brain` e restaurar o `config.yaml` do Hermes). |
| F5 | **Ponte própria** (único processo com rede e token, regra R5): só o Nibo. O mcp.ai segue como em produção hoje: as units de extratos e saldos chamam o mcp.ai com `MCPAI_KEY` no próprio ambiente (`/etc/gabi-finance/`). *(ajustado no corte: mudar isso alteraria o fluxo financeiro)* |
| F6 | **Pessoas ficam**: tabela `pessoa` (id, nome, papel), `conta.usuarios` (portadores dos cartões), `gastador_regra` e "para quem". Esposa e filhas têm cartão da conta do Ricardo: o portador único preenche o gastador sozinho. Ficha da família, documentos, pets e bens saem (estão no `esper-brain`). |
| F7 | **Avisos só financeiros** no Telegram: vence em breve, valor diferente, débito automático, saldo divergente, bancos desatualizados. Resumo da manhã financeiro às 07:05 (bloco "dinheiro" de hoje). O `gabi-brain` perde o bloco de dinheiro do resumo dele até a etapa 3 juntar tudo no `hot.md`. |
| F8 | **MCP** com nome de servidor `gabi_finance` e os **mesmos nomes de ferramenta** das financeiras de hoje; o SOUL e o include do Hermes trocam o prefixo `mcp__gabi_brain__` por `mcp__gabi_finance__` só nelas. `tools/auditar_promessas.py` acompanha. |
| F9 | **VPS**: usuário `gabifinance`, código `/opt/gabi-finance`, banco e bruto `/var/lib/gabi-finance`, backups `/var/backups/gabi-finance`, segredos `/etc/gabi-finance/`, socket `/run/gabi-finance/api.sock`, host no Tailscale `gabi-finance.tail985643.ts.net`, units `gabi-finance-*`. Instalação: o Ricardo roda, o Claude guia. |

## O que fica e o que sai

**Fica:** `gabi/dinheiro`, `gabi/cobrar`, `gabi/decisoes.py` (canal de decisões financeiras), base (`db`, `rodada`, `bruto`, `envelope`, `identidade`, `acesso`, `agentes`, `backup`, `exportacao`, `mascara`, `hoje`, `api`), `avisos.py` e `telegram.py` reduzidos ao financeiro, `dia.py` reduzido ao bloco dinheiro, `gabi/fontes` com `mcpai`, `nibo`, `ponte`, `servico`, `roteador`, `ambiente`, `_http`, `tokens`, MCP (`servidor`, `tokens` e as ferramentas financeiras), rotas `dinheiro`, `cobrar`, `gastos`, `despesas`, `cadastros` (parte financeira), `decisoes`, `avisos`, `agentes`, `contagens` (se usada pelas telas que ficam).

**Sai:** `agenda`, `correio`, `teams`, `contatos`, `envios`, `familia`, `documentos`, `projetos`, `atividades`, `anexos`, `antecipar`, `reuniao`, `revisao`, `transcricao`, `visao_pdf`, `importar` (se só servir à família), `qualidade` (se não for financeira), fontes Google, Graph, Linear, Paperless, OpenRouter, `nibo_escrita` (se não for usada), telas Trabalho, Projetos, Atividades, Envios, Contatos e Cadastros não financeiros, units de agenda, anexos, contatos, correio, documentos, teams.

Regra para os "se": o corte segue o grafo de imports a partir do que fica; o que nada que fica importa, sai. Casos duvidosos viram decisão no plano, não suposição.

## Banco

Migração nova (próximo número livre após 0089) que faz `drop table` das tabelas que nenhum módulo que fica usa — a lista sai do grafo do corte e é conferida contra `sqlite_master` de um banco migrado. A mesma migração roda nos testes (banco-modelo) e na cópia da produção.

## Virada (resumo; o roteiro exato vai no plano)

1. Instalar `gabi-finance` (usuário, pastas, venv, units desligadas).
2. Parar os timers financeiros do `gabi-brain` (extratos, saldos, notas); cópia fresca do banco (`.backup`) para `/var/lib/gabi-finance/` e migrar.
3. Mover os tokens do mcp.ai e do Nibo (novo) para `/etc/gabi-finance/`.
4. Subir ponte, API, MCP e timers do `gabi-finance`; rodar uma rodada de extratos e de saldos.
5. **Conferência**: saldos por conta, total A pagar do mês e projeção de 30 dias nos dois (o `gabi-brain` ainda lendo a cópia de antes) — têm que bater.
6. Hermes: backup do `config.yaml`, trocar o MCP financeiro para `gabi_finance`, SOUL novo, `/new` nos dois canais.
7. Desligar (sem remover) no `gabi-brain`: timers de extratos, saldos e notas e o bloco de dinheiro do resumo.

**Volta:** religar os timers do `gabi-brain`, restaurar o `config.yaml`, `/new`.

## Pré-requisitos do Ricardo

- Token novo da API do Nibo (o atual expirou; notas paradas desde ao menos 09/11).
- Rodar os comandos da virada na VPS.

## Testes

A suíte do `gabi-brain` (~3.200 testes) é a rede: cada módulo que sai leva os seus testes; o que fica tem que continuar verde. Testes novos: a migração de corte (tabelas que somem e que ficam), o resumo financeiro e os avisos só financeiros, o MCP só com ferramentas financeiras.

## Fora de escopo

Coletor e digestão (etapa 3), integração com o `esper-brain`, Linear, qualquer funcionalidade financeira nova.
