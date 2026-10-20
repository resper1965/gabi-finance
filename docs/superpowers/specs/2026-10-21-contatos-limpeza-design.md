# Limpeza de contatos da ness: nome, telefone inválido e contato inútil (design)
Data: 21/10/2026 · Estende: ADR-020 (`2026-10-20-contatos-escrita-graph-design.md`) · Registra: ADR-021 (a escrever na implementação)

## Objetivo
Depois de aprovar as 50 propostas de criar/corrigir celular, o Ricardo achou sujeira que a regra de dígitos não pega. Quer que a Gabi **proponha** a limpeza, sempre com aprovação individual no painel, mesmo interruptor `contatos.escrita` e mesma fila `contato_proposta`. Nada vai ao Graph sem estado `aprovada`.

## Decisões do Ricardo (21/10)
1. **Nomes:** só limpar lixo (símbolos soltos como `⁹` e `|`, espaços duplicados, espaços nas pontas). Não mexe em caixa alta (NOFARO, LTB SAO PAULO são empresas) nem completa nomes.
2. **Inválidos:** 53 dos 62 "telefones inválidos" são números estrangeiros legítimos (+DDI ≠ 55) que o sincronizador recusa por só entender Brasil. Decisão: **ensinar o estrangeiro** e propor apagar só o que sobrar (código curto, malformado).
3. **Contato "U"** (nome de uma letra, +5511947338256): **apagar o contato**.

## Mudanças
### 1. Estrangeiro válido (sem escrita)
`gabi/escuta/contatos.py::_telefone`: sem `canonico` (o Graph não manda), aceita `+<DDI≠55><dígitos>` com 8 a 15 dígitos no total como E.164 sem converter para +55. Ramal, curto (≤ 7 dígitos) e texto continuam inválidos. Efeito: some da contagem de inválidos e passa a existir em `contato_graph.telefone`. O gerador de `corrigir` só olha `+55`, então estrangeiros não geram proposta.

### 2. Três tipos novos em `contato_proposta`
| tipo | quando propõe | o que escreve no Graph |
|---|---|---|
| `corrigir_nome` | o nome limpo difere do atual; nome limpo precisa ter ≥ 2 caracteres | só `displayName`; telefone igual no antes e no depois |
| `apagar_telefone` | `contato_graph.telefone is null` (ainda inválido depois do item 1) | limpa só aquele campo de telefone, com o valor `antes` conferido |
| `apagar_contato` | nome limpo com **1 caractere** e o contato não tem e-mail nem outro telefone além do que a proposta mostra | apaga o contato inteiro |

`apagar_telefone` apaga só o campo; o contato continua existindo, mesmo que fique sem telefone (apagá-lo é decisão do Ricardo, no Outlook). `apagar_contato` só nasce da regra do nome de 1 caractere.

Limpeza de nome (`_limpar_nome`): remove caracteres de `Unicode categoria S* e P*` que estejam soltos nas pontas ou isolados por espaço (`|`), troca sobrescritos/subscritos coladas à palavra (`⁹`) quando o contato **não** é uma sigla com dígito comum (`EMR3` não muda porque o `3` é ASCII), colapsa espaços e corta as pontas. Parênteses, hífen, ponto e apóstrofo **dentro** de nomes são preservados (`Antonio Américo (Tonico) ...`, `Gabriela Andrade - HomeCred`).

### 3. Aplicar (`contatos_gravar.py`)
Cada tipo ganha `_aplicar_*` no padrão dos existentes: revalida contra `contato_graph` (a linha lida ainda é a mesma: nome e telefone original), conta ainda em `escuta.contas_contatos`; divergência → `contato_alterado`; falha da ponte → `graph_indisponivel`; resultado `alterado` da ponte → `contato_alterado`. Sucesso: atualiza `contato_graph` local e marca `aplicada` na mesma transação. `apagar_contato` remove a linha de `contato_graph` (e o contato local de `contato_google` por telefone, se houver só ele).

### 4. Ponte (`graph_ness_contatos.py` + `ponte.py`)
Dois métodos novos, no mesmo arquivo da escrita de contatos: `contato_apagar_telefone(conta, graph_id, campo, antes_telefone)` e `contato_apagar(conta, graph_id, antes)`. Ambos releem o contato e só escrevem se nome e o campo conferem com o que o chamador viu; senão devolvem `{"resultado": "alterado"}`. `corrigir_nome` reaproveita `contato_corrigir` com o telefone igual no antes e no depois; **primeira tarefa do plano: confirmar no código que esse caminho aceita telefone inalterado** e, se não aceitar, acrescentar `contato_renomear`. Apagar contato usa `DELETE /users/{conta}/contacts/{id}` (a permissão `Contacts.ReadWrite` já cobre). Allowlist da ponte (`ponte.py:30`) ganha os nomes novos.

### 5. Painel
A aba Contatos lista os tipos novos com antes → depois (telefone original em `apagar_telefone`; nome e telefone em `apagar_contato`). O lote existente passa a aprovar `corrigir` **e** `corrigir_nome` mostrados na tela; **`apagar_telefone` e `apagar_contato` nunca entram em lote** (individual, com confirmação). Recusar aprovada continua valendo até a gravação.

### 6. Segurança
- Mesma trava `flock`, mesmo interruptor, mesma auditoria na transação da decisão. Log só com contagens; nenhum nome ou número.
- Apagar é irreversível no Graph da ness. Por isso: nunca em lote, revalidação estrita e ADR-021 registrando a exceção ao "sem apagar" da ADR-020.
- `aprovar_correcoes` só altera `tipo in ('corrigir','corrigir_nome')`.

### 7. Fora do escopo
Caixa alta, completar nomes incompletos, mesclar duplicados, apagar contato por qualquer outra regra, e-mail/endereço.

## Testes
Para cada tipo: gerar (positivo, negativo, idempotente, respeita `recusada/aplicada`), aplicar (ok, `contato_alterado`, `graph_indisponivel`, desligado = só simula), nunca em lote (apagar_*), `_limpar_nome` (⁹, `|`, EMR3, parênteses preservados), `_telefone` estrangeiro (+1, +44 válidos; ramal e curto inválidos), migração do `check` de `tipo`. Suíte completa em shards antes de instalar.

## Resultado esperado nos dados atuais (21/10)
`corrigir_nome`: 2 (José Rodrigo Carvalho⁹ ×2 contatos, Jaqueline Jurkovich |), `apagar_contato`: 1 (U), `apagar_telefone`: cerca de 9 (códigos curtos e malformados), estrangeiros (53) deixam de ser inválidos. Números exatos conferidos na primeira sincronização.
