# ADR-028 · Hermes completo: honestidade, família e frescor por ferramenta (Onda 1; Ondas 2 e 3 por referência)

Data: 25/10/2026 · Estado: aceito (Onda 1 pronta na branch `feat/hermes-onda1`, a instalar) · Spec: `docs/superpowers/specs/2026-10-25-hermes-completo-design.md` · Plano: `docs/superpowers/plans/2026-10-25-hermes-onda1.md`

**Contexto.** Em 24/10 o Ricardo ditou ao Hermes filhas, ex-esposas, companheira, mãe, pai, irmãos, sobrinhos e o Cookie. O Hermes respondeu "Anotado!" cerca de 15 vezes e não chamou nenhuma ferramenta de escrita. Não havia como criar pessoa nova nem pet. A ficha da família saía com "Dados até 14/10 (desatualizados)".

**Decisões (Ricardo, 25/10).**
1. Escopo em três ondas, cada uma com plano, merge e instalação próprios: (1) honestidade e família; (2) ver tudo, só leitura; (3) agir com aprovação.
2. **Privacidade é decisão do dono:** o dado sai completo para ele (números, telefones, e-mails); nada é mascarado por iniciativa do sistema. Logs, `chamada_mcp` e `decisao` continuam só com ids, campo e ação.
3. Ficam fora: leitura de PDF ou imagem pelo modelo, memória ou histórico semântico, correlação entre fontes.

**Exceções aceitas pelo Ricardo.**
- **ADR-023, regra do mês:** uma tabela nova (`receber_manual`, Onda 3) e cerca de 12 ferramentas MCP sem o mês de uso manual; a justificativa são os pedidos reais.
- **R1 parcial:** o que o Ricardo dita no chat é gravado direto, com histórico e Desfazer (já valia para contato, ADR-025; passa a valer para pessoa, pet e, na Onda 3, valor a receber, lixeira de e-mail e regra "sempre lixo"). Nada é gravado a partir de texto de terceiros.

**Correção da spec (achada ao planejar).** O "Dados até 14/10" não vinha de o Nibo contar no `dados_ate`: o Nibo está em `fontes.em_espera` e não conta. O Hermes leu a `ultima` do Nibo (14/10) na lista `fontes`. Além disso, `desatualizado` saía `True` por `bancos_antigos` (C6 Empresas). A solução continua a mesma: ferramenta sem fonte declarada recebe envelope sem `fontes`, sem `bancos_antigos` e com `desatualizado=False`.

**Onda 1: como ficou.**
- **Frescor por ferramenta:** `envelope(..., fontes=...)` com `servidor.FONTES_DA_FERRAMENTA`. Família, documentos e afins devolvem `desatualizado=False` e `fontes=[]`; `bancos_antigos` só vale quando `fontes` é None ou inclui open-finance. Teste garante que toda ferramenta registrada tem declaração.
- **Pessoa e pet:** `gabi/familia/pessoas.py` (`registrar_pessoa`, `registrar_pet`, `listar_pets`, `desfazer_especial`) sobre `contato._aplicar`; MCP `familia_registrar_pessoa` e `familia_registrar_pet` no escopo `familia` (31 ferramentas); rótulos "Pessoa criada: …" e "Pet: …" no painel. Histórico em `pessoa_historico` (pets em `pessoa_id='pets'`, `campo='pet:<id>'`), `decisao` com origem `familia`.
- **Regras de resolução:** registrar pessoa nunca casa por substring pura; pessoa sem `nome_completo` cujo `nome` é a(s) primeira(s) palavra(s) do nome ditado é a mesma pessoa, e `nome_completo` vazio é preenchido quando o ditado o estende; o slug só tem `[a-z0-9-]`. Desfazer uma 'criada' leva junto as linhas da mesma chamada (mesmo `quem` e `quando`); mudança posterior de outra chamada devolve `conflito`.
- **SOUL, "Gravar de verdade":** "anotado", "registrei", "salvei" e "guardei" só depois de ferramenta de escrita com ok, citando o que foi gravado; sem ferramenta, o Hermes diz que fica só na conversa.
- **Conferência de promessas:** `python -m tools.auditar_promessas [--desde YYYY-MM-DD]` lê `~/.hermes/state.db` em `?mode=ro` e lista as respostas com verbo de gravação sem escrita bem-sucedida (sem `"erro"`) do brain no mesmo turno. Rodado pelo assistente, sem timer; só vira timer depois de um mês com casos.

**Ondas 2 e 3 (por referência, cada uma com plano próprio).** Onda 2: contatos, a receber, avisos, Teams pendente, regras, decisões, empresas e leitura de e-mail (escopo `contatos` novo). Onda 3: `receber_manual` (migração 0082), e-mail para a lixeira e regra "sempre lixo" por pedido no chat. Detalhe na spec.

**Limites conhecidos.** Duas chamadas no mesmo segundo são indistinguíveis no Desfazer de 'criada'; o id de pessoa vem da primeira palavra ("Dr. João Silva" vira `dr`). A conferência de promessas é por verbo: pode marcar frase que só cita gravação e não perceber promessa sem esses verbos.

**Fora.** Timer da conferência; qualquer escrita no Paperless; envio externo (R2).
