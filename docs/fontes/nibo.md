# Fonte: Nibo (API Empresa) — somente leitura no cliente `gabi/fontes/nibo.py`

- **Autenticação:** header `ApiToken` com o token em `NIBO_TOKEN` (`/etc/gabi-finance/nibo.env`, root 600, lido só pelo serviço de fontes; G8; plano Premium). Nunca `Authorization`; o token nunca entra em erro ou log.
- **Cliente (T2.3):** `Nibo.organizations/contas/agendamentos(desde_update, tipo)/extrato(conta, de, ate)/nfse(desde)/socios/clientes/categorias`. **Nenhum** método de escrita ou exclusão. Paginação OData: `$orderby` obrigatório, `$top=500`, `$skip`. Incremental por `updateDate`.
- **Rotas confirmadas com o token real (G8, 09/10/2026, só leitura):** `/partners` (sócios; 2 registros), `/customers` (clientes; 29), `/categories` (categorias; 26), além de `organizations` (3) e contas (3); paginação OData e formato `items` funcionam. Ainda NÃO verificadas com dado real: as rotas de escrita (agendamento, anexo, baixa) e o formato de resposta delas — só serão exercitadas no primeiro lote, com confirmação do Ricardo.
- **Erros:** 500 `{error, error_description}` e 400 `{message, messageDetail}` viram `ErroNibo("GET <rota> -> <status>: <detalhe>")`.
- **Gravação:** só no lote diário confirmado (T2.4, `cobrar/lote_nibo.py`), conforme abaixo.

---

# Nibo · API Empresa: o que o gabi-finance usa

Fonte: índice oficial https://nibo.readme.io/llms.txt (lido em 08/10/2026). Cada página tem a versão em markdown, com a definição OpenAPI, acrescentando `.md` à URL.
Base: `https://api.nibo.com.br/empresas/v1` · header `ApiToken: …` (nunca `Authorization`) · plano Premium · OData `$filter $orderby $skip $top`, até 500 por consulta, `$orderby` obrigatório para paginar · erros: 500 `{error, error_description}` e 400 `{message, messageDetail}`.

A API "Nibo Obrigações" (escritório contábil) **não se aplica**.

## Leitura (usar)
| Rota | Para quê no gabi-finance |
|---|---|
| `GET /organizations` | testar o token no setup; conferir o CNPJ da Bekaa; guardar `organizationId` |
| `GET /accounts` | achar a C6 PJ e guardar o `accountId` (`conta.nibo_account_id`) |
| `GET /accounts/{id}/views/statement?startDate&endDate` | extrato do Nibo: `scheduleId, entryId, stakeholderName, value, date, currentBalance, isReconciliated`. Conferência cruzada com o Open Finance |
| `GET /accounts/{id}/reconciliation` | o que o Nibo ainda não conciliou |
| Consultar saldo | saldo pelo Nibo, para conferência (rota a abrir) |
| `GET /schedules` | **leitura principal**: a pagar (`Debit`) e a receber (`Credit`), incremental por `updateDate`. Campos na Especificação de dados |
| `GET /nfse` | notas emitidas, base de Notas a receber (bruto, retenções, líquido) |
| Listar categorias · Hierarquia das categorias | mapear categoria do gabi-finance ↔ categoria do Nibo (`categoryId`) para o lote |
| Listar sócios · Listar clientes · Listar fornecedores | achar o `stakeholderId`: o sócio Ricardo (lote), ness e IONIC (clientes, por CNPJ) |
| Listar pagamentos / recebimentos realizados | "pagos e recebidos", se `GET /schedules` não bastar |

## Gravação (só no lote diário confirmado)
O lote diário é para despesa da Bekaa paga pelo PF. Na contabilidade, a PJ passa a **dever ao sócio**. Por isso **não** se usa "Criar pagamento" (que daria baixa numa conta da PJ que não pagou).

1. **Idempotência:** `GET /schedules?$filter=reference eq 'gabi:<lancamento_id>'`. Se já existir, pula.
2. **Criar agendamento de pagamento ao sócio:** `POST /schedules/debit/FormatType=json` com
   `stakeholderId` = sócio Ricardo · `value` · `dueDate` e `scheduleDate` = data do gasto · `accrualDate` = data do gasto · `categoryId` = categoria do Nibo equivalente · `description` = estabelecimento · `reference` = `gabi:<lancamento_id>`. Resposta: `scheduleId`.
3. **Anexar o comprovante:** `POST /files` (multipart, campo `file`, o PDF vindo do Paperless) devolve `[{fileId}]`. Depois `POST /schedules/debit/{scheduleId}/files/attach` com `["fileId"]` (resposta 204).
4. **Quando a PJ reembolsar o sócio** (Pix C6 PJ → Itaú PF visto no Open Finance), a Gabi **propõe** a baixa: `POST /schedules/debit/{scheduleId}/payments {accountId: C6 PJ, date, value, identifier}`. A baixa também exige confirmação.

Um erro num item não desfaz os outros. O item fica `erro` no `lote_nibo` e reprocessa sozinho no próximo lote, protegido pela `reference`.

## Proibido
Toda rota de **excluir** (conciliação, transferência, pagamento, recebimento, agendamentos, arquivos, contatos, centro de custo, anotação). Também: `PUT /accounts/{id}` e "Criar conta", criar ou atualizar cliente, fornecedor, sócio ou funcionário, criar categoria ou centro de custo, emitir ou cancelar NFS-e, criar ou cancelar cobrança, criar transferência, "Criar pagamento" e "Criar recebimento" diretos, atualizar agendamentos e "Criar item na caixa de entrada".

## A abrir antes de codar
Consultar saldo · Listar categorias e hierarquia · Listar sócios · Listar pagamentos e recebimentos realizados (campos exatos) · limite de chamadas por minuto (não documentado no índice).
