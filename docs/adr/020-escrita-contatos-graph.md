# ADR-020 · Escrita de contatos da ness no Graph (criar e corrigir, só com aprovação)
Data: 20/10/2026 · Estado: aceito (código pronto na branch `feat/contatos-escrita`, nada ligado; passos do dono no runbook `#contatos-escrita`) · Spec: `docs/superpowers/specs/2026-10-20-contatos-escrita-graph-design.md` · Plano: `docs/superpowers/plans/2026-10-20-contatos-escrita-graph.md`

**Contexto.** O ADR-019 deixou os contatos da ness só de leitura. Em 20/10 o Ricardo pediu que a Gabi crie contatos que ainda não existem (quem escreveu pelo WhatsApp) e corrija celulares cujo número muda ao normalizar (tipicamente o celular antigo de 8 dígitos sem o 9) nos contatos da `resper@ness.com.br`. Isso é exceção explícita ao "só leitura" do ADR-019 e só vale para contatos; e-mail, agenda e Teams seguem como estavam.

**Decisões e razões.**
1. **Fila `contato_proposta` com aprovação individual no painel** (Escuta › Contatos). Nada vai ao Graph sem estado `aprovada`; quem decide é o dono (R1). Há um atalho para aprovar de uma vez as correções que estão na tela (o painel manda os ids exibidos; nunca as criações nem o que o dono não viu). Uma proposta aprovada pode ser recusada até ser gravada (`aprovada → recusada`); `recusada`, `aplicada` e `falhou` são finais.
2. **Gerador sem modelo** (`gabi/escuta/contatos_propostas.py`): regras fixas sobre `contato_graph` (o que o Graph devolveu, com o campo de origem) e as mensagens do WhatsApp. Só propõe `corrigir` para `campo='mobile'`, porque a escrita só toca `mobilePhone`, e só quando a normalização muda os DÍGITOS (dígitos do texto original sem o DDI 55 ≠ dígitos do E.164 sem `+55`); diferença só de formatação não vira proposta (evita centenas de propostas cosméticas). Número que não normaliza (ramal, DDI estranho) nunca vira proposta. A coluna `origem` continua `telefone_invalido` para as correções (nome histórico da migração 0072). Dado de terceiros nunca vai a log.
3. **Ponte com 2 métodos, sem apagar:** `contato_criar` e `contato_corrigir` em `graph_ness_contatos.py` (arquivo separado, para a varredura de `graph_ness.py` continuar valendo). Só `displayName` e `mobilePhone`. Antes de alterar, relê o contato e só escreve se nome e celular forem os que o chamador viu.
4. **Interruptor `contatos.escrita` desligado por padrão** (`parametro`; só o valor `"ligado"` liga). Desligado, o módulo só conta o que aplicaria e não chama o Graph.
5. **Trava e revalidação:** `flock` não bloqueante impede rodadas sobrepostas; antes de gravar, revalida contra o banco (as duas: a conta ainda está em `escuta.contas_contatos`?; criar: o remetente ainda está aprovado com o mesmo nome? o número já existe em algum contato já sincronizado, Graph ou Google, em qualquer conta?; corrigir: a linha lida ainda é a mesma?). Falhas viram `falhou` com motivo fixo, nunca texto de exceção.
6. **Auditoria na mesma transação da decisão** (quem, quando, o quê), sem nome nem número no log.
7. **Quando roda:** `ExecStartPost` do serviço `gabi-brain-contatos`, logo depois da sincronização; só contagens no log.

**Consequências e riscos aceitos.**
- O app `ness-automacao` tem `Contacts.ReadWrite` no tenant inteiro. A barreira é o código (conta só de `M365_CONTAS`, 2 métodos, dois campos, sem apagar) e a aprovação; a política de acesso do Exchange continua pendente com o administrador.
- Só o celular é corrigido; telefones fixos e de trabalho ficam de fora desta fase.
- Os métodos `contato_criar`/`contato_corrigir` da ponte não conferem aprovação: qualquer processo do grupo `gabibrain` com acesso ao socket do serviço de fontes poderia chamá-los para a conta da lista branca. Aceito (mesmo modelo de confiança do `move` do e-mail); as guardas de aprovação, interruptor e trava ficam no programa que aplica (`contatos_gravar`).
- Contato guardado numa subpasta de contatos do Outlook não vem no `/contacts` do Graph; a checagem de duplicata não o vê e criar o mesmo número pode duplicá-lo. Aceito.
- Contato só com e-mail não entra em `contato_graph` (não há o que corrigir).
- Resíduo: se o `POST` de criar der certo e as duas tentativas de gravar o resultado no banco falharem, a proposta pode ficar `aprovada`. O caminho agendado é protegido pela sincronização anterior (a criação aparece e a revalidação vira `ja_existe`); rodar o módulo à mão repetidas vezes nessa situação poderia recriar o contato.
- Um timeout da ponte pode marcar `graph_indisponivel` mesmo com a criação já feita (o mesmo resíduo acima).

**Fora desta fase.** Apagar e mesclar contatos, e-mail e endereço, escrita no Google, na IONIC, e aprovação por Hermes/MCP (a aprovação é só no painel).
