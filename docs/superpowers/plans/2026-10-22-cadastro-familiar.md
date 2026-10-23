# Cadastro familiar, consulta documental e confiabilidade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** o Hermes consulta e mantém as fichas da família e seus documentos, lê o OCR do Paperless com referência e diz "não encontrei" em vez de inventar.

**Architecture:** domínio novo em `gabi/familia/` (fichas, contato, documentos) sobre a `pessoa` existente e três tabelas novas (0077). Cinco ferramentas MCP no escopo `familia`, rotas `/api/v1/familia`, aba Família no painel e carga inicial sem modelo. Parte B: método `texto` do Paperless na ponte, trecho na busca e `documentos_texto`. Parte C: vazio explícito no `executar` do MCP e SOUL do Hermes versionado.

**Tech Stack:** Python 3, SQLite, FastAPI, MCP, React + vitest. Testes: `.venv/bin/python -m pytest -q`; painel: `cd painel && npx vitest run && npm run build`.

**Spec:** `docs/superpowers/specs/2026-10-22-cadastro-familiar-design.md` · ADR `docs/adr/025-cadastro-familiar.md`

## Global Constraints
- Número de documento nunca entra em log, stderr, `decisao`, mensagem de erro ou resposta de ferramenta que não seja `familia_consultar` ou a tela Família.
- Erros com códigos fixos: `pessoa_ambigua`, `campo_invalido`, `valor_invalido`, `conflito`, `nao_encontrado`, `requisicao_invalida`.
- Auditoria em `decisao` com `origem='familia'`, só com id da pessoa, campo e tipo.
- Campos de contato graváveis: `apelido`, `parentesco`, `nascimento` (texto ou data `YYYY-MM-DD`); `telefones`, `emails`, `enderecos` (listas, até 10 itens; texto até 200 caracteres).
- Tipos de documento: `cpf`, `rg`, `cnh`, `passaporte`, `outro`; `pais` ISO-2 com padrão `BR`; datas `YYYY-MM-DD`; número de 1 a 40 caracteres.
- `normalizar_nome` vem de `gabi.envios.propostas` (reutilizar, não duplicar); telefone por `gabi.contatos.telefone.normalizar_telefone`.
- Esquema novo = migração `0077`. Código e comentários em pt-BR, no estilo vizinho. Nomes: "Gabi" é o projeto, "o brain" é a app, "Hermes" é o agente.
- Commit com a linha Co-Authored-By do modelo que fez o trabalho. Sem push, merge ou instalação dentro das tarefas.

## Review Focus
1. Pessoa com o mesmo primeiro nome de outra ("Ana" × "Ana Paula"): casa só por igualdade do nome inteiro, nome completo ou apelido normalizado; senão `pessoa_ambigua` com candidatos (Task 2).
2. Desfazer depois que o valor mudou de novo: `conflito`, nada é sobrescrito (Task 3).
3. Proposta do mesmo número de um documento já ativo com datas diferentes: vira atualização daquele documento, não um duplicado (Task 4).
4. OCR com CPF com DV inválido ou data "01/02/2030" (ambígua dd/mm × mm/dd): entra como proposta `conferir=1`; datas são lidas como dd/mm (padrão BR) (Task 10).
5. Ferramenta que devolve `itens: []` dentro de um objeto maior, com outras chaves: o aviso de vazio entra sem apagar as outras chaves (Task 9).

---

### Task 1: Migração 0077 com cópia dos documentos legados
**Files:** Create `migrations/0077_familia.sql`; Test `tests/familia/__init__.py`, `tests/familia/test_migracao.py`
**Produces:** tabelas `pessoa_documento`, `pessoa_historico`, `pessoa_proposta` com as colunas da spec (seção "Dados: migração 0077"), checks de `tipo`, `origem` e `estado`, índices `pessoa_documento(pessoa_id)`, `pessoa_documento(validade)` e o índice único das propostas abertas `(pessoa_id, tipo, numero) where estado='pendente'`.
- [ ] Testes que falham:
  - `test_copia_documentos_legados`: uma pessoa com `dados.documentos=[{"tipo":"CPF","numero":"123"},{"tipo":"Passaporte","numero":"AB1","emissor":"PF"},{"tipo":"Título","numero":"9"}]`, depois de migrar, tem 3 linhas `origem='legado'` com `tipo` igual a `cpf`, `passaporte` e `outro`, `pais='BR'`, e `dados` inalterado.
  - `test_pessoa_excluida_nao_copia`.
  - `test_checks` (tipo inválido é recusado).
- [ ] Rodar e ver falhar.
- [ ] Implementar a cópia com `json_each(pessoa.dados, '$.documentos')`, normalizando `tipo` em SQL: `lower`, mais `replace` de acentos para os conhecidos; desconhecido vira `outro`. A pessoa da migração usa o mesmo banco-modelo da `conftest`. Se a cópia for difícil em SQL puro, a 0077 cria só o esquema e a cópia vira `gabi/familia/migrar_legado.py`, chamada uma vez pelo instalador, com teste equivalente.
- [ ] Rodar `.venv/bin/python -m pytest tests/familia tests/test_esquema.py tests/test_db.py -q`. Esperado: passa.
- [ ] Commit `feat(familia): tabelas de documentos, histórico e propostas (0077)`.

### Task 2: Fichas (listar, ficha, resolver, vencimentos, auditoria, divergências)
**Files:** Create `gabi/familia/__init__.py`, `gabi/familia/fichas.py`; Test `tests/familia/test_fichas.py`
**Produces:**
- `class ErroFamilia(Exception)` com `codigo`, `mensagem`, `candidatos`.
- `listar(con) -> list[dict]`: `{id, nome, apelido, parentesco, nascimento, documentos_qtd}`.
- `ficha(con, pessoa_id) -> dict`: `{id, nome, nome_completo, apelido, parentesco, nascimento, telefones, emails, enderecos, documentos:[{id,tipo,pais,numero,emissor,emissao,validade,paperless_id,origem,atualizado_em}], divergencias:[{documento_id, tipo, campos:[...]}]}`. `telefones` junta `dados.telefone` e `dados.telefones`; `emails` faz o mesmo com `email` e `emails`, sem repetir.
- `resolver_pessoa(con, texto) -> str` (id).
- `vencimentos(con, hoje: date, meses: int) -> list[dict]`: `{pessoa_id, nome, tipo, pais, validade, vencido: bool}`, sem número, ordenado por validade.
- `auditar_leitura(con, pessoa_id, tipos, quem, agora)`.
- [ ] Testes que falham:
  - `listar` não traz número.
  - `ficha` traz os dois passaportes (BR e PT) com origem.
  - Uma proposta pendente com validade diferente do documento ativo aparece em `divergencias` com `campos == ["validade"]`.
  - `resolver_pessoa("ana")` com "Ana" e "Ana Paula" no banco dá o id de "Ana"; `"ana p"` dá `pessoa_ambigua`, com `candidatos` vazio se ninguém casar.
  - Apelido casa.
  - `vencimentos(hoje, 6)` inclui o que vence em 5 meses e o vencido há 10 dias, e exclui o vencido há 40 dias e o que vence em 7 meses.
  - O texto de `auditar_leitura` não contém o número.
- [ ] Rodar e ver falhar. [ ] Implementar. [ ] Rodar `tests/familia`. [ ] Commit `feat(familia): fichas, vencimentos e auditoria de leitura`.

### Task 3: Contato gravado direto, com histórico e desfazer
**Files:** Create `gabi/familia/contato.py`; Test `tests/familia/test_contato.py`
**Consumes:** Task 2 (`ErroFamilia`).
**Produces:**
- `atualizar(con, pessoa_id, campo, acao, valor, quem, agora) -> {"antes", "depois", "historico_id"}`. `acao` ∈ `definir` | `adicionar` | `remover`; listas só aceitam `adicionar`/`remover`, e textos ou datas só `definir`.
- `desfazer(con, historico_id, quem, agora) -> dict`.
- `historico(con, pessoa_id=None, limite=50) -> list[dict]`.
- [ ] Testes que falham:
  - `adicionar` telefone "(11) 98888-7777" grava `+5511988887777` em `dados.telefones` e cria o histórico.
  - Telefone inválido dá `valor_invalido`, e e-mail inválido idem.
  - Campo fora da lista dá `campo_invalido`.
  - `remover` de um valor ausente dá `valor_invalido`.
  - O 11º item dá `valor_invalido`.
  - `desfazer` restaura e marca `desfeito_em`.
  - Desfazer depois de outra mudança no mesmo campo dá `conflito` (Review Focus 2).
  - A auditoria não contém o valor.
- [ ] Rodar e ver falhar. [ ] Implementar com `transacao(con)`. [ ] Rodar. [ ] Commit `feat(familia): contato com histórico e desfazer`.

### Task 4: Propostas de documento
**Files:** Create `gabi/familia/documentos.py`; Test `tests/familia/test_documentos.py`
**Consumes:** Tasks 1–2.
**Produces:**
- `propor(con, pessoa_id, *, tipo, numero, emissor=None, emissao=None, validade=None, pais="BR", paperless_id=None, origem, conferir=False, agora) -> int | None`. Devolve None quando o documento já existe idêntico.
- `decidir(con, proposta_id, estado, quem, agora)`.
- `listar_propostas(con, estado="pendente") -> list[dict]`, com `atual` (o documento ativo, ou None) e `proposto`.
- [ ] Testes que falham:
  - CPF com DV inválido entra com `conferir=1`; CPF válido entra com `conferir=0`.
  - Data fora de ISO dá `valor_invalido`.
  - Proposta idêntica a um documento ativo devolve None.
  - Mesmo número com validade nova vira proposta com `documento_id` do ativo, e aprovar atualiza a linha sem criar outra (Review Focus 3).
  - Aprovar um documento novo cria a linha com `origem` igual a `ricardo` (vindo do Hermes) ou `carga`.
  - Recusar não muda nada.
  - Decidir duas vezes dá `conflito`.
  - Propostas abertas repetidas dão None ou a de antes, sem violar o índice.
- [ ] Rodar e ver falhar. [ ] Implementar. [ ] Rodar. [ ] Commit `feat(familia): propostas de documento com aprovação`.

### Task 5: API `/api/v1/familia` e a rota antiga do CPF
**Files:** Create `gabi/rotas/familia.py`; Modify `gabi/api.py`, `gabi/rotas/cadastros.py` (a rota `/pessoas/{pid}/cpf` lê `pessoa_documento`, mascarada com `gabi.mascara.mascarar_documento`), `docs/openapi.json` e `docs/api.md` (regerar); Test `tests/rotas/test_familia.py`
**Consumes:** Tasks 2–4.
**Produces:** as rotas da spec (seção "API"), só boss. `ErroFamilia` é mapeado assim: `nao_encontrado` dá 404, `conflito` dá 409 e os demais dão 400 com o código.
- [ ] Testes que falham: cada rota com status e forma; não boss dá 403; `/cpf` mascarado a partir da tabela.
- [ ] Rodar e ver falhar. [ ] Implementar e regerar os docs (`tools/gerar_docs_api.py`). [ ] Rodar `tests/rotas tests/test_docs_api.py tests/test_matriz_acesso.py -q`. [ ] Commit `feat(api): rotas da família`.

### Task 6: Ferramentas MCP do escopo `familia`
**Files:** Create `gabi/mcp/ferramentas_familia.py`; Modify `gabi/mcp/servidor.py` (registro, `ESCOPOS_FERRAMENTAS`, `ESCOPOS_HERMES += "familia"`), `gabi/mcp/tokens.py` (`ESCOPOS += "familia"`), `tests/mcp/test_servidor.py` (lista exata 25), `tests/mcp/test_tokens.py`, `docs/fontes/hermes.md` (`python -m tools.gerar_hermes`, mais a frase dos escopos), `docs/api.md` se o teste de docs exigir; Test `tests/mcp/test_familia.py`
**Consumes:** Tasks 2–4.
**Produces:** `familia_listar()`, `familia_consultar(pessoa: str)`, `familia_vencimentos(meses: int = 12)`, `familia_atualizar_contato(pessoa: str, campo: str, acao: str, valor: str)`, `familia_propor_documento(pessoa, tipo, numero, emissor="", emissao="", validade="", pais="BR", paperless_id=0)`.
- `pessoa` é resolvida por `resolver_pessoa`; os candidatos vão na mensagem.
- `familia_consultar` chama `auditar_leitura` com quem `hermes`.
- `familia_propor_documento` usa origem `hermes`, e na tabela fica `origem='ricardo'` ao aprovar. Devolve o `link` (`painel.url` + `#cadastros`).
- As docstrings seguem a spec, inclusive "dado de terceiros" e "nunca em resumos".
- [ ] Testes que falham: cada ferramenta; sem escopo dá `sem_escopo`; lista exata de 25; `familia_listar` e `familia_vencimentos` não trazem número; a auditoria existe após `familia_consultar`.
- [ ] Rodar e ver falhar. [ ] Implementar e regerar `hermes.md`. [ ] Rodar `tests/mcp tests/test_docs_api.py -q`. [ ] Commit `feat(mcp): ferramentas da família`.

### Task 7: Painel, aba Família
**Files:** Create `painel/src/telas/CadastrosFamilia.tsx`; Modify `painel/src/navegacao.ts` (aba `["familia", "Família", "Quem é a família e quais documentos vencem?"]` em Cadastros, logo depois de `cadastros`), `painel/src/App.tsx` (render); Test `painel/tests/familia.test.tsx`
**Consumes:** Task 5. Seguir `ContatosPropostas.tsx` e `Envios.tsx`.
- [ ] Testes que falham:
  - A ficha mostra contato e documentos com número e validade; o que vence em até 6 meses ganha destaque.
  - A proposta mostra o atual e o proposto, e Aprovar faz `POST .../decisao {"estado":"aprovada"}`; a etiqueta "conferir" aparece.
  - O Desfazer chama `/historico/{id}/desfazer`.
  - O link do Paperless aparece quando existe `paperless_id`, usando `paperless.url` se vier na ficha; senão mostra só o id.
- [ ] Rodar e ver falhar. [ ] Implementar. [ ] Rodar `cd painel && npx vitest run && npm run build`. [ ] Commit `feat(painel): aba Família`.

### Task 8: Parte B, OCR do Paperless no MCP
**Files:** Modify `gabi/fontes/ponte.py` (`PERMITIDOS["paperless"] += "texto"`), `gabi/mcp/ferramentas_prop.py` (`documentos_buscar` com `trecho` e `referencia`; nova `documentos_texto`, escopo `docs`), `tests/mcp/test_servidor.py` (lista exata 26), `docs/fontes/hermes.md`, `docs/fontes/paperless.md` (reescrito para busca, baixar e texto); Test `tests/mcp/test_propostas.py` (ou um arquivo novo `tests/mcp/test_documentos.py`), `tests/fontes/test_ponte.py`
**Produces:**
- `documentos_buscar` → `itens:[{id, titulo, criado_em, trecho, referencia:{paperless_id,titulo,criado_em}}]`. O `trecho` vem do `content` do resultado da busca: até 300 caracteres centrados na primeira ocorrência, sem diferença de caixa, ou os primeiros 300.
- `documentos_texto(id: int, limite: int = 8000) -> {texto, cortado: bool, referencia}`, com `limite` entre 1 e 20000.
- [ ] Testes que falham: trecho centrado; trecho do começo quando o termo não aparece; `documentos_texto` corta e marca `cortado`; Paperless fora do ar dá `fonte_indisponivel`; a ponte permite `texto`; lista exata de 26.
- [ ] Rodar e ver falhar. [ ] Implementar e reescrever `paperless.md`. [ ] Rodar `tests/mcp tests/fontes -q`. [ ] Commit `feat(mcp): trecho e texto do OCR do Paperless`.

### Task 9: Parte C, confiabilidade
**Files:** Modify `gabi/mcp/servidor.py` (`executar` acrescenta `vazio` e `aviso` quando o resultado é dict com `itens == []`); Create `deploy/hermes/SOUL.md` (a partir do atual `~/.hermes/SOUL.md`, com as mudanças da spec, seção "Parte C"), `deploy/instalar-hermes-soul.sh` (copia com backup `~/.hermes/SOUL.md.bak-$(date +%F-%H%M)`, como o usuário `ricardo`, e imprime o lembrete `sudo systemctl restart hermes-gateway`); Test `tests/mcp/test_confiabilidade.py`, `tests/test_deploy.py` se ele varre `deploy/`
**Produces:** a constante `AVISO_VAZIO` com o texto exato da spec.
- [ ] Testes que falham:
  - `financeiro_lancamentos` sem resultado traz `vazio` e `aviso`, sem perder as outras chaves (Review Focus 5).
  - Com resultado, nenhuma das duas chaves aparece.
  - `documentos_buscar` vazio traz o aviso.
  - O SOUL do repositório contém as três regras novas, palavra por palavra, e não contém "reembolso" nem "exames".
  - O script não sobrescreve sem backup (teste com `HOME` temporário).
- [ ] Rodar e ver falhar. [ ] Implementar. [ ] Rodar `tests/mcp tests/test_deploy.py -q`. [ ] Commit `feat(mcp): vazio explícito e SOUL do Hermes versionado`.

### Task 10: Carga inicial: `familia.yaml` primeiro, OCR como complemento
(Revisto em 23/10, spec seção "Carga inicial": o brain já tem a base de 08/10 com números **mascarados**; a carga traz o número completo e o que mudou, e o Ricardo pediu "trazer tudo".)
**Files:** Create `tools/carga_familia.py`; Modify `gabi/familia/documentos.py` (mascarado), `pyproject.toml` e `requirements.lock` (PyYAML); Test `tests/test_carga_familia.py`, `tests/familia/` (mascarado)
**Consumes:** Tasks 2, 3 e 4 (`propor`, `decidir`, `contato.atualizar`, `pessoa_historico`); `Ponte(caminho, "paperless")` (`docs`, `documento`, `texto`).
**Produces:**
- Em `documentos.py`: documento ativo com `*` no número é "mascarado". `propor` sem documento igual aponta `documento_id` para o mascarado do mesmo `tipo`+`pais` (o primeiro por id); se os dígitos visíveis do mascarado não forem sufixo dos dígitos do número novo, `conferir=1`. `decidir` aprovando sobre mascarado grava também `numero`.
- `carregar_yaml(con, dados: dict, agora, aplicar: bool) -> dict` (contagens) e `extrair(ocr: str) -> list[dict]` (`{tipo, numero, emissao, validade, conferir}`), `ligar(con, titulo, ocr) -> pessoa_id | None`.
- `main(argv)` com `--yaml` (padrão `~/OP-Gabi-fechamento/familia.yaml`), `--sem-ocr`, `--aplicar` e `--socket` (padrão `GABI_FONTES_SOCKET`). Sem `--aplicar` nada é gravado (tudo numa transação desfeita, ou só contagem).
- Etapa yaml, exatamente como na spec: ligação por `id`; documentos de pessoa viram propostas `origem='carga'` (emissor de `emissor`/`autoridade_emissora`, emissão de `emissao`/`expedicao`, data só `YYYY-MM-DD` válida, `conferir` para CPF sem DV e passaporte/cnh sem validade); contato (`telefone`, `nascimento`, `enderecos`, `apelido`) via `contato.atualizar` com `quem='carga'`, só quando vazio ou sem linha em `pessoa_historico` para o campo, senão conta divergência; empresa: `documentos` e `dados_bancarios` diferentes atualizam `empresa.dados` e gravam `decisao` "carga atualizou <campo> da empresa <id>" sem valor; pets e `obrigacoes` só conferem; `matriz_de_acesso`, `assistente`, `documento` ignorados.
- Etapa OCR: busca pelos termos da spec; propõe só documento que não existe ou campo vazio (com `paperless_id`); OCR divergente do yaml/ativo sai `conferir=1`.
- Expressões OCR:
  - CPF `\d{3}\.?\d{3}\.?\d{3}-?\d{2}`, com DV;
  - passaporte BR `[A-Z]{2}\d{6}`;
  - datas `dd/mm/aaaa` e `dd mmm aaaa` (em inglês e português) perto de "validade", "valid until", "date of expiry" ou "expira";
  - RG `\d{1,2}\.?\d{3}\.?\d{3}-?[\dxX]`;
  - CNH: 11 dígitos perto de "registro".
- A saída mostra só contagens (lista da spec), nunca número, nome de arquivo com dado ou valor.
- [ ] Testes que falham (yaml e OCR de exemplo, sem dado real; nunca ler o `familia.yaml` real nos testes):
  - Mascarado: proposta aponta para ele; aprovar troca o número e não cria segundo documento; dígitos visíveis que não batem dão `conferir=1`.
  - yaml: ligação por id; id ausente conta "sem cadastro"; tipo normalizado; data inválida descartada; CPF com DV inválido `conferir=1`; passaporte sem validade `conferir=1`.
  - Contato: grava em campo vazio e em campo nunca editado (com histórico `quem='carga'`); campo com linha em `pessoa_historico` não muda e conta divergência; valor igual não grava.
  - Empresa: `dados_bancarios` diferente atualiza e grava `decisao` sem o valor.
  - Rodar duas vezes com `--aplicar` não duplica propostas nem histórico.
  - OCR: CPF válido `conferir=False`, DV inválido `True`; passaporte com validade; data dd/mm lida como BR, e mais de uma data candidata dá `conferir=True` (Review Focus 4); OCR divergente do ativo `conferir=1`.
  - Sem `--aplicar`, nenhuma linha é gravada; com `--aplicar`, as propostas saem com `origem='carga'`.
  - A saída não contém número.
- [ ] Rodar e ver falhar. [ ] Implementar. [ ] Rodar `tests/test_carga_familia.py tests/familia -q` e a suíte. [ ] Commit `feat(tools): carga da família pelo familia.yaml e pelo OCR do Paperless`.

### Task 11: Documentação
**Files:**
- Modify `docs/runbook.md`: seção `#familia` com estes passos:
  1. instalar;
  2. `python -m tools.carga_familia` sem e depois com `--aplicar`, com o caminho do socket e o usuário certos (conferir no `deploy/` como os outros tools rodam);
  3. aprovar na aba Família;
  4. token do Hermes com `familia` (emitir, listar, revogar, como no `#envios`), `tools.include` e reinício do `hermes-gateway`;
  5. `bash deploy/instalar-hermes-soul.sh`.
- Modify `docs/BACKLOG.md` (item novo FA1 aberto com dono R), `docs/STATUS.md` (uma linha), `docs/ARQUITETURA.md` (`gabi/familia`), `docs/DOSSIE-REVISAO-EXTERNA.md` (o cadastro familiar sai de "em desenho" e passa a "pronto na branch"; a parte B e a parte C entram em funcionalidades).
- [ ] Escrever. [ ] Rodar a suíte completa e o painel; ler os resumos. [ ] Commit `docs: cadastro familiar, OCR e confiabilidade`.
