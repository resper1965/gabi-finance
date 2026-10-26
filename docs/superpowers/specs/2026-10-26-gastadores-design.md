# Gastadores: quem gastou, separado de para quem foi

Data: 26/10/2026 · Estado: desenho aprovado pelo Ricardo em 26/10 (item 2 da lista de 26/10) · ADR a criar: 030

## O que o Ricardo disse
- Em Gastos, os "gastadores" se classificam pelos **portadores dos cartões**. Pessoas sem cartão não são gastadoras.
- Os cartões são todos dele; os portadores são **Louise, Giovanna, Sabrina e ele**.
- Nos cartões compartilhados, **"eu indico"** quem gastou: nada deduzido.
- Histórico dos compartilhados: fica **"a indicar"** (opção 1), sem copiar o "para quem".
- "Quem gastou" é separado de "para quem foi" (ele paga por várias pessoas: filhas, casa, pets, ex-esposas; ver memória favorecido-vs-para-quem).

## Fato que define o desenho
O Open Finance **não diz qual cartão físico** (titular ou adicional) fez a compra: as transações de cartão trazem só descrição, valor, categoria e parcelas (conferido nos brutos de outubro de todos os cartões). Logo, num cartão com 2+ portadores, só o Ricardo sabe quem gastou.

## Modelo
- Migração 0084: `lancamento.gastador_id text references pessoa(id)` e `lancamento.gastador_origem text check (gastador_origem in ('cartao','voce','regra'))`.
- **Portadores** = os `usuarios` de cada conta de cartão (cadastro de contas, já existe; editável em Cadastros). Dados atuais: Pão de Açúcar → sabrina; MC Black → ricardo, giovanna; LATAM → ricardo, louise; demais → ricardo. **Bradesco Platinum passa a ricardo, louise** (hoje vazio) — dado, gravado na instalação, não no código.
- Os gastadores possíveis são a união dos portadores dos cartões não excluídos (hoje: as 4 pessoas). Nada chumbado no código.

## Preenchimento (`gabi/dinheiro/gastador.py`, chamado ao fim da captura e no reaplicar do histórico)
1. Já tem `gastador_origem` 'voce' ou 'regra': não mexe.
2. Cartão com **um** portador: esse portador, origem 'cartao'.
3. Cartão com **2+** portadores: regra "sempre assim" de gastador para a loja, se houver (origem 'regra'); senão fica **vazio = a indicar**.
4. Conta corrente (Pix, boleto, débito): o usuário único da conta; sem usuário definido, a pessoa de papel `titular` (Ricardo). Origem 'cartao' (vem da conta).
5. Cartão sem portador cadastrado: fica a indicar (e a tela de Cadastros já mostra "Quem usa").
Só lançamentos de saída que são gasto (`natureza like '%custo%'`) contam nas telas; o campo é preenchido para todos.

## API
- `gastador_id` entra nos campos editáveis de `PATCH /lancamentos/{id}` e `POST /lancamentos/lote` (origem 'voce'; `null` volta a "a indicar" ou ao automático). Recusa (400) pessoa que não é portadora **daquela conta**.
- `GET /lancamentos?pendente=gastador`: compras de cartão compartilhado ainda a indicar.
- Cada lançamento traz `gastador: {id, nome, origem}` e `portadores: [ids]` da conta (para a tela oferecer só eles).
- "Sempre assim" (`criar_regra` no lote e `sempre_assim`) passa a levar o gastador decidido; a regra só vale em conta onde aquela pessoa é portadora.
- `GET /destino/agrupado?por=gastador`: "Quem gastou", com "(a indicar)" como linha própria. `por=pessoa` continua sendo "Para quem foi".

## Painel
- **Gastos › Lançamentos:** filtro "Quem gastou: a indicar"; em compra de cartão compartilhado, botões só com os portadores daquele cartão (ex.: Ricardo | Louise), um toque grava. O bloco de "para quem" segue igual.
- **Gastos › Cartões:** coluna "Quem gastou"; no lote, "Quem gastou: manter / <portadores>".
- **Para onde vai › Por pessoa:** duas leituras, "Quem gastou" (4 portadores + a indicar) e "Para quem foi" (como hoje).
- Contador do menu Gastos: soma os "a indicar".

## Hermes (escopo `fin`)
- `financeiro_indicar_gastador(lancamento_ids, pessoa)`: grava depois de mostrar as compras e ouvir o sim; recusa quem não é portador daquele cartão (`nao_portador`). Registra em `decisao` (origem hermes). Desfazer: indicar outro ou o painel.
- `financeiro_para_onde_vai(por="gastador")` responde "quanto a Louise gastou".
- `financeiro_lancamentos` traz o `gastador`; novo filtro `gastador` e `pendente="gastador"`.
- SOUL: "essa compra foi da Louise" → `financeiro_indicar_gastador`; nunca deduzir.

## Histórico
Instalação: cadastra o Bradesco como ricardo+louise, roda o preenchimento em todo o histórico (cartões de um portador e contas ficam resolvidos; compartilhados ficam a indicar). O "para quem" não é tocado. Antes/depois: contagem por gastador e quantos a indicar.

## Testes
- Preenchimento: um portador, compartilhado a indicar, regra de loja, conta corrente, não sobrescreve 'voce'.
- API: indicar, recusa de não portador, lote, `pendente=gastador`, agrupado por gastador, "sempre assim".
- Captura de ponta a ponta mantendo a indicação do Ricardo.
- MCP: indicar, `nao_portador`, escopo; lista oficial do Hermes e SOUL.
- Painel: botões só com portadores; filtro a indicar; aba Quem gastou.

## Fora
- Ler fatura em PDF para descobrir o adicional (decisão: "eu indico").
- Sugestão automática por histórico da loja nos compartilhados.
- Mudar "para quem".

## Desfazer
`alter table lancamento drop column gastador_origem; alter table lancamento drop column gastador_id; delete from schema_versao where nome='0084_gastador.sql';`, `git revert` do merge e reinstalar; Hermes: config e SOUL dos backups, restart e `/new`.
