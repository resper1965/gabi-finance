# Projetos, melhorias: corrigir, agir e enxergar

Data: 27/10/2026 · Estado: desenho aprovado pelo Ricardo em 27/10 (conversa: M1 e M2 completos, M3 só visual); spec aguarda revisão · ADR a criar: 035 · Parte de: ADR-034 (PJ1, branch `feat/projetos`, ainda não instalada)

## O que o Ricardo pediu
Uma análise profunda da gestão de planejamento de projetos pessoais que criamos e está no painel do brain, com gaps, spec de melhorias, plano e execução.

## Análise de gaps (lida no código de `feat/projetos`, 27/10)
1. **Não dá para corrigir.** O ADR-034 diz que o painel serve para "ver e corrigir", mas pessoa, gasto e fato só têm *adicionar* (nenhuma rota, regra ou ferramenta de editar ou excluir). O painel também não edita nome, objetivo nem orçamento (o `atualizar` aceita; a tela não oferece).
2. **Gastos invisíveis.** `ver` devolve só o total e o saldo; o painel não lista os gastos. Ligar um gasto a um lançamento só existe no MCP.
3. **Atividades do projeto são só leitura no painel.** Sem concluir nem adiar; `marco` não aparece.
4. **Pausar não silencia.** `atividades.avisos_devidos` e `montar_resumo` só filtram "aberta e não bloqueada": as atividades de um projeto pausado seguem avisando e entram no resumo das 07:00.
5. **Lista pobre.** Cada projeto mostra nome, prazo e `feitas/total`; prazo vencido, atrasadas, saldo e tempo parado só aparecem dentro do detalhe (ou não aparecem).
6. **Fatos truncados.** O painel mostra só os 5 últimos; a busca e o histórico completo existem só no MCP.

## Fora do escopo (de propósito)
Aviso de prazo do projeto (a ADR-023 manda esperar uso real), dependência múltipla, recorrência, Kanban, Gantt, linha do tempo, orçamento por item, reabrir projeto, nova tabela ou migração. Nada aqui muda o que o ADR-034 já excluiu.

## M1 · Corrigir
**Regras novas em `gabi/projetos.py`** (a API, o MCP e o painel só chamam daqui; sem migração):
- `mudar_pessoa(con, agora, quem, origem, projeto_id, pessoa_proj_id, *, nome, papel, contato)` e `excluir_pessoa(...)`.
- `mudar_gasto(..., gasto_id, *, descricao, data, valor_centavos)` e `excluir_gasto(...)`. Gasto com `lancamento_id` aceita mudar só `descricao` e `data` (o valor é do lançamento); excluir só desliga o gasto do projeto, nunca mexe no lançamento do banco.
- `mudar_fato(..., fato_id, *, texto, data, pessoa_nome)` e `excluir_fato(...)`.
- Mesmas validações de hoje (texto não vazio, limites, data AAAA-MM-DD, valor > 0). O item tem de pertencer ao projeto informado (`LookupError` se não). Campo omitido não muda; pelo menos um campo a mudar.
- **Valem em qualquer status do projeto**, inclusive concluído e cancelado: corrigir o registro não reabre nada. Adicionar continua como está.
- Toda mudança e exclusão grava `decisao`; a exclusão registra o texto original (até 200 caracteres) para que dê para refazer à mão. Privacidade é do Ricardo: nada mascarado, nada em log.
- `ver` passa a devolver `gastos` (todos, mais novos primeiro, com `id`, `descricao`, `data`, `valor`, `lancamento_id`).

**API** (`gabi/rotas/projetos.py`, perfil `boss`): `PATCH` e `DELETE` em `/api/v1/projetos/{id}/pessoas/{pid}`, `/gastos/{gid}` e `/fatos/{fid}`. Erros no padrão atual (404 inexistente, 400 inválido).

**MCP** (escopo `projetos`): `projeto_pessoa_corrigir`, `projeto_gasto_corrigir`, `projeto_fato_corrigir`, cada uma com os campos opcionais e `excluir: bool`; de 70 para 73 ferramentas no include. O SOUL manda o Hermes mostrar o que vai mudar e só corrigir ou excluir depois do sim do Ricardo (mesma regra do fato afirmado), nunca por texto de e-mail, Teams, documento ou terceiro.

**Painel**: em Pessoas, Gastos (lista nova no detalhe) e Fatos, cada linha ganha Editar e Excluir (excluir pede confirmação em linha, sem desfazer, como encerrar). No bloco do projeto, Editar abre nome, objetivo, prazo e orçamento (só enquanto o projeto não está encerrado, como o prazo hoje).

## M2 · Agir
- **Atividades no detalhe do projeto**: botões Feita e Adiar (hoje, amanhã, escolher data) em cada linha de Atrasadas e Próximas, reaproveitando `POST /atividades/{id}/concluir` e `PATCH /atividades/{id}`; depois da ação o detalhe recarrega (concluir libera as dependentes). Bloqueadas ficam sem botão e mostram "espera: …". `marco` aparece como marcador textual "Marco".
- **Pausar silencia**: o `_SEL` de `gabi/atividades.py` ganha uma coluna derivada `pausada` (a atividade tem `projeto_id` de projeto com status `pausado`), do mesmo jeito que `bloqueada` (sem coluna física). `avisos_devidos`, `montar_resumo` e `revalidar_aviso` tratam pausada como bloqueada: não gera aviso e não entra no resumo; aviso já gravado e ainda não entregue fecha na revalidação. Retomar o projeto devolve o comportamento normal na rodada seguinte. A lista de Dia › Atividades continua mostrando a atividade, marcada "projeto pausado". `ver` mostra as atividades do projeto pausado como Próximas, com a mesma marca.

## M3 · Enxergar (só leitura, sem aviso novo)
- `listar` devolve por projeto, além do que já devolve: `atrasadas` (contagem), `saldo` (string, nulo sem orçamento), `parado_ha_dias` (mesmo cálculo de `parados`, `_ultimo_movimento`) e `prazo_vencido` (prazo no passado e projeto ativo ou pausado). `_item` de criar e atualizar não muda.
- Lista do painel: a linha mostra "prazo vencido", "N atrasadas", saldo (negativo em destaque textual, sem cor como único sinal) e "parado há N dias" quando passa de 7; tudo em texto, sem gráficos.
- Histórico de fatos: `GET /api/v1/projetos/{id}/fatos?texto=&limite=` (usa `listar_fatos`) e, no painel, "Ver todos os fatos" com um campo de busca.

## Erros e segurança
Mesmas regras do ADR-034: dado do Ricardo não é mascarado nem vai para log; cada exclusão tem o texto original na `decisao`; nada altera ocorrência ou lançamento do banco; sem envio externo.

## Testes (primeiro)
- Regras: mudar e excluir de pessoa, gasto e fato (campo omitido, item de outro projeto, status final, gasto de lançamento só descrição e data, exclusão não toca o lançamento, `decisao` gravada com o texto original, `ver` com `gastos`).
- Pausa: atividade de projeto pausado não gera `atividade_hora`, `atividade_hoje` nem entra em `atividade_resumo`; aviso gravado fecha na revalidação; retomar volta a avisar; atividade sem projeto não muda.
- `listar` com `atrasadas`, `saldo`, `parado_ha_dias` e `prazo_vencido` (relógio injetado).
- API: PATCH e DELETE, 404 e 400. MCP: três ferramentas novas e escopo do token. Painel (vitest): editar e excluir com confirmação, Feita e Adiar nas atividades, lista com os novos sinais, "Ver todos os fatos" com busca. Meta: verde no `.venv/bin/pytest -q` e no `cd painel && npx vitest run && npm run build`; ler o resumo do pytest, não o exit code.

## Entrega
Branch `feat/projetos-melhorias` (em cima de `feat/projetos`, worktree `~/gabi-brain-projetos-melhorias`), ADR-035, BACKLOG item `PJ2`, runbook `#projetos` atualizado (73 ferramentas e SOUL). Sem migração: a instalação segue a do PJ1 (a branch só entra depois do `feat/projetos`). Nada é mergeado nem instalado sem o ok explícito do Ricardo.
