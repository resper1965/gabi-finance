# ADR-006 — Cobrança por e-mail: só rascunho na Fase 2

**Encerrada pela ADR-023 (22/10/2026):** a cobrança por e-mail saiu (tabelas vazias); fica a ferramenta `despesas_por_empresa`.

**Estado:** aceita (plano mestre, 08/10/2026).

## Contexto
As Decisões §2 (R2) dizem que o gabi.brain **não envia e-mail**. A cobrança de reembolso (ness, IONIC) precisa de um e-mail com a relação de despesas e os comprovantes.

## Decisão
O app **monta e guarda um rascunho** (`cobranca`/`cobranca_item`: destinatário, assunto, corpo com tabela e total, comprovantes confirmados como anexos, aviso dos itens sem comprovante) e o mostra no painel. `enviar` está desabilitado: a API responde 403 `nao_permitido`. O destinatário vem de `empresa.dados.email_cobranca` (cadastro, R6). Na Fase 3 o rascunho vai à caixa do usuário como **rascunho do provedor** (Graph `POST /me/messages`), nunca como envio.

## Consequência
Nenhum e-mail sai sem o Ricardo apertar enviar no próprio cliente de e-mail. `texto_confirmacao(c)` (`Enviar para <email>, N itens, R$ X, A anexos`) já existe, gerado no servidor, para o caso de o envio ser habilitado.

## Quando reverter
Só por ADR assinado pelo Ricardo que habilite o envio, com a confirmação textual obrigatória (409 se divergir) e idempotência por cobrança.
