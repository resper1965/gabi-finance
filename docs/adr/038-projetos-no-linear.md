# ADR-038 · Projetos no Linear; o brain guarda a pasta (dinheiro, fatos, anexos, documentos)

Data: 09/11/2026 · Estado: proposto (spec escrita, aguarda revisão do Ricardo; nada implementado) · Spec: `docs/superpowers/specs/2026-11-09-projetos-no-linear-design.md`

**Contexto.** O ADR-034 pôs a gestão de projetos dentro do brain ("tudo no brain, nenhuma ferramenta externa de projetos"), por causa do dinheiro. O Ricardo achou o painel pobre de dados e sem mobilidade (pesado no celular) e quer conduzir projetos ("vamos vender a fazenda") falando com o Hermes, com o projeto num gerenciador como o Linear.

**Decisão (tomada com o Ricardo em 09/11).**
1. **Projeto, etapas, dependências, prazos e marcos moram no Linear.** O Hermes fala com o MCP oficial do Linear direto, sem Composio (um intermediário a mais guardando token, sem ganho para um só app).
2. **O brain guarda a "pasta" do projeto:** orçamento e gastos, fatos, anexos, documentos (`paperless_id`) e pessoas, ligados ao projeto pelo `linear_id`.
3. **Sem espelho.** Nada é escrito nos dois lugares e não há sincronização. Se em um mês fizer falta, avalia-se um espelho de um sentido (Linear → brain, só leitura); espelho bidirecional foi recusado (conflito, duas fontes de verdade).
4. **Atividades soltas continuam no brain** (ADR-033), com aviso no Telegram. Regra do SOUL: faz parte de um projeto → Linear; é solto → brain; nunca nos dois.
5. **Só depois do sim do Ricardo** o Hermes cria projeto ou etapa no Linear (regra do fato afirmado). Linear fora do ar: o Hermes avisa e para; não cria no brain como plano B.

**Muda no ADR-034.** Substitui a decisão 1 e a linha "Fora: ferramenta externa de projetos". Mantêm-se as decisões de dinheiro, pessoas, documentos, anexos, fato só com sim e `projeto_parado`. Perdem efeito no uso do Hermes (código fica, fora do include): `projeto_criar` e dependência/marco em `atividade_criar` e `atividade_listar`.

**Consequências.** Os dados do plano passam a existir num serviço de terceiros (escolha do Ricardo). Duas fontes com papéis distintos, não espelhadas. Os avisos de etapa vêm do app do Linear, não do Telegram. A chave de API é colocada pelo Ricardo.

**Desfazer.** Restaurar `config.yaml.bak-antes-linear` e o SOUL, reiniciar `hermes-gateway`, `/new`; `git revert` do merge e `sudo ~/instalar-brain.sh`; a migração só acrescenta colunas; revogar a chave no Linear.
