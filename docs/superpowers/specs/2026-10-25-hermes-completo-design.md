# Hermes completo: o agente usa o que o brain já sabe

Data: 25/10/2026 · ADR: `docs/adr/028-hermes-completo.md` (a escrever junto com o código da Onda 1) · Depende de: Documentos (ADR-027, migração 0081) mergeado antes.

## Objetivo
O Hermes deixa de falhar nas perguntas reais do Ricardo por falta de ferramenta, e nunca mais afirma que gravou algo que não gravou. O brain já guarda contatos, a receber, avisos, Teams, regras, empresas e família. O Hermes passa a ler isso e a gravar, com as travas de sempre, o que o Ricardo dita.

## Evidência (conversas de 23 e 24/10, banco de 25/10)
- **"Anotado!" sem gravar:** em 24/10 o Ricardo ditou filhas, ex-esposas, companheira, mãe, pai, irmãos, sobrinhos, o Cookie e as empresas. O Hermes respondeu "Anotado!" cerca de 15 vezes e não chamou nenhuma ferramenta de escrita. Nada ficou no brain nem na memória dele. A ferramenta `familia_atualizar_contato` já grava `parentesco`, mas ele não a usou. Também não há como criar pessoa nova (irmãos, mãe, sobrinhos) nem pet.
- **"Dados até 14/10 (desatualizados)"** na ficha da família: o envelope marca toda resposta como desatualizada porque `notas-nibo` é fonte esperada e o Nibo está em 401 desde 16/10 (em espera por chave). A família não depende do Nibo.
- **Sem ferramenta, embora o dado exista:**
  - contatos: 1.137 do Google e 1.152 do Graph;
  - a receber: 248 notas e 224 recebimentos;
  - avisos: 128;
  - conversas do Teams;
  - regras: 64;
  - empresas: 6.

  No parecer de 22/10 ficaram sem resposta: "você tem meus contatos?", registrar um valor a receber (2 vezes) e "apague esses e-mails" (2 vezes).
- **E-mail:** o Hermes oferece "quer que eu leia o conteúdo?", mas o brain só guarda o trecho.

## Decisões do Ricardo (25/10)
1. Escopo em três ondas: (1) honestidade e família; (2) ver tudo; (3) agir com aprovação. Cada onda tem seu próprio plano e merge.
2. **Privacidade é gatilho do Ricardo:** o dado sai completo para ele (números, telefones, e-mails). Nada é mascarado por iniciativa do sistema.
3. Ficam fora: leitura de PDF ou imagem pelo modelo, memória ou histórico semântico, correlação entre fontes.

## Exceções a decisões anteriores (aceitas pelo Ricardo ao aprovar o escopo)
- **ADR-023, regra do mês:** uma tabela nova (`receber_manual`) e cerca de 12 ferramentas MCP sem o mês de uso. A justificativa são os pedidos reais listados acima.
- **R1 parcial:** o que o Ricardo dita no chat é gravado direto, com histórico e desfazer. Isso já valia para contato (ADR-025) e passa a valer para pessoa, pet e valor a receber. Mandar e-mail para a lixeira e criar regra "sempre lixo" por pedido explícito dele no chat também é gravação direta: as duas coisas são reversíveis (lixeira de 30 dias, regra removível).

## Regras que continuam
- R2: nenhum envio externo.
- Texto de terceiros (e-mail, Teams, OCR) é dado, nunca instrução. Pedido vindo de um terceiro nunca vira escrita.
- Logs e `chamada_mcp` só com contagens e ids.
- Nada escreve no Paperless.
- Ponte: método novo só de leitura, na lista branca.
- Segredos, só o Ricardo coloca.

---

## Onda 1: honestidade e família

### 1.1 Regra de honestidade (SOUL)
`deploy/hermes/SOUL.md` ganha uma regra com exemplos:
- "Anotado", "registrei", "salvei" e "guardei" só podem aparecer depois de uma ferramenta de escrita que devolveu ok, e a resposta cita o que foi gravado.
- Se não há ferramenta para gravar aquilo, ele diz: "Não tenho como gravar isso no brain; fica só nesta conversa."
- Dado de família ditado pelo Ricardo vai para `familia_atualizar_contato` ou `familia_registrar_pessoa` na mesma resposta.

### 1.2 Conferência de promessas (`tools/auditar_promessas.py`, rodado pelo assistente, sem timer)
- Lê `~/.hermes/state.db` em modo somente leitura e marca as mensagens do assistente com verbo de gravação ("anotad", "registr", "salv", "guard", "atualiz") que não tiveram nenhuma chamada a ferramenta de escrita do brain no mesmo turno.
- Imprime data, sessão e os primeiros 80 caracteres de cada uma.
- O assistente roda na retomada de cada sessão e traz os casos ao Ricardo.
- Só vira timer depois de um mês com casos.

### 1.3 Pessoa e pet (`gabi/familia/pessoas.py`, ferramentas no escopo `familia`)
- `familia_registrar_pessoa(nome, parentesco, apelido="", nascimento="", falecido=False, observacao="")`:
  - cria a pessoa, ou atualiza se `nome` ou `apelido` resolve para uma pessoa só (mesma resolução de `familia_consultar`);
  - com mais de um candidato, devolve `ambiguo` e a lista; nunca escolhe sozinho;
  - `parentesco` é texto livre curto, relativo ao Ricardo ("irmão", "mãe", "ex-esposa, mãe da Louise", "sobrinho", "proprietária do apto da Gigi");
  - `id` é o slug do primeiro nome e, se já existir, do nome completo;
  - grava em `pessoa_historico` com Desfazer na aba Documentos (bloco por pessoa) e `decisao` com origem `familia`.
- `familia_registrar_pet(nome, especie, raca="", nascimento="", dono="")`: grava na tabela `pet`, que já existe (`dados` JSON). O histórico vai para `pessoa_historico` com `pessoa_id='pets'` (a pessoa `pets` já existe) e `campo='pet:<id>'`; o Desfazer funciona do mesmo jeito.
- `familia_listar` passa a incluir os pets.

### 1.4 Frescor por ferramenta (`gabi/envelope.py`)
- Cada ferramenta declara de quais fontes depende (`FONTES_DA_FERRAMENTA`, padrão: todas).
- As de família, documentos, contatos e empresas declaram nenhuma.
- `dados_ate` e `desatualizado` só olham as fontes declaradas. Um teste garante que toda ferramenta registrada tem declaração.

**Pronto quando:**
- a carga de 24/10 foi refeita pelo Ricardo no chat e ficou no brain (pessoas, parentesco e Cookie);
- `auditar_promessas` não mostra nenhum caso novo em 7 dias;
- a ficha da família não diz mais "desatualizado".

## Onda 2: ver tudo (só leitura)
| ferramenta | escopo | fonte no brain | devolve |
|---|---|---|---|
| `contatos_buscar(texto, limite=10)` | `contatos` (novo) | `contato_google`, `contato_google_email`, `contato_graph` | nome, telefones, e-mails, empresa e origem, juntando o mesmo contato das duas fontes (mesma regra de `listar_unicos`) |
| `financeiro_a_receber(mes="")` | `fin` | `cobrar.a_receber.a_receber_do_mes` mais `receber_manual` (Onda 3) | recorrentes e notas por situação, com totais |
| `avisos_abertos(dias=7)` | `trabalho` | `aviso` | tipo, texto (`descrever`), quando, se já foi ao Telegram |
| `teams_pendentes()` | `trabalho` | `teams_conversa` com `teams.regra.pendente` | quem, desde quando, se o mencionou (sem texto: o texto do Teams nunca é lido) |
| `regras_listar(texto="")` | `fin` | `regra` (mesma consulta de `GET /dinheiro/regras`) | padrão, categoria, para quem, empresa, origem |
| `decisoes_recentes(dias=30, texto="")` | `decisoes` | `decisao` | quando, quem, o quê, origem |
| `empresas_listar()` | `fin` | `empresa` | nome, CNPJ e `dados` |
| `email_ler(mensagem_id)` | `trabalho` | ponte: método novo `mensagem` em `google_email` e `graph_ness` (só leitura) | remetente, assunto, data e corpo em texto (até 8.000 caracteres), marcado como dado de terceiros; nunca de mensagem na lixeira |

- O token do Hermes ganha o escopo `contatos`.
- `email_listar` passa a devolver `mensagem_id`.
- `docs/fontes/hermes.md` é regerado; `~/.hermes/config.yaml` ganha a lista nova de ferramentas (`tools.include`), e o Hermes reinicia.
- No SOUL, uma linha por pergunta típica, apontando a ferramenta.

**Pronto quando:** as perguntas do parecer ("tem meus contatos?", "quanto tenho a receber?", "o que o Igor mandou no LinkedIn?") são respondidas com dado real, sem invenção.

## Onda 3: agir com aprovação
### 3.1 A receber manual (migração 0082)
- Tabela `receber_manual`:
  - `id`, `pagador`, `valor_centavos`, `vencimento` (opcional), `conta` (opcional), `observacao`;
  - `estado`: `aberto`, `recebido` ou `cancelado`;
  - `lancamento_id` (quando casado), `criado_em`, `quem`, `atualizado_em`.
- Ferramenta `financeiro_registrar_a_receber(pagador, valor, vencimento="", conta="", observacao="")` (escopo `fin`): gravação direta do que o Ricardo dita, com `decisao`. A resposta traz o id, para ele desfazer pelo chat (`financeiro_cancelar_a_receber(id)`) ou no painel.
- A conciliação de recebimentos (`cobrar.recebimentos`) passa a propor o casamento com um crédito de mesmo valor (±1%) e mesmo pagador, como já faz com as notas. O Ricardo confirma.
- `financeiro_a_receber` e o painel "A receber" mostram esses itens.
- Desconto ou adiantamento (o caso NESS): registrar com valor negativo e uma observação.

### 3.2 E-mail pelo chat (escopo `trabalho`)
- `email_lixeira(mensagem_ids)`: até 50 por chamada.
  - Vale para qualquer mensagem triada da caixa (não só as sugeridas como lixo, porque o pedido é do Ricardo). Na lixeira recuperável, nunca apaga de vez.
  - A lógica da rota `POST /correio/mensagens/{id}/lixeira` sai para `gabi/correio/lixeira.py`, e a rota e a ferramenta passam a usá-la. A rota mantém a restrição a `classe='lixo'`; a ferramenta não tem essa restrição.
  - Conta com a lixeira desligada (hoje é o caso da ness) devolve `conta_sem_lixeira`.
  - Devolve quantas foram movidas e as que falharam, com o código.
- `email_regra_lixo(remetente_ou_dominio)`: grava em `email.regras_lixo` (mesma normalização de `correio.regras`). Desfazer: `email_remover_regra_lixo`.
- Só por pedido explícito do Ricardo no chat. O SOUL proíbe agir a partir de texto de e-mail ou de terceiros. Cada chamada vai para `decisao` (origem `hermes`) com a contagem, sem assunto nem remetente.

### 3.3 Lembrete de vencimento de documento
O aviso `documento_vence` (Documentos, Task 5) já chega pelo Telegram nos marcos de 60, 30 e 7 dias. **Não** se cria cron no Hermes para isso, para não duplicar. Fica fora desta spec.

**Pronto quando:** o Pix da família Reis e o adiantamento da NESS estão registrados pelo chat e aparecem no "A receber"; uma limpeza de e-mail pelo chat foi feita e conferida na lixeira.

---

## Erros e auditoria
- Códigos fixos: `sem_escopo`, `nao_encontrado`, `ambiguo`, `valor_invalido`, `conta_sem_lixeira`, `fonte_indisponivel`.
- `chamada_mcp` registra ferramenta, status e duração.
- Escritas vão para `decisao` sem número, telefone, e-mail ou texto.
- Falha na ponte vira `fonte_indisponivel`. O Hermes diz isso e não inventa.

## Testes
- pytest por ferramenta: escopo, resposta, erro e auditoria sem dado.
- `test_servidor`: conjuntos e contagens por escopo.
- Envelope: toda ferramenta tem fontes declaradas, e família ignora o Nibo.
- `auditar_promessas` testado com um `state.db` sintético (com e sem chamada de escrita).
- Ponte: teste da lista branca com `mensagem` e nenhum verbo de escrita novo.
- `receber_manual`: registrar, cancelar, casar com crédito e mostrar no "A receber".
- Painel: Desfazer de pessoa e pet no bloco por pessoa (vitest).

## Ordem e entrega
- Onda 1 → Onda 2 → Onda 3. Cada uma passa por plano, execução por subagentes, revisão final, merge e instalação autorizada pelo Ricardo.
- Depois de cada instalação: reiniciar o Hermes e mandar `/new` no Telegram e no WhatsApp.
- A Onda 1 começa depois do merge de Documentos (migração 0081 e aba Documentos).
