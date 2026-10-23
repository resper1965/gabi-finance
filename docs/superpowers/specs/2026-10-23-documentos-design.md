# Documentos: números e validades de tudo que está no Paperless

Data: 23/10/2026 · ADR: `docs/adr/027-documentos.md` (a escrever junto com o código) · Amplia a ADR-025 (cadastro familiar)

## Objetivo
"Documento" é qualquer papel relevante da vida do Ricardo: identidade, CNH, passaporte, visto, escritura, matrícula, IPTU, CRLV, apólice, contrato, procuração, certidão, garantia, carteirinha de plano. O que é relevante vai para o Paperless, que é o arquivo único. O brain lê cada documento, tira os **números que o identificam** e as **datas que importam** (validade, vigência, vencimento, renovação) e liga tudo a **quem ou o que** ele se refere (pessoa, imóvel, veículo ou outro bem). O Ricardo não preenche nada: confere e aprova.

## Decisões do Ricardo (23/10)
1. Usos: **perguntar ao Hermes**, **aviso de vencimento**, **ver no painel** e **ter os dados para preencher** cadastros.
2. Fonte: **só o Paperless**.
3. **Imagem nunca vai a modelo.** Escaneado sem texto fica com o OCR que o Paperless tiver.
4. **O texto (OCR) pode ir a um modelo** pelo OpenRouter, para entender qualquer tipo de documento.
5. Caminho A: ampliar o cadastro familiar (proposta → aprovação no painel), com bens ao lado das pessoas.

## Exceções a decisões anteriores (aceitas pelo Ricardo)
- ADR-025 "Fora: extração por modelo" e o parecer de 22/10 ("metadados nunca extraídos por modelo"): passa a haver extração por modelo, só do texto.
- Texto de documento com CPF, endereço e valores sai da VPS para o provedor do modelo.
- ADR-023, regra do mês: tabelas, rodada e aviso novos sem o mês de uso manual.

## Fora do escopo
Leitura de imagem por modelo; refazer OCR localmente; escrever no Paperless; anexos de e-mail e Drive; preencher formulário sozinho (o painel e o Hermes só entregam os dados).

## 1. Dados (migração 0081; a 0080 é da conciliação achatada)
| tabela | uso |
|---|---|
| `bem` | `id` texto (`apto-moema`), `tipo` (`imovel` · `veiculo` · `outro`), `nome`, `dados` JSON (endereço, modelo, ano), `criado_em`, `excluido_em` |
| `documento` | `id`, `titular_tipo` (`pessoa` · `bem`), `titular_id`, `tipo` (texto livre normalizado: `cnh`, `crlv`, `apolice`…), `pais` (2 letras, `BR` padrão), `emissor`, `paperless_id`, `origem` (`legado` · `ricardo` · `leitura`), `criado_em`, `atualizado_em`, `excluido_em` |
| `documento_numero` | `documento_id`, `nome` (`numero`, `placa`, `renavam`, `chassi`, `matricula`, `inscricao_iptu`, `apolice`…), `valor` (exatamente como está no documento) |
| `documento_data` | `documento_id`, `tipo` (`emissao` · `validade` · `vigencia_inicio` · `vigencia_fim` · `vencimento` · `renovacao`), `data` |
| `documento_proposta` | o documento inteiro proposto (JSON canônico), `documento_id` que substitui (se houver), `bem_novo` JSON (se o titular é um bem ainda inexistente), `paperless_id`, `conferir` + `motivos`, `estado` (`pendente` · `aprovada` · `recusada`), `origem` (`hermes` · `leitura`), datas |
| `documento_leitura` | `paperless_id` pk, `modificado` (do Paperless), `estado` (`lido` · `sem_texto` · `sem_documento` · `falhou`), `motivo` curto, `custo`, `lido_em` |

A migração copia `pessoa_documento` para `documento` (+ `documento_numero` `numero`, + `documento_data` `emissao`/`validade`) e as `pessoa_proposta` pendentes para `documento_proposta`. As tabelas antigas ficam como `*_legado` (não lidas mais; desfazer = renomear de volta). `familia_consultar`, `familia_vencimentos` e `familia_propor_documento` passam a ler e escrever as novas, com a mesma resposta de hoje.

## 2. Leitura (`gabi/documentos/leitura.py`, rodada diária `gabi-brain-documentos.timer`, 05h)
1. Lista os documentos do Paperless pela ponte (`docs`, só leitura) e pega os que não estão em `documento_leitura` ou cujo `modified` mudou. Primeira rodada = todos, com teto de documentos por rodada (`documentos.max_por_rodada`, padrão 50) para espalhar o custo em dias.
2. OCR vazio ou com menos de 40 caracteres úteis: `sem_texto`, sem modelo.
3. Manda ao modelo (fraco; forte só se o fraco não devolver JSON válido) o título, a data e o OCR (até `documentos.max_caracteres`, padrão 12.000), com a instrução de que o texto é DADO e nunca instrução, pedindo JSON: `{"relevante": bool, "tipo", "pais", "emissor", "titular": {"nome", "cpf", "placa", "renavam", "matricula", "endereco"}, "numeros": [{"nome", "valor"}], "datas": [{"tipo", "data"}]}`. `relevante=false` (boleto avulso, nota fiscal, recibo): `sem_documento`.
4. **Conferência local, sem confiar no modelo:**
   - **Número "as is":** cada número tem de aparecer no OCR exatamente como o modelo devolveu, ignorando só espaços e pontuação (`.`, `-`, `/`). O que não aparece é descartado. Nenhum cálculo de dígito verificador e nenhuma correção: se o OCR leu `FKO77009`, a proposta traz `FKO77009` e o Ricardo corrige na aprovação olhando o documento (decisão do Ricardo, 23/10).
   - Datas: formato válido; validade antes da emissão vira `conferir`.
5. **Titular:** pessoa por CPF; senão por nome (primeiro nome único, como `resolver_pessoa`); bem por placa, Renavam, chassi, matrícula ou inscrição; senão endereço igual a um bem. Sem titular: a proposta traz `bem_novo` (veículo se há placa/Renavam/chassi, imóvel se há matrícula/inscrição/endereço, senão `outro`) e fica `conferir`.
6. Já existe documento igual (mesmo titular, tipo e número principal, mesmas datas): nada. Igual com datas novas: proposta que substitui.
7. Grava a proposta e `documento_leitura`. Erro de modelo: `falhou`, nova tentativa na rodada seguinte (até 3). Custo gravado por chamada; teto diário do serviço de modelo vale (reusa o orçamento do correio, `dinheiro.modelo.Orcamento`).

## 3. Aprovação e painel (aba **Documentos**, substitui a aba Família em `#cadastros/documentos`; `#cadastros/familia` redireciona)
- **Propostas:** cartão com titular (ou "bem novo: …"), tipo, números, datas, motivos de `conferir` e link do Paperless. Ações: aprovar, recusar, corrigir um campo antes de aprovar, escolher outro titular.
- **Lista:** por pessoa e por bem; cada documento com números (botão copiar) e datas; vencido em destaque; "vence em até 60 dias" em atenção.
- Aprovar cria/atualiza `documento` (e `bem`, se novo) e registra em `decisao` (origem `documentos`).

## 4. Hermes e avisos
- **MCP (escopo `familia`, que já tem números completos):** `documentos_consultar(titular?, tipo?, texto?)` devolve documentos aprovados com números, datas e link do Paperless; `documentos_vencimentos(meses)` substitui por dentro o `familia_vencimentos` (que continua). `bens_listar()`. Cada consulta registrada sem os números (como a ADR-025).
- **Aviso `documento_vence`** (`gabi/avisos.py`): para cada documento aprovado com `validade`, `vigencia_fim` ou `vencimento`, avisa a 60, 30 e 7 dias (`documentos.avisar_dias`), um por (documento, marco). Fecha sozinho quando o documento sai, ou quando um documento do mesmo titular e tipo com data posterior é aprovado. Revalidado na entrega como os outros avisos. Documento já vencido há mais de 30 dias na aprovação não gera aviso (o passaporte da Louise de 2019 não vira alerta).

## 5. Segurança
- O OCR vai ao modelo marcado como dado; o resultado só gera proposta; nada do documento alimenta `decisao_responder` nem envio.
- Números completos só no escopo `familia` (Hermes) e no painel; logs e `documento_leitura.motivo` nunca levam número nem texto.
- Ponte do Paperless continua só leitura (`docs`, `documento`, `texto`, `baixar`).

## 6. Testes
- Leitura com modelo falso: número inventado descartado; número com pontuação diferente aceito; `FK077009` do modelo contra `FKO77009` no OCR = descartado (as is); titular por CPF, placa e bem novo; documento igual não repropõe; `sem_texto`, `sem_documento`, `falhou` e as 3 tentativas; teto por rodada.
- Migração: dados da família copiados, propostas pendentes copiadas, `familia_*` com a mesma resposta.
- Aviso: marcos 60/30/7, fechamento por documento novo, vencido antigo sem aviso.
- Painel (vitest): aprovar, corrigir, escolher titular, copiar.

## Pronto quando
1. Suíte verde (pytest e vitest).
2. Instalado; a primeira rodada leu os documentos do Paperless e o Ricardo vê as propostas na aba Documentos.
3. O Hermes responde "qual o Renavam do carro?" com o dado aprovado e o link.
4. Um aviso `documento_vence` real chega no Telegram ou a lista de vencimentos mostra o próximo.
