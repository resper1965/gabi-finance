# ADR-021 · Limpeza de contatos da ness no Graph (renomear, apagar telefone, apagar contato, só com aprovação)
Data: 21/10/2026 · Estado: aceito (código na branch `feat/contatos-limpeza`; instalar é passo do dono) · Spec: `docs/superpowers/specs/2026-10-21-contatos-limpeza-design.md` · Plano: `docs/superpowers/plans/2026-10-21-contatos-limpeza.md` · Estende: ADR-020

**Contexto.** Depois de aprovar as propostas de criar/corrigir celular (ADR-020), o Ricardo achou sujeira que a regra de dígitos não pega: lixo no nome (`⁹`, `|`), telefones que o sincronizador chamava de inválidos e um contato de nome "U". A ADR-020 deixava "apagar" fora de escopo; esta ADR abre essa exceção, estreita e sempre aprovada contato a contato.

**Decisões e razões.**
1. **Três tipos novos na mesma fila `contato_proposta`** (migração 0073): `corrigir_nome`, `apagar_telefone`, `apagar_contato`. Mesma aprovação individual, mesmo interruptor `contatos.escrita`, mesmo aplicador, mesma trava e auditoria da ADR-020.
2. **Estrangeiro não é inválido.** 53 dos 62 "inválidos" eram números com DDI diferente de 55, que o sincronizador recusava por só entender Brasil. `_telefone` agora aceita `+DDI` (ou `00`) com 8 a 15 dígitos como está, sem converter para +55; ramal e curto continuam inválidos. Só sobra como `apagar_telefone` o que de fato não é número.
3. **Nome: só lixo.** `limpar_nome` tira sobrescrito/subscrito Unicode, símbolos da lista `|¦*_~^`\<>=` soltos ou nas pontas e espaço sobrando. Não mexe em caixa alta (NOFARO, LTB SAO PAULO), dígito comum (EMR3), hífen, parênteses, ponto, apóstrofo nem `&`. Lista explícita, não categoria Unicode, para não apagar o hífen solto de "Gabriela Andrade - HomeCred".
4. **Apagar contato só para nome de 1 caractere**, contato com um único telefone válido e sem e-mail. **Apagar telefone** só do campo cujo número não normaliza; os outros números do contato ficam.
5. **Apagar nunca entra em lote.** `aprovar_correcoes` só aprova `corrigir` e `corrigir_nome`; o painel pede confirmação extra para aprovar `apagar_*`.
6. **Ponte: três métodos novos** em `graph_ness_contatos.py` (`renomear`, `apagar_telefone`, `apagar`) com wrappers em `graph_ness.py` e allowlist em `ponte.py`. Todos releem o contato e só escrevem se o que o chamador viu ainda confere (`apagar` ainda confere que não ganhou e-mail nem 2º telefone); senão `alterado`, sem escrever. O único `DELETE` do código é o de apagar contato inteiro; `graph_ness.py` continua sem PATCH/PUT/DELETE.

**Consequências.** Apagar é irreversível no Graph da ness (não há lixeira de campo). Por isso a aprovação é individual e a revalidação, estrita. Com `contatos.escrita` ligado, aprovar já é decidir gravar: a gravação acontece na próxima rodada do timer ou no `systemctl start gabi-brain-contatos`.

**Fora do escopo.** Caixa alta, completar nomes incompletos, mesclar duplicados, apagar contato por outra regra, e-mail/endereço.
