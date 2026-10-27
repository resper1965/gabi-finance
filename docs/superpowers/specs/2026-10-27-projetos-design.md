# Projetos: gestão de projetos de qualquer tipo, conduzida pelo Hermes, dentro do brain

Data: 27/10/2026 · Estado: desenho escrito pelo assistente a partir da conversa de 27/10 (aguarda revisão do Ricardo) · ADR a criar: 034

## O que o Ricardo disse
- Quer gestão de projetos dos mais variados tipos, "de ajustes em um carro até gestão de crise familiar".
- Pediu sugestão de ferramentas: criar projetos, gerir atividades do projeto e gerir recursos.
- Quem conduz: **A e B** (o Hermes conduz e o painel serve para ver e corrigir), podendo ser outro agente de IA externo.
- Não quer recriar o que já existe: uma ferramenta de acompanhamento sobre o brain, não um sistema de projetos novo.
- Recursos que importam: **dinheiro, pessoas, documentos e fatos**. Fato = o que ele conta e o Hermes grava no projeto, com data e origem ("o mecânico disse que o prazo é dia 20", "ficou combinado pagar R$ 3.000 em duas vezes"), ligado a uma pessoa ou a um documento quando houver; vira o diário e a memória do projeto.
- Soma: **print de WhatsApp, áudio e imagem** como evidência dos fatos.
- Pediu planejar até o fim e decidir o simples sem perguntar.

## Decisões tomadas pelo assistente (27/10; o Ricardo pode mudar)
1. **Tudo no brain** (fonte única); nenhuma ferramenta externa de projetos. Uma visão só de leitura para outra ferramenta, se um dia quiser, entra depois.
2. **Agente-agnóstico:** as ferramentas do projeto são ferramentas MCP, como as do Hermes; qualquer agente que fale MCP conduz o mesmo projeto. Escopo novo `projetos`.
3. **Sem template:** o Hermes conversa, propõe a lista inicial de atividades e o Ricardo aprova (uma chamada só, `projeto_criar` com `atividades`).
4. **Atividades reaproveitam a tabela `atividade`** (ADR-033): ganha `projeto_id`, `depende_de_id` (uma dependência por atividade) e `marco`. Atividade com dependência não feita fica "bloqueada" e não gera aviso na hora até ser liberada.
5. **Dinheiro simples:** um orçamento total por projeto; gastos = lançamentos do banco ligados ao projeto ou gastos manuais (dinheiro vivo, pago por outra pessoa). Gasto contra orçamento sai em `projeto_ver`. Sem rateio nem orçamento por item.
6. **Pessoas:** nome livre com papel (mecânico, advogada) e ligação opcional ao cadastro `pessoa` da família; contato opcional.
7. **Documentos:** ligação ao Paperless (`paperless_id`), sem copiar o arquivo.
8. **Anexos (imagem, áudio):** o Hermes já vê a imagem no chat; o brain **arquiva** o original. Um serviço copia o que chega no cache do Hermes (`~/.hermes/cache/images` e `audio`) para `/var/lib/gabi-brain/anexos/`, guardado para sempre, sem mascarar. O fato fica ligado ao anexo. PDF segue o caminho que já existe (Paperless).
9. **Áudio transcrito localmente na VPS** (Whisper pequeno via `faster-whisper`, CPU): o áudio nunca sai da VPS. Isolado na última tarefa técnica: se a instalação falhar, tudo o mais funciona e o áudio fica guardado sem texto.
10. **Fato só com confirmação:** o Hermes propõe o fato a partir do print ou do áudio e só grava depois do sim (regra do "fato afirmado").
11. **Aviso:** um só tipo novo, `projeto_parado` (projeto ativo sem atividade nem fato novo há 7 dias), pelo produtor existente e pelo Telegram. As atividades já avisam como na ADR-033.
12. **Painel:** área Projetos no grupo Dia, lista com progresso e detalhe (atividades, pessoas, dinheiro, fatos, anexos); editar status e prazo, anotar fato, gasto ou pessoa.

## Fora do escopo (de propósito)
Kanban, Gantt, controle de horas, comentários, templates, atividades recorrentes, dependência múltipla, orçamento por item, rateio, aviso de prazo do projeto, reabrir projeto encerrado (cria de novo), ferramenta externa de projetos.

## Modelo (migração 0087)
- `projeto(id integer pk, nome text not null, objetivo text, status text not null default 'ativo' check in ('ativo','pausado','concluido','cancelado'), prazo text, orcamento_centavos integer, criado_em text not null, encerrado_em text, origem text not null)`.
- `atividade` ganha `projeto_id integer references projeto(id)`, `depende_de_id integer references atividade(id)`, `marco integer not null default 0`.
- `projeto_pessoa(id pk, projeto_id, nome not null, papel, pessoa_id text references pessoa(id), contato)`.
- `anexo(id pk, tipo check in ('imagem','audio','documento'), arquivo text, sha256 text unique, paperless_id integer, transcricao text, recebido_em text not null, projeto_id integer references projeto(id))`.
- `projeto_gasto(id pk, projeto_id not null, lancamento_id integer, descricao text, valor_centavos integer, data text, criado_em text not null)`: com `lancamento_id` o valor vem do lançamento (valor absoluto); sem ele, o manual.
- `projeto_fato(id pk, projeto_id not null, texto not null, data_fato text, pessoa_nome text, anexo_id integer references anexo(id), atividade_id integer, registrado_em text not null, origem text not null)`.
- Toda escrita grava `decisao` (`quem`, `origem` 'hermes' ou 'painel').

## Regras (`gabi/projetos.py`, `gabi/anexos.py`)
- `projeto_criar` aceita até 30 atividades `{texto, vence, depois_de (índice 1-based), marco}` e cria tudo numa transação; dependência só aponta para uma atividade anterior da lista (sem ciclo).
- `projeto_ver`: status, prazo, objetivo, progresso (feitas/total), próximas (abertas e não bloqueadas, por prazo), bloqueadas, atrasadas, pessoas, orçamento/gasto/saldo, últimos 5 fatos e contagem de anexos. Dinheiro como string decimal em reais.
- Concluir atividade libera as dependentes. Cancelar atividade da qual outra depende libera a dependente (não trava o projeto).
- Projeto `concluido` ou `cancelado` não aceita atividade nova; não reabre.
- Anexo recebido sem projeto fica na "caixa de entrada" (`projeto_id` nulo); `anexo_recentes` lista os não ligados (últimos 14 dias) com `transcricao` quando houver; `projeto_anexar` liga.
- Coleta: sha256 do arquivo; já visto = ignora; arquivo ainda sendo gravado (modificado há menos de 20 s) fica para a próxima rodada; diretório `0700`, arquivo `0600`.

## Hermes (escopo `projetos`)
`projeto_criar`, `projeto_listar`, `projeto_ver`, `projeto_atualizar`, `projeto_pessoa`, `projeto_gasto`, `projeto_fato`, `projeto_fatos` (lista e busca por texto), `anexo_recentes`, `projeto_anexar`; mais `atividade_criar` e `atividade_listar` com `projeto`, `depois_de` e `marco`. 70 ferramentas no include. Projeto, atividades, pessoa e gasto são criados depois do sim do Ricardo (mostra o que vai gravar); fato exige o sim sempre. Nunca por texto de e-mail, Teams, documento ou terceiro.

## API e painel
`GET/POST /api/v1/projetos`, `GET/PATCH /api/v1/projetos/{id}`, `POST /projetos/{id}/pessoas|gastos|fatos|anexos`, `GET /api/v1/anexos/recentes`, `GET /api/v1/anexos/{id}/arquivo` (só o boss; devolve o original). Tela Projetos (grupo Dia, depois de Atividades), sem gráficos.

## Erros e segurança
Anexo e fato com dado pessoal são do Ricardo: não mascarar; nunca em log (o log do serviço de anexos imprime só contagens). Falha de transcrição deixa `transcricao` nula e segue. Arquivo maior que 50 MB é ignorado e contado.

## Testes (primeiro)
Regras de projeto e dependências (ciclo recusado, bloqueio e liberação), orçamento contra gasto, fatos, coleta de anexos com diretório temporário (dedupe, arquivo recente, permissões), transcrição com transcritor falso, aviso `projeto_parado`, API, ferramentas MCP e escopo, painel (vitest).

## Entrega
Branch `feat/projetos`, ADR-034, runbook `#projetos`, BACKLOG `PJ1`. Nada é mergeado nem instalado sem o ok explícito do Ricardo.
