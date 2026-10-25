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
- **Pessoa e pet:** `gabi/familia/pessoas.py` (`registrar_pessoa`, `registrar_pet`, `listar_pets`, `desfazer_especial`) sobre `contato._aplicar`; MCP `familia_registrar_pessoa` e `familia_registrar_pet` no escopo `familia` (31 ferramentas); rótulos "Pessoa criada: …" (no desfazer, "Pessoa removida: …") e "Pet: …" no painel. Histórico em `pessoa_historico` (pets em `pessoa_id='pets'`, `campo='pet:<id>'`), `decisao` com origem `familia`.
- **Regras de resolução:** registrar pessoa nunca casa por substring pura. Sem casamento por igual ou começo de palavra, casa quem tem a mesma primeira palavra (no `nome`, no `nome_completo` ou no apelido) e todas as palavras ditadas entre as suas: "Louise Esper" é a "Louise Lavrik Esper", "Gigi Esper" é a Giovanna de apelido Gigi; "Chafic Esper" não é o "Ricardo … Esper" (primeira palavra diferente). Pessoa sem `nome_completo` cujo `nome` é a(s) primeira(s) palavra(s) do ditado também é a mesma, e o `nome_completo` vazio é preenchido quando o ditado o estende. Mais de uma: `pessoa_ambigua`, com candidatos no formato "Sandra (Sandra Maria Esper)" quando há nome completo. O slug só tem `[a-z0-9-]`.
- **Titular e apelido:** a linha com `papel='titular'` (o Ricardo) nunca é escrita por `registrar_pessoa`; se a resolução cair nela, volta `pessoa_ambigua` com ela de candidata e o Hermes pergunta. Se só o apelido casar e a primeira palavra do nome ditado não estiver entre as palavras da pessoa, também volta `pessoa_ambigua` em vez de juntar. O resultado traz `nome` e `nome_completo` de quem foi gravado.
- **Desfazer 'criada':** leva junto as linhas da mesma chamada (mesmo `quem` e `quando`). Dá `conflito` só se algum campo tocado depois da criação (por linha desfeita ou não) não estiver nem no valor que a criação gravou nem vazio; mudança posterior já desfeita não bloqueia, mudança posterior que ficou bloqueia. As linhas posteriores ficam como estão (a exclusão não mexe em `dados`).
- **Leituras e legado:** `familia_consultar` e `familia_listar` trazem `nome_completo`, `falecido` e `observacao`. Pet da carga antiga com `tutor`/`aniversario` é lido como `dono`/`nascimento` quando as chaves novas faltam; gravar escreve as novas e deixa as antigas. O histórico do painel traz até 200 linhas.
- **SOUL, "Gravar de verdade":** "anotado", "registrei", "salvei" e "guardei" só depois de ferramenta de escrita com ok, citando o que foi gravado; sem ferramenta, o Hermes diz que fica só na conversa.
- **Conferência de promessas:** `python -m tools.auditar_promessas [--desde YYYY-MM-DD]` lê `~/.hermes/state.db` em `?mode=ro` e lista as respostas com verbo de gravação sem escrita bem-sucedida do brain no mesmo turno. O Hermes guarda o resultado embrulhado (`<untrusted_tool_result …>`, aviso e `{"result": "<json do brain em texto>"}`); a conferência tira o embrulho, decodifica as duas camadas e só conta como falha a chave `erro` no topo (sem decodificar, uma regex só da chave), nunca um valor como `"estado": "erro"`. Rodado pelo assistente, sem timer; só vira timer depois de um mês com casos.

**Ondas 2 e 3 (por referência, cada uma com plano próprio).** Onda 2: contatos, a receber, avisos, Teams pendente, regras, decisões, empresas e leitura de e-mail (escopo `contatos` novo). Onda 3: `receber_manual` (migração 0082), e-mail para a lixeira e regra "sempre lixo" por pedido no chat. Detalhe na spec.

**Limites conhecidos.** Duas chamadas no mesmo segundo são indistinguíveis no Desfazer de 'criada'; o id de pessoa vem da primeira palavra ("Dr. João Silva" vira `dr`). A conferência de promessas é por verbo: pode marcar frase que só cita gravação e não perceber promessa sem esses verbos.

**Fora.** Timer da conferência; qualquer escrita no Paperless; envio externo (R2).
