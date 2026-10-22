# ADR-025 · Cadastro familiar e documentos pessoais (exceções à ADR-023 e à R1)

Data: 22/10/2026 · Estado: aceito · Spec: `docs/superpowers/specs/2026-10-22-cadastro-familiar-design.md` · Plano: `docs/superpowers/plans/2026-10-22-cadastro-familiar.md` · Issues: #1, #3

**Contexto.** Em 22/10 o Ricardo pediu, na issue #1, que o Hermes saiba quem é a família e quais documentos cada pessoa tem, porque é "uma ação fundamental para um agente pessoal". Ele aceitou quebrar regras, desde que avisado. O histórico do Hermes mostra o caso real: "quando vence meu passaporte?" ficou sem resposta.

**Decisões.**
1. **Tabelas `pessoa_documento`, `pessoa_historico` e `pessoa_proposta`** (migração 0077). Os documentos que já estavam em `pessoa.dados` são copiados com `origem='legado'`, sem apagar o original.
2. **Escopo MCP `familia` no Hermes, com números completos, inclusive de menores.** O número só aparece em `familia_consultar` (ficha de uma pessoa), e cada consulta é registrada sem o número.
3. **Contato gravado direto** quando o Ricardo dita (telefone, e-mail, endereço, apelido, parentesco, nascimento), com histórico e desfazer. **Documento só por proposta** aprovada no painel.
4. **Carga inicial sem modelo:** expressões fixas sobre o OCR do Paperless geram propostas, e a leitura duvidosa vem marcada "conferir".
5. **Junto, da issue #3:** OCR do Paperless pelo MCP (`documentos_texto` e trecho na busca), resposta vazia explícita em todas as ferramentas, conflito explícito na ficha e o SOUL do Hermes versionado no repositório.

**Exceções aceitas pelo Ricardo.**
- **Dado sensível no canal.** Contraria o "CPF e afins nunca saem para o canal" e passa pelo provedor do modelo e pelo Telegram/WhatsApp.
- **R1 parcial.** O contato muda pelo que o Ricardo dita, sem clique depois.
- **ADR-023, regra do mês.** Três tabelas e um escopo novos sem o mês de uso manual.
- **ADR-023, corte de ontem.** Volta o acesso a dado sensível que tinha saído com `pessoas_dado`.

**Riscos aceitos.**
- Um texto de terceiro pode induzir o Hermes a propor um documento errado. Isso vira só proposta, visível no painel.
- A gravação direta de contato depende de o Hermes só conversar com o Ricardo (ADR-007). O valor anterior fica no histórico.

**Fora.** Alerta ou timer de vencimento, escrita no Paperless, extração por modelo, acesso `familia_vip`.
