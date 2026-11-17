# Costuras do corte

Gerado por `python -m tools.grafo_imports --fica <lista do plano> gabi.importar --sai <lista do spec>`.
O fecho puro dos imports a partir do que fica arrasta quase tudo (`api`, `avisos`, `dia` e `mcp.servidor` importam as áreas que saem), então
`--sai` declara os prefixos que o spec manda embora; cada aresta de um módulo que fica para um deles é uma costura. Os módulos que saem
estão em `saem.txt` (um por linha). As Tasks 2–5 executam as ações abaixo; os testes dos módulos que saem são apagados na Task 5, não antes.

## Decisões que o spec não fecha

| Módulo | Decisão | Motivo |
|---|---|---|
| `gabi.importar` | FICA | Carga do staging do Plano 1 (planilha, lançamentos, cadastros de compromissos): só usa `db`, `dinheiro`, `rodada`, `hoje`. É financeiro; o spec só o manda embora se servisse só à família, e não serve. Seu teste (`tests/test_importar.py`) é financeiro e não pode ser apagado. |
| `gabi.qualidade` + `rotas.qualidade` | SAI | EV5 mede aceite de sugestões, custo do modelo (OpenRouter) e latência de ferramentas do MCP; não lê tabela financeira e só `rotas.qualidade` a importa. |
| `gabi.fontes.nibo_escrita` | FICA | `ambiente.fontes_do_ambiente()` ainda instancia `NiboEscrita` como a fonte `nibo` (leitura de notas e a receber) e `tests/cobrar/test_nibo*.py` a cobrem; a ponte só permite os métodos de leitura (R2). Trocar por `Nibo` seria mudar comportamento financeiro. |
| `gabi.fontes.tokens` | SAI | Só emite tokens de Google, Graph e Linear (`token_google_*`, `token_graph`, `linear_do_ambiente`); nada que fica a importa (só `tests/fontes/test_tokens.py`). mcp.ai e Nibo usam variável de ambiente. O spec o listava em "fica" por engano de nome (o `gabi.mcp.tokens`, dos escopos do MCP, é outro e fica). |
| `gabi.rotas.dia` | SAI | Telas Hoje e Agenda; o `dia.py` que fica só alimenta o resumo financeiro. Fora da lista de rotas do spec (F2). |
| `gabi.rotas.cadastros` | FICA, reduzir na Task 3 | Rota mista; não importa módulo que sai (sem costura no grafo), mas expõe cadastros não financeiros por dentro. |
| `gabi.mcp.ferramentas_{atividades,documentos,envios,familia,projetos}` | SAEM inteiros | Só têm ferramentas de áreas que saem. |
| `gabi.mcp.ferramentas_{agir,assistente,dec,prop,ver,dia}` | FICAM, reduzidos na Task 3 | Mistos: só as ferramentas não financeiras saem. `ferramentas_despesas` é financeiro e fica inteiro. |
| `tools/*` (`carga_familia`, `comparar_agenda`, `obter_token_google`, `obter_token_teams`, `sonda_teams_ness`, `gerar_docs_api`, ...) | Fora desta etapa | Task 5 e seguintes; não importados por `gabi/`. |

## Costuras (módulo que fica -> importa algo que sai)

| Módulo que fica | Importa | Arquivo:linha | O que fazer |
|---|---|---|---|
| `gabi.api` | `rotas.agenda`, `atividades`, `contatos`, `correio`, `dia`, `documentos`, `envios`, `familia`, `projetos`, `qualidade`, `teams` | `gabi/api.py:167-198` | Remover o uso: tirar os `include_router` (Task 3). Os motivos estão acima. |
| `gabi.avisos` | `agenda`, `agenda.consulta`, `agenda.convites` | `gabi/avisos.py:16-17` | Remover o uso: avisos de convite e de agenda saem (F7: só avisos financeiros). |
| `gabi.avisos` | `atividades`, `projetos` | `gabi/avisos.py:15` | Remover o uso: avisos de atividade e projeto saem. |
| `gabi.avisos` | `documentos.repositorio` | `gabi/avisos.py:324,330,351` | Remover o uso: aviso `documento_vence` sai (documentos vão para o esper-brain). |
| `gabi.avisos` | `teams`, `teams.regra` | `gabi/avisos.py:120,266` | Remover o uso: aviso `teams_sem_resposta` sai. |
| `gabi.decisoes` | `contatos.telefone` | `gabi/decisoes.py:75` | Trazer a função (`normalizar_telefone`) para o módulo, como privada (Task 2). |
| `gabi.decisoes` | `correio.regras` | `gabi/decisoes.py:74` | Trazer a função (`endereco`) para o módulo, como privada (Task 2). |
| `gabi.dia` | `agenda`, `agenda.consulta`, `correio`, `correio.consulta` | `gabi/dia.py:5-6` | Remover o uso: `dia.py` fica só com o bloco `dinheiro` (F7); agenda e e-mail saem. |
| `gabi.fontes.ambiente` | `graph_ness`, `paperless` | `gabi/fontes/ambiente.py:6-7` | Remover o uso: fábricas só `nibo` e `mcpai` (Task 2). |
| `gabi.fontes.ponte` | `google_agenda`, `google_contatos`, `google_email`, `google_oauth`, `graph_ness`, `openrouter`, `paperless` | `gabi/fontes/ponte.py:13-20` | Remover o uso: `PonteAgenda`, `PonteEmail`, `PonteGraph`, `PonteModelo` e as entradas de `PERMITIDOS`/`ERROS` que não são `nibo`/`mcpai` (Task 2). |
| `gabi.fontes.roteador` | `google_oauth`, `graph_ness` | `gabi/fontes/roteador.py:4,64` | Remover o uso: só `nibo` e `mcpai` roteiam; as demais caem em fonte desconhecida (Task 2). |
| `gabi.fontes.servico` | `google_agenda`, `google_contatos`, `google_email`, `graph_ness`, `openrouter` | `gabi/fontes/servico.py:7-11` | Remover o uso: o serviço de fontes monta só `nibo` e `mcpai` (Task 2). |
| `gabi.fontes.tokens` | `google`, `graph`, `linear` | `gabi/fontes/tokens.py:16,17,107` | O módulo que fica sai também (ver decisão acima); `saem.txt`, apagado na Task 5 com `tests/fontes/test_tokens.py`. |
| `gabi.mcp.ferramentas_agir` | `correio`, `correio.fontes`, `correio.lixeira` | `gabi/mcp/ferramentas_agir.py:8` | Remover o uso: ferramentas de e-mail (lixeira etc.) saem; ficam as de `receber_manual`, `gastador`, `nao_gasto` (Task 3). |
| `gabi.mcp.ferramentas_assistente` | `antecipar`, `reuniao`, `revisao`, `google_oauth`, `graph_ness` | `gabi/mcp/ferramentas_assistente.py:5-7` | Remover o uso das ferramentas que dependem deles; conferir na Task 3 o que sobra financeiro (se nada, o módulo sai). |
| `gabi.mcp.ferramentas_dia` | `agenda`, `antecipar`, `correio`, `google_oauth`, `graph_ness` | `gabi/mcp/ferramentas_dia.py:6-12` | Remover o uso: agenda e e-mail saem; fica o resumo financeiro e `_inteiro`/`AVISO_TERCEIROS` se algo que fica os usa (Task 3). |
| `gabi.mcp.ferramentas_prop` | `fontes.paperless` | `gabi/mcp/ferramentas_prop.py:8` | Remover o uso: ferramentas de proposta de documento saem; `ErroFerramenta` e as propostas financeiras ficam (Task 3). |
| `gabi.mcp.ferramentas_ver` | `contatos.contatos` | `gabi/mcp/ferramentas_ver.py:13` | Remover o uso: ferramentas de contato saem (Task 3). |
| `gabi.mcp.ferramentas_ver` | `teams.regra` | `gabi/mcp/ferramentas_ver.py:17` | Remover o uso: ferramentas ligadas a Teams saem (Task 3). |
| `gabi.mcp.servidor` | `ferramentas_atividades`, `ferramentas_documentos`, `ferramentas_envios`, `ferramentas_familia`, `ferramentas_projetos` | `gabi/mcp/servidor.py:24` | Remover o uso: deixam de ser registradas (Task 3). |
| `gabi.mcp.servidor` | `fontes.graph_ness` | `gabi/mcp/servidor.py:280` | Remover o uso: sem `PonteGraph` nem `ErroGraphNess` (Tasks 2-3). |
