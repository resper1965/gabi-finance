# Reembolso de saúde no gabi.brain (D8)
Data: 16/10/2026 · Estado: aprovado para implementar (decisões pequenas abaixo; o Ricardo pode trocar qualquer uma) · Item D8 de `docs/BACKLOG.md` · Origem: `reembolso_fila.py`, `paperless_fluxos.py`, `dossies.py`, `requisitos.py` do gabi-fin.

**Atenção:** isto é o reembolso do PLANO DE SAÚDE para o Ricardo (SulAmérica). Não confundir com `gabi/cobrar/reembolso.py` (despesas que ness/IONIC devem a ele).

## 1. O que o legado faz
1. A escuta antiga (agente `escuta`) lê um documento de saúde no WhatsApp e grava uma **pista** (`pista-<md5>.json`: paciente, prestador, caso consulta|tratamento, tipo do documento, data, valor, CPF/CNPJ, conselho, especialidade, confiança) numa fila de arquivos, com a cópia do anexo.
2. `reembolso_fila.py` (root, `gabi-reembolso.path` + timer de 15 min) copia o anexo para o consume do Paperless, acha o documento pelo checksum, classifica (tipo, campos) e aplica etiqueta: `reembolso-a-pedir`, `reembolso-sem-nf` (consulta sem nota fiscal), `reembolso-sem-aprovacao` (tratamento sem aprovação da operadora) ou `a-conferir` (confiança baixa). Autorização da operadora não ganha etiqueta: conta para o par (paciente, prestador).
3. **Dossiê** = (paciente, prestador, mês do atendimento) entre os documentos `a-pedir`. `requisitos.json` define o que falta: itens de todo dossiê (comprovante, paciente, data, valor, prestador, CPF/CNPJ, conselho, especialidade) e, para tratamento, pedido médico e relatório. Portões: consulta só com NF; tratamento com NF e autorização. NF vale só no mês do dossiê; autorização vale para o par.
4. `fluxos.py diario`: **reabre** documento `sem-nf`/`sem-aprovacao` quando o item chega (até 90 dias), resume os dossiês, manda **dois avisos por dossiê** (abriu / pronto), casa o **crédito da operadora** no extrato (`reembolso-pedido` -> `reembolso-recebido`) e marca `a-conferir` o pedido sem crédito há mais de 30 dias.
5. Comandos da Gabi: `documentos` (manda os PDFs do dossiê no Telegram do OpenClaw) e `pedi [protocolo]` (a-pedir -> pedido).
6. `fluxos.py segunda` (timer 08h BRT): lista "reembolsos a pedir e a conferir" no Telegram.

## 2. O que muda no brain
| Legado | Brain |
|---|---|
| Pista em fila de arquivos (escuta antiga) | **Sem fila.** A escuta nova (ADR-016) já grava o anexo de saúde no Paperless; com tipo de documento de reembolso (NF, recibo, comprovante, pedido médico, relatório, autorização) ou `caso` informado, a etiqueta é `gabi:saude-reembolso` (e não `gabi:saude-exame`). O Ricardo também pode pôr `gabi:saude-reembolso` à mão em qualquer documento do Paperless. |
| Classificação vinda da pista | O brain classifica **a partir do documento** (texto/OCR do Paperless): um modelo barato devolve JSON validado (tipo, caso, paciente, prestador, data, valor, CPF/CNPJ, conselho, especialidade, confiança); texto do documento é dado de terceiros entre marcas (R14), CPF mascarado antes do modelo. Sem modelo/teto: o documento espera a próxima rodada. |
| Etiquetas trocadas (sai/entra) | O cliente do Paperless só ACRESCENTA etiquetas `gabi:*`. O **estado vive no cofre cifrado**; o Paperless recebe só marcas que nunca voltam atrás (tabela em 4). |
| `requisitos-pedido.json` no workspace | `parametro` `reembolso_saude.requisitos` (JSON editável); sem ele vale `seeds/reembolso-saude-requisitos.json` (cópia do seed do legado). |
| Avisos no Telegram do OpenClaw | Avisos do brain (`aviso`, entregues pelo `gabi-brain-telegram`), **sem nomes** (ver 3). |
| `documentos` (PDFs no Telegram) | Ferramenta MCP `reembolso_saude_dossie`: devolve os ids dos documentos do dossiê e um **rascunho do pedido** (lista do que anexar). Os PDFs saem por `documentos_baixar` para o próprio Ricardo; quem envia à operadora é ele (R2). |
| `pedi` | Ferramenta MCP `reembolso_saude_pedi` (escopo `propostas`): **registra** que o Ricardo pediu (fila `reembolso_saude_acao`); a próxima rodada aplica no cofre. Não envia nada. |
| Lista de segunda 08h | A rodada gera, na segunda a partir das 08h BRT, **um aviso** `reembolso_saude_semana` (uma vez por semana) com o mesmo texto da ferramenta MCP `reembolso_saude_segunda` (sem modelo). |
| Timers `gabi-reembolso.path`/`.timer`/`-segunda.timer` | Um timer do brain: `gabi-brain-reembolso-saude.timer` (15 min), instalado e DESLIGADO. |

## 3. Dado de saúde (ADR-014)
Paciente, prestador, valor, CPF do profissional, conselho e especialidade **ficam só no cofre cifrado** (`saude.enc`, tabelas `reembolso_doc` e `reembolso_dossie`, criadas pelo próprio módulo, sem tocar em `saude.py`). No `gabi.db` (migração 0040) ficam só: referência do documento (`reembolso_saude_doc`: id, estado do processamento, motivo em código fixo) e a **projeção por dossiê** (`reembolso_saude_dossie`: número, mês, estado, quantidade de documentos, códigos do que falta, data do último documento) e a fila de ações. O MCP não recebe a chave do cofre (ADR-014), então as ferramentas só leem essa projeção: falam em "dossiê 3 (09/2026)", nunca em nomes. Quem é o dossiê o Ricardo vê em `GET /api/v1/reembolso-saude/dossies` (só boss com grau total em saúde; a leitura entra no log do cofre) ou no Paperless. Aviso, log e texto da lista de segunda também não levam nome.

## 4. Estados e etiquetas
Estado de cada documento (cofre): `a_pedir`, `sem_nf`, `sem_aprovacao`, `a_conferir`, `autorizacao` (só apoio), `pedido`, `recebido`.
| Legado | `gabi:*` | Quando o brain acrescenta |
|---|---|---|
| (entrada) | `gabi:saude-reembolso` | a escuta (ou o Ricardo) |
| `reembolso-a-pedir` | nenhuma | estado só no cofre (o a-pedir some quando vira pedido, e o cliente não remove etiqueta) |
| `reembolso-sem-nf`, `reembolso-sem-aprovacao`, `a-conferir` | nenhuma | idem: voltam atrás ao chegar o item; ficam no cofre e no aviso |
| `reembolso-pedido` | `gabi:reembolso-pedido` | quando o `pedi` é aplicado |
| `reembolso-recebido` | `gabi:reembolso-recebido` | quando o crédito da operadora é casado (ou o Ricardo declara) |
Documentos antigos com `reembolso-a-pedir`, `reembolso-pedido`, `reembolso-recebido` ou do tipo "Autorização" no Paperless são **adotados** (leitura) na primeira rodada: reclassificados pelo texto; `pedido` e `recebido` mantêm o estado.

## 5. Requisitos (dados editáveis)
Chave `reembolso_saude.requisitos`: `operadora`, `operadora_extrato`, `dias_guarda_nao_reembolsavel` (90), `dias_sem_credito` (30), `consulta_exige` (["nf"]), `tratamento_exige` (["nf","autorizacao"]), `todos` (comprovante, paciente, data, valor, prestador, doc_prestador, conselho, especialidade), `tratamento` (pedido_medico, relatorio) e `rotulos` (nome de cada item nas mensagens). Valores como no seed do legado. Item fora do vocabulário (nf, recibo, comprovante, pedido_medico, relatorio, autorizacao; paciente, prestador, valor, doc_prestador, conselho, especialidade, data) ou JSON quebrado: o módulo não roda e avisa `reembolso_saude_requisitos` (nunca inventa).

## 6. O que NÃO será portado
- **Envio de PDFs no Telegram do OpenClaw** e `openclaw message send`: o OpenClaw sai; R2 proíbe envio externo automático. Vira a ferramenta de dossiê + `documentos_baixar`.
- **Fila de arquivos** (`pista-*.json`, `cmd-*.json`, `aviso-*.json`, `feitas/`, `falhas/`) e cópia do anexo para o consume: o anexo já está no Paperless.
- **Casar pelo checksum**: não há mais pista para casar.
- **Campos personalizados do Paperless** (`paciente`, `prestador`, `caso-reembolso`...): o cliente do brain não os escreve; os dados ficam no cofre. Leitura dos campos antigos: Depois (os documentos antigos são reclassificados pelo texto).
- **`valor-reembolsado` preenchido à mão**: o casamento de crédito usa o valor total (como o legado sem o campo).
- **PDF sem texto (foto sem OCR)**: o documento fica `falhou` ("sem texto legível"); leitura por visão: Depois.
- **Tela no painel**: Depois (a API de leitura existe).

## 7. Decisões pequenas (uma linha cada; a mais conservadora)
- D-1 Nome do módulo `gabi/reembolso_saude/`; ferramentas `reembolso_saude_*` (não colidem com `reembolsos_*` de cobrar).
- D-2 Modelo só classifica texto que já está no Paperless; resposta inválida = documento `falhou` (código `resposta inválida`), sem repetir com o modelo forte.
- D-3 Confiança abaixo de `LIMIAR` (`gabi/dinheiro/modelo.py`), tipo de documento ou caso ausente = `a_conferir`; o brain não adivinha.
- D-4 `caso` ausente nunca vira "consulta" por padrão.
- D-5 Aviso por dossiê: um "abriu" e um "pronto" (como no legado), com o dossiê pelo número e mês, sem nomes. Aviso de "não reembolsável" também por número.
- D-6 Rodada a cada 15 min (como o timer legado), instalada e desligada; um escritor do cofre por vez (trava de arquivo ao lado do cofre; exames e API ainda não usam a mesma trava: resíduo registrado).
- D-7 Crédito só casa com lançamento positivo cuja descrição contém `operadora_extrato`, de data igual ou posterior ao pedido, e só se for único candidato.
- D-8 Pedido ambíguo não existe: `pedi` é por número de dossiê, não por nome.
- D-9 Lista de segunda sem nomes; sai como aviso (uma vez por semana) e sob demanda por MCP.
- D-10 `reembolso_saude_pedi` e `reembolso_saude_recebi`: só gravam intenção; o cofre muda na rodada. Sem confirmação do Ricardo no chat, o Hermes não deve chamá-las (instrução na descrição da ferramenta).
- D-11 Classificação pela escuta nova: documento desconhecido continua `gabi:saude-exame` (comportamento de hoje).
- D-12 Escopos: leituras `fin` (lista, segunda) e `docs` (dossiê, que revela ids de documentos); `pedi`/`recebi` em `propostas`.

## 8. Aceite
Documento de NF/recibo/pedido enviado pela escuta (modo `ativo`) vira dossiê no cofre; "faltando" bate com `requisitos`; aviso "abriu" e depois "pronto" chegam sem nome; `reembolso_saude_dossie` lista os ids; `pedi` move para pedido e acrescenta `gabi:reembolso-pedido`; crédito do extrato vira recebido; na segunda 08h chega a lista. Com isso `gabi-reembolso.path`, `gabi-reembolso.timer` e `gabi-reembolso-segunda.timer` saem (runbook).
