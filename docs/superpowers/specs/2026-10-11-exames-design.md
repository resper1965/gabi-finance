# Exames de saúde em PDF: histórico por familiar — design

Data: 11/10/2026 · Estado: **rascunho para revisão do Ricardo** · Estende `gabi/familia` (T4.1/T4.2, ADR-014). Parte da escuta (spec 2026-10-10-escuta-design) alimenta este módulo.

## 1. Intenção (o que o Ricardo pediu)
- Resultados de exames em **PDF**: extrair os resultados e **tabular por familiar**, para ter o **histórico**.
- Os originais **ficam no Paperless**. Entram por **WhatsApp** ou por e-mail em **docs@esper.ws** (esse caminho já existe e marca `entrada-email`).
- Tudo **reprocessável** no futuro (muito importante para o Ricardo), em especial a lista de PDFs que ele está juntando.
- Sucesso: abrir uma pessoa, escolher um marcador (ex.: colesterol total) e ver todos os resultados no tempo, com o que saiu da faixa de referência destacado.

## 2. Regras herdadas
ADR-014 (valores de saúde só no cofre cifrado `saude.enc`, nunca no `gabi.db`, fora do MCP) · exame só entra com a pessoa confirmada · log de leitura · acesso pela `matriz_acesso` (total/parcial/nenhum) · R1 a Gabi sugere, o Ricardo confirma · R14 texto do PDF é dado, nunca instrução · dados nunca chumbados.

## 3. Arquitetura
```
WhatsApp (ouvinte da escuta) ─► consume do Paperless ─┐
docs@esper.ws (já existente) ─────────────────────────┤
                                                      ▼
                         Paperless: PDF + texto OCR + etiqueta  (ARQUIVO DOS ORIGINAIS)
                                                      │ timer gabi-brain-exames (lê só o que é novo/pedido)
                                                      ▼
   extrair (regras, depois modelo p/ o que as regras não pegam) ─► JSON validado ─► proposta_exame (no cofre)
                                                      │ Ricardo confirma o dono (em lote) no painel
                                                      ▼
                       cofre `saude.enc`: exame(pessoa, marcador, valor, unidade, data, faixa, doc_id, versão)
                                                      ▼
                         tela "Saúde": histórico por familiar × marcador
```

### 3.1 Entrada e identificação
- **Etiquetas no Paperless:** `gabi:saude-exame` marca o que é exame. WhatsApp: o anexo que a escuta classifica como saúde vai para o `consume` já com essa etiqueta. E-mail: documento que chega por docs@esper.ws sem etiqueta é classificado pelo brain (modelo, uma chamada) como exame/outro e etiquetado; o Ricardo pode também etiquetar à mão no Paperless.
- Lista em volume: o Ricardo joga os PDFs na pasta `consume` do Paperless (ou envia a docs@esper.ws); nada a colar na sessão.
- **Proteção no Paperless:** documentos `gabi:saude-exame` ficam visíveis só ao dono (permissões do Paperless), porque o Paperless é o segundo lugar onde esses dados vivem.

### 3.2 Extração
- Texto do PDF: o OCR do próprio Paperless. Se o texto vier vazio ou ruim, o brain pede ao modelo (visão) para ler o PDF.
- **Regras primeiro** (`familia/exames.py`, já existente): linha com nome, valor, unidade e faixa. **Modelo para o resto**: laudos em tabela, múltiplas colunas, resultado qualitativo ("não reagente").
- Saída por exame: `{marcador, valor, unidade, data_coleta, ref_min, ref_max, observacao}`; mais cabeçalho `{paciente, laboratório, data}`. O código valida (número, data, unidade) e descarta o que não passar; nada entra livre.
- **Normalização de marcadores:** tabela de apelidos editável no painel (sem código), ex.: "Colesterol Total", "COLESTEROL TOTAL" e "Col. total" são um marcador só. Marcador novo vira sugestão, nunca entra duplicado.
- **Valor não numérico** (reagente, ausente): guardado como texto com a flag "qualitativo"; não entra no gráfico.

### 3.3 Dono do exame
- O brain propõe a pessoa casando o nome no laudo com `pessoa` (nome e apelidos). O Ricardo confirma **em lote** ("este laudo é da Bia": uma tela com várias propostas, seleção e confirmar). Sem confirmação, o exame fica como proposta e **não** aparece no histórico.
- Duas pessoas com nomes parecidos ou nome ilegível: o brain não chuta; pede escolha.

### 3.4 Reprocessar
- O cofre guarda, por exame, o **id do documento no Paperless** e o hash do texto usado; o PDF nunca é copiado para o cofre. Reprocessar relê o PDF no Paperless e extrai de novo.
- Cada extração é uma **versão**: reprocessar cria versão nova e mantém a anterior; a tela mostra a versão mais recente e permite comparar.
- Gatilhos: um documento, um filtro (pessoa, laboratório, período) ou o lote inteiro; ao trocar regra ou modelo. Só quem tem acesso total à saúde dispara.
- Mudança de apelido de marcador: **reaplica** sem rodar o modelo de novo.
- Se o documento sumir do Paperless, os valores já extraídos continuam; só o reprocessamento daquele item fica indisponível, com aviso.

### 3.5 Tela "Saúde" (painel)
- **Por familiar:** tabela marcador × data (colunas por coleta), faixa de referência, destaque de fora da faixa (setinha e cor, com texto, não só cor).
- **Série:** um marcador no tempo (gráfico simples) com a faixa de referência sombreada.
- **Fila "A confirmar":** exames propostos esperando dono, em lote.
- **Visibilidade:** `matriz_acesso`; familiar com acesso parcial vê só a si mesmo. Cada abertura gera linha em `leitura` (quem, quando, o quê).
- **Fora do MCP:** o Hermes não lê valores de saúde (ADR-014). Pode saber só "há N exames novos a confirmar".

## 4. Dados
No cofre (`saude.enc`): `exame` ganha `doc_id`, `versao`, `qualitativo`, `observacao`; `marcador_apelido(apelido, marcador)`. No `gabi.db`: só a referência (id do documento, estado: novo/extraído/confirmado/falhou, versão). Migração `0022` (a 0021 é da escuta). Nada de valor de saúde no `gabi.db`.

## 5. Erros e segurança
- Sem chave do cofre ou do modelo: o timer não extrai e avisa; nada se perde (o PDF segue no Paperless).
- PDF protegido, corrompido ou sem texto legível: estado `falhou` com motivo; aparece no painel para o Ricardo.
- O modelo não tem ferramentas e só devolve JSON; instrução dentro do PDF é ignorada. CPF mascarado antes de enviar ao modelo. Teto e alerta de custo como no resto do brain.
- Logs não carregam valores de exame nem nome de paciente.

## 6. Testes e aceite
- Unidade (modelo falso): extração por regras, por modelo, qualitativo, JSON inválido descartado, injeção no PDF ignorada, normalização de marcador, dono ambíguo, reprocessar mantém a versão anterior, documento sumido.
- Varredura: teste que prova que nenhum valor de saúde existe no `gabi.db` e que o MCP não expõe exames.
- Painel (vitest): histórico, série, fila em lote, acesso parcial.
- **Aceite com dado real**: a lista do Ricardo (PDFs reais); medir quantos exames foram extraídos sem correção, quantos ele corrigiu, e conferir uma amostra à mão. Meta de qualidade a combinar na revisão.

## 7. Pendências do Ricardo
Subir a lista de PDFs (pasta `consume` ou docs@esper.ws) · confirmar donos em lote · conferir amostra · decidir a meta de acerto · confirmar que o Paperless pode restringir esses documentos ao dono.
