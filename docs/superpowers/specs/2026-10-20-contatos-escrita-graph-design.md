# Escrita de contatos da ness no Graph, com aprovação (design)

Data: 20/10/2026 · Estado: aguardando revisão do dono · Relacionados: ADR-019 (Graph da ness, só leitura), `docs/fontes/graph-ness.md`, `gabi/escuta/contatos.py`.

## Objetivo
O brain propõe **criar** contatos novos e **corrigir** contatos existentes na conta `resper@ness.com.br` (Microsoft Graph). Nada é gravado sem a aprovação individual do dono, no painel. Isso abre uma exceção ao "só leitura" do ADR-019; a exceção precisa de uma trava tão forte quanto a da leitura.

## Fora do escopo
Apagar contato, mesclar duplicados, gravar e-mail/endereço/empresa, gravar em Google ou na IONIC, aprovação pelo Hermes ou por modelo, gerador com modelo de IA, número sem nome (não gera proposta).

## Dados
1. **Leitura ajustada.** `GraphNess.contatos` passa a devolver também o `id` do contato no Graph e o telefone original (hoje só nome, telefone e e-mails). A sincronização guarda isso em tabela nova `contato_graph(conta, graph_id, nome, telefone_original, telefone, atualizado_em)`. `contato_google`/`contato_google_email` não mudam.
2. **`contato_proposta`**: `id`, `tipo` (`criar`|`corrigir`), `conta`, `graph_id` (nulo em criar), `nome_antes`, `telefone_antes`, `nome_depois`, `telefone_depois`, `origem` (`whatsapp`|`telefone_invalido`), `estado` (`pendente`|`aprovada`|`recusada`|`aplicada`|`falhou`), `motivo`, `criada_em`, `decidida_em`, `decidida_por`, `aplicada_em`. Índice único parcial impede duas propostas ativas para o mesmo alvo.

## Gerador (sem modelo, depois da sincronização)
- **Criar:** `escuta_remetente` com estado `aprovado` e `nome` preenchido cujo número não existe em `contato_graph` nem em `contato_google` → proposta `criar` com nome e telefone E.164.
- **Corrigir:** contato em `contato_graph` cujo `telefone_original` hoje não vira E.164 válido, mas vira com a regra existente de normalização (`_telefone`/`normalizar_telefone`) → proposta `corrigir`. Quando a regra não produz número, o contato fica fora da fila.
  - *Revisão final (20/10):* a regra acima era um conjunto vazio (a sincronização já aplica a mesma normalização). Vale: celular (`campo='mobile'`) com nome e E.164 cuja normalização muda os DÍGITOS em relação ao `telefone_original` (sem DDI 55) → `corrigir`; só formatação não gera proposta. Ver ADR-020.
- Proposta `recusada` para o mesmo alvo e mesmo valor não é regerada. Se o valor muda, pode gerar de novo.

## Aplicação
- Comando `python -m gabi.escuta.contatos_gravar` roda após a sincronização (mesmo timer de contatos). Só processa `aprovada`.
- Antes de corrigir, relê o contato no Graph; se `displayName` ou o telefone mudaram desde a leitura da proposta, a proposta é descartada (`falhou`, motivo `contato_alterado`) e o gerador a refaz na rodada seguinte. Nunca sobrescreve edição do dono.
- Sucesso → `aplicada`; erro do Graph → `falhou` com motivo curto, sem dado pessoal.

## Trava (ponte `graph_ness`)
- Dois métodos novos na lista branca: `contato_criar`, `contato_corrigir`. Não existe método de apagar.
- Só a conta de `M365_CONTAS`; URL montada só como `/users/<conta>/contacts` (POST) ou `/users/<conta>/contacts/<id>` (PATCH), com `id` validado pelo formato do Graph vindo do banco.
- Corpo limitado a `displayName` e `mobilePhone`. Um teste varre o módulo e falha se houver DELETE ou outro campo.
- Interruptor `contatos.escrita` (`ligado`|`desligado`), nasce `desligado`; desligado, o comando de aplicação só lista o que aplicaria.
- O ADR-019 ganha a exceção por escrito (novo ADR-020 referenciado por ele).

## Painel (Escuta › Contatos)
Lista de propostas pendentes com antes/depois lado a lado, botões Aprovar e Recusar por linha e "aprovar todas as correções de telefone". Rotas só para o nível `boss`. Aprovação só pelo painel (nem Hermes nem MCP aprovam).

## Auditoria
Cada decisão e cada aplicação gravam id da proposta, tipo e login. Nunca nome nem telefone.

## Testes
- Gerador: criar, corrigir, recusada não repete, valor novo regera, número sem nome não gera.
- Ponte: URL, campos, ausência de DELETE, conta fora da lista recusada, id inválido recusado (HTTP falso, como nos testes atuais).
- Aplicação: aprovada grava, pendente não, interruptor desligado não grava, contato alterado descarta, falha do Graph vira `falhou`.
- Rotas: só boss, aprovar/recusar, aprovar em lote.

## Passos do dono depois de pronto
Instalar, rodar uma sincronização, revisar a fila no painel e só então ligar `contatos.escrita`.
