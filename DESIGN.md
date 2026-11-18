---
name: gabi.finance
description: Painel pessoal de dinheiro como laudo pericial. Papel frio, tinta azul-grafite, regras finas de 1px e estados em carimbo; todo valor-chave carrega um código de evidência.
colors:
  papel: "oklch(0.962 0.008 170)"
  folha: "oklch(0.985 0.004 170)"
  papel-2: "oklch(0.935 0.011 170)"
  papel-3: "oklch(0.905 0.013 170)"
  tinta: "oklch(0.27 0.032 255)"
  tinta-2: "oklch(0.44 0.026 250)"
  tinta-3: "oklch(0.51 0.02 245)"
  regra: "oklch(0.87 0.012 190)"
  regra-forte: "oklch(0.7 0.016 220)"
  acento: "oklch(0.45 0.115 255)"
  acento-hover: "oklch(0.39 0.11 255)"
  sobre-acento: "oklch(0.985 0.004 170)"
  acento-fundo: "oklch(0.92 0.03 250)"
  foco: "oklch(0.52 0.15 255)"
  selecao: "oklch(0.85 0.06 250)"
  trilho: "oklch(0.235 0.014 240)"
  trilho-2: "oklch(0.29 0.016 240)"
  trilho-regra: "oklch(0.35 0.016 240)"
  trilho-tinta: "oklch(0.9 0.01 200)"
  trilho-tinta-2: "oklch(0.74 0.014 220)"
  carimbo-vermelho: "oklch(0.5 0.17 25)"
  carimbo-vermelho-fundo: "oklch(0.95 0.025 25)"
  carimbo-verde: "oklch(0.46 0.1 155)"
  carimbo-verde-fundo: "oklch(0.95 0.03 155)"
  carimbo-azul: "oklch(0.46 0.13 255)"
  carimbo-azul-fundo: "oklch(0.94 0.03 250)"
  carimbo-grafite: "oklch(0.42 0.025 250)"
  ambar: "oklch(0.88 0.12 90)"
  ambar-borda: "oklch(0.6 0.12 75)"
  ambar-tinta: "oklch(0.33 0.07 65)"
  ambar-fundo: "oklch(0.955 0.045 92)"
  serie-1: "oklch(0.34 0.06 255)"
  serie-2: "oklch(0.47 0.08 252)"
  serie-3: "oklch(0.6 0.075 248)"
  serie-4: "oklch(0.73 0.055 245)"
  serie-5: "oklch(0.83 0.035 240)"
  entrada-1: "oklch(0.52 0.09 165)"
  entrada-2: "oklch(0.74 0.07 165)"
  emp-ness: "oklch(0.58 0.12 230)"
  emp-ionic: "oklch(0.53 0.13 305)"
  emp-bekaa: "oklch(0.66 0.13 65)"
  emp-pessoal: "oklch(0.55 0.015 240)"
typography:
  conclusao:
    fontFamily: "Public Sans Variable, Public Sans, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 450
    lineHeight: 1.32
    letterSpacing: "-0.018em"
  pergunta:
    fontFamily: "Public Sans Variable, Public Sans, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-0.015em"
  sentenca:
    fontFamily: "Public Sans Variable, Public Sans, system-ui, sans-serif"
    fontSize: "1.3125rem"
    fontWeight: 450
    lineHeight: 1.38
    letterSpacing: "-0.012em"
  secao:
    fontFamily: "Public Sans Variable, Public Sans, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.005em"
  valor:
    fontFamily: "Public Sans Variable, Public Sans, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 650
    lineHeight: 1.5
    fontFeature: "'tnum' 1, 'lnum' 1"
  corpo:
    fontFamily: "Public Sans Variable, Public Sans, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  meta:
    fontFamily: "Public Sans Variable, Public Sans, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.45
  carimbo:
    fontFamily: "Public Sans Variable, Public Sans, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 700
    lineHeight: 1.45
    letterSpacing: "0.07em"
  codigo:
    fontFamily: "JetBrains Mono, ui-monospace, SF Mono, Menlo, monospace"
    fontSize: "0.6875rem"
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: "0em"
rounded:
  carimbo: "1px"
  base: "2px"
spacing:
  e1: "4px"
  e2: "8px"
  e3: "12px"
  e4: "16px"
  e5: "24px"
  e6: "32px"
  e7: "48px"
components:
  button:
    backgroundColor: "{colors.folha}"
    textColor: "{colors.tinta}"
    typography: "{typography.corpo}"
    rounded: "{rounded.base}"
    padding: "0 12px"
    height: "34px"
  button-hover:
    backgroundColor: "{colors.papel-2}"
  button-primary:
    backgroundColor: "{colors.acento}"
    textColor: "{colors.sobre-acento}"
    rounded: "{rounded.base}"
    padding: "0 12px"
    height: "34px"
  button-primary-hover:
    backgroundColor: "{colors.acento-hover}"
  button-ghost:
    backgroundColor: "{colors.papel}"
    textColor: "{colors.acento}"
    rounded: "{rounded.base}"
    padding: "0 8px"
    height: "34px"
  field:
    backgroundColor: "{colors.folha}"
    textColor: "{colors.tinta}"
    typography: "{typography.corpo}"
    rounded: "{rounded.base}"
    padding: "0 10px"
    height: "34px"
  segmented-option-selected:
    backgroundColor: "{colors.tinta}"
    textColor: "{colors.papel}"
    padding: "0 12px"
    height: "32px"
  stamp:
    backgroundColor: "{colors.papel}"
    textColor: "{colors.carimbo-grafite}"
    typography: "{typography.carimbo}"
    rounded: "{rounded.carimbo}"
    padding: "1px 6px 0"
  stamp-conferir:
    backgroundColor: "{colors.ambar}"
    textColor: "{colors.ambar-tinta}"
    typography: "{typography.carimbo}"
    rounded: "{rounded.carimbo}"
  evidence-code:
    backgroundColor: "{colors.papel}"
    textColor: "{colors.tinta-2}"
    typography: "{typography.codigo}"
    rounded: "{rounded.carimbo}"
    padding: "0 4px"
  rail-item-current:
    backgroundColor: "{colors.papel}"
    textColor: "{colors.tinta}"
    height: "40px"
  notice:
    backgroundColor: "{colors.folha}"
    textColor: "{colors.tinta}"
    rounded: "{rounded.base}"
    padding: "12px 14px"
---

# Design System: gabi.finance

## Overview

**Creative North Star: "O Laudo Pericial"**

O painel é um laudo do dinheiro, não um app de banco. Cada número é evidência: carrega código de item, fonte, rodada e conferência, e cada estado é um carimbo com texto. O chão é papel de laudo frio (cinza-esverdeado claro), a tinta é azul-grafite, e o trilho de navegação é um grafite-toner profundo que ancora a página como a lombada de um processo.

A densidade é de sessão de revisão no computador: tabelas pautadas por regras de 1px, listas com linhas finas, uma frase grande de conclusão no topo e achados numerados abaixo. Nada flutua e nada decora. A hierarquia vem de peso, tamanho e regra, não de cartões, sombras ou cor. A única cor que chama atenção é a que significa estado: vermelho, verde, azul de nota e o âmbar de "a conferir".

O sistema funciona nos dois temas (claro por padrão, escuro pelo `data-theme` ou pela preferência do sistema) com os mesmos papéis de cor; texto com contraste mínimo de 4,5:1 nos dois, verificado por teste.

**Key Characteristics:**
- Papel frio, tinta azul-grafite, trilho grafite; acento azul único para ação.
- Estados como carimbos de régua dupla, em caixa alta, sem rotação; o texto sempre diz o estado, a cor nunca vai sozinha.
- Etiqueta de evidência (código de item + quadro de proveniência) em todo valor-chave.
- Sans única de documentação técnica; mono só para códigos, horários, datas curtas e número de rodada.
- Regras finas de 1px, cantos de 1px a 2px, sem sombra de cartão.
- Algarismos tabulares em todo valor.

## Colors

Paleta de papel e tinta com uma só cor de ação e quatro cores de estado, cada uma com fundo suave próprio. Todos os valores são OKLCH, definidos em `painel/src/tema/tokens.css`; o escuro reaproveita os mesmos papéis (valores no sidecar).

### Primary
- **Azul de Ação** (`acento`, oklch(0.45 0.115 255)): botão primário, links, caret, marcação de linha selecionada (com `acento-fundo`), barras do ranking. `acento-hover` escurece no hover. O anel de foco usa `foco`, um azul mais vivo.

### Neutral
- **Papel de Laudo** (`papel`): fundo da página e do cabeçalho.
- **Folha** (`folha`): superfície de campo, tabela embutida, painel, quadro e faixa de proveniência; um passo mais clara que o papel.
- **Papel Sombreado** (`papel-2`, `papel-3`): hover e linha em foco; trilho de barra e esqueleto.
- **Tinta** (`tinta`, `tinta-2`, `tinta-3`): texto principal, secundário e rótulo de eixo/legenda.
- **Regra** (`regra` 1px fina, `regra-forte` para cabeçalho de tabela e borda de campo).
- **Grafite de Trilho** (`trilho`, `trilho-2`, `trilho-regra`, `trilho-tinta`, `trilho-tinta-2`): navegação lateral, barra inferior no celular e toast. O item atual vira "aba de papel": fundo `papel`, texto `tinta`.

### Tertiary (estados)
- **Carimbo Vermelho** (`carimbo-vermelho`): atrasado, divergente, perigo, selo de contagem.
- **Carimbo Verde** (`carimbo-verde`): pago, conferido, interruptor ligado, "termina neste mês".
- **Carimbo Azul** (`carimbo-azul`): nota e projeção.
- **Carimbo Grafite** (`carimbo-grafite`): atenção neutra, carimbo padrão.
- **Âmbar de Etiqueta** (`ambar`, `ambar-borda`, `ambar-tinta`, `ambar-fundo`): somente o que está "a conferir", incluindo sugestão da Gabi, "sem dono" e faixa de dados desatualizados.
- Cada estado tem um `-fundo` suave para quadros de aviso.

### Gráficos
- **Séries** (`serie-1` a `serie-5`): rampa azul-grafite, escura a clara, para barras compostas e linha de saldo.
- **Entradas** (`entrada-1`, `entrada-2`): verde-azulado para o que entra.
- **Empresas** (`emp-ness`, `emp-ionic`, `emp-bekaa`, `emp-pessoal`): uma cor por dono do gasto, sempre ao lado de rótulo em texto.

### Named Rules
**A Regra do Âmbar Único.** O âmbar significa "a conferir" e nada mais. Não vira destaque, decoração nem aviso genérico.

**A Regra do Texto no Estado.** Cor nunca carrega estado sozinha: todo estado é um carimbo com palavra (ATRASADA, CONFERIDO, A CONFERIR, PROJEÇÃO).

**A Regra do Acento Único.** O azul de ação é a única cor de interação. Estado e ação não compartilham matiz de significado.

## Typography

**Display e Body Font:** Public Sans Variable (com Public Sans, system-ui, sans-serif). Escolhida por ter cara de formulário oficial e `tnum`/`lnum`.
**Label/Mono Font:** JetBrains Mono (400, 500), só em código de item, horário, data curta e número de rodada.

**Character:** Uma sans de documentação técnica faz tudo, do H1 ao rodapé de tabela; o contraste vem de peso (400 a 700) e tamanho, e a mono marca o que é registro, não prosa. Escala fixa em rem, razão ~1,14.

### Hierarchy
- **Conclusão** (450, 1.75rem/28px, 1.32, -0.018em): a frase de conclusão do Resumo, até 36em; 700 nos trechos-chave.
- **Pergunta** (650, 1.5rem/24px, 1.2, -0.015em): H1 de cada tela, escrito como pergunta; sem rótulo acima.
- **Sentença** (450, 1.3125rem/21px, 1.38, -0.012em): frase de conclusão de cada tela interna.
- **Seção** (650, 1.125rem/18px, 1.25): título de seção e valor de achado.
- **Valor/Título de item** (650, 1rem/16px): valor de linha, nome do lançamento.
- **Corpo** (400, 0.875rem/14px, 1.5): texto, tabelas, botões (600).
- **Meta** (400, 0.75rem/12px, 1.45): legenda, prova do achado, cabeçalho de tabela (600), notas de até 70 a 75ch.
- **Carimbo** (700, 0.6875rem/11px, 0.07em, caixa alta): somente carimbos de estado.
- **Código** (mono 500, 0.6875rem/11px): código de item (RS-01, AP-02).

### Named Rules
**A Regra do Registro em Mono.** Mono é só para o que é registro: código de item, horário, data curta, rodada, chave. Valor monetário e prosa ficam em sans.

**A Regra do Tabular.** Todo valor usa `tabular-nums lining-nums`; coluna de número alinha à direita.

**A Regra da Caixa Alta de Carimbo.** Caixa alta com espaçamento é do carimbo de estado. Rótulo de seção, grupo e campo é frase em caixa normal, 600.

## Layout

Casca de duas colunas: trilho grafite fixo (232px, recolhe para 60px) e coluna principal com cabeçalho fixo (H1 como pergunta, ações, abas ARIA), faixa de proveniência logo abaixo e conteúdo que rola dentro de `.conteudo`. A página tem até 1360px, padding 24px 32px, ritmo vertical de 28px entre seções; blocos internos usam a escala de 4 a 48px (`e1` a `e7`).

O Resumo é uma folha de rosto em duas colunas (conteúdo e lateral de 380px, folga 28px 44px): conclusão, achados numerados, saldo por banco; à direita, pendências e gráfico. Telas de laudo usam `grade-laudo` (lateral de 340px, gap 32px 40px); pares usam `grade-2` com `auto-fit` a partir de 420px. Abaixo de 1180px tudo vira coluna única.

No celular (`data-celular`, 390px): trilho vira barra inferior grafite de 58px com "Mais"; padding 18px 14px; a faixa de proveniência cabe numa linha, sem fontes nem próxima rodada; a tabela de achados vira grade de três colunas por item, com carimbo e ação na segunda linha; alvos de toque de 40px. Ordem no Resumo: conclusão, achados, pendências, gráfico, bancos.

Densidade vem de listas pautadas (linha de 1px, padding vertical 10 a 14px), não de cartões. Sem grades de cartões do mesmo tamanho.

## Elevation & Depth

Plano por padrão. A profundidade é tonal (papel, folha, papel-2) e linear (regra de 1px, regra de 2px na tinta sob o cabeçalho de seção, regra dupla no carimbo). Nenhuma superfície em repouso tem sombra.

### Shadow Vocabulary
- **Camada** (`--sombra-camada`: `0 6px 20px -6px oklch(0.25 0.03 250 / 0.28), 0 1px 3px oklch(0.25 0.03 250 / 0.12)` no claro; `0 8px 24px -6px oklch(0 0 0 / 0.55), 0 1px 3px oklch(0 0 0 / 0.4)` no escuro): só para o que flutua sobre a página: quadro de evidência, painel de avisos, menu, toast.
- **Anel de foco de campo** (`0 0 0 2px` de `foco` a 35%): foco de campo e busca.

### Named Rules
**A Regra do Plano em Repouso.** Superfícies em repouso são planas. Sombra só em camadas que flutuam, nunca em cartão, tabela ou botão.

## Shapes

Quase retilíneo, como formulário impresso. Raio base de 2px (`--raio`) para botão, campo, painel, quadro e menu; 1px para carimbo, código de item e etiqueta. Nada de canto arredondado grande. Bordas de 1px em `regra-forte` (controles) ou `regra` (linhas); o carimbo de estado usa borda dupla de 3px. Quadros de aviso têm borda inteira na cor do estado, nunca faixa lateral grossa. Estado vazio usa borda tracejada de 1px. Sem marcas de canto e sem rotação.

## Components

### Buttons
- **Shape:** retilíneo (2px), 34px de altura, `0 12px`, 600 em 14px, sem sombra.
- **Padrão:** fundo `folha`, borda `regra-forte`; hover `papel-2` com borda `tinta-3`; ativo `papel-3`.
- **Primary:** fundo e borda `acento`, texto `sobre-acento`; hover `acento-hover`. Uma ação primária por pendência.
- **Ghost:** transparente, texto `acento`, hover `acento-fundo`. Também `.btn-sm` (28px) e `.btn-icon` (34px).
- **Perigo:** texto `carimbo-vermelho`. Desabilitado: opacidade 0,5.
- Foco: anel de 2px em `foco`, deslocado 2px.

### Inputs / Fields
- **Style:** `folha`, borda `regra-forte` 1px, 2px de raio, 34px de altura, rótulo acima em 12px 600 `tinta-2`.
- **Hover:** borda `tinta-3`. **Focus:** borda `foco` mais anel de 2px a 35%.
- **Busca:** campo com ícone lucide, foco no contêiner. Checkbox e rádio com `accent-color` no acento.

### Controle segmentado e chips
- **Segmentado** (período, filtros, é gasto/não é gasto): borda `regra-forte`, divisores `regra`; opção selecionada preenche com `tinta` e texto `papel`, 600, `aria-pressed`.
- **Chip** (escolha de pessoa): 30px, mesma lógica, selecionado em `tinta`; sugerido pela Gabi em `ambar-fundo`; setas, Home e End navegam entre chips.

### Carimbo (assinatura)
- **Estado:** régua dupla de 3px na cor do estado, 1px de raio, caixa alta 11px 700 com 0,07em, sem fundo, sem rotação, sem emoji ou glifo.
- **Tipos:** `erro` vermelho (ATRASADA, DIVERGENTE), `ok` verde (PAGO, CONFERIDO), `nota` azul (NOTA, PROJEÇÃO), `atencao` grafite, `conferir` etiqueta âmbar preenchida (A CONFERIR).
- **Origem** (`banco`, `regra`, `parado`, `paperless`, `ajuste`): régua simples de 1px em `regra-forte`, texto `tinta-2`; não é estado.
- Feminino consistente no texto; carimbo vai depois do item que descreve, não como título de grupo.

### Etiqueta de evidência (assinatura)
- **Código:** `ev-cod`, mono 11px em caixa de 1px com borda `regra-forte`. Prefixos estáveis por tela: RS (Resumo), AP (A pagar), PV (Previsão), SM (Semanas), PO (Para onde vai), CT (Cartões), PC (Parcelas), AS (Assinaturas), NT (Notas). O Resumo cita os códigos que soma (RS-02 = AP-01 + AP-02 + AP-03).
- **Estado do código:** `a_conferir` pinta o código de âmbar; no hover, foco ou toque o código inverte para `tinta` sobre `papel`.
- **Quadro:** `role="tooltip"` por portal, `position: fixed`, 340px, `folha`, sombra de camada; abre com 260ms de pausa no hover, no foco e no toque; Esc, rolagem ou redimensionamento fecham. Mostra a cadeia Fonte (uma linha por fonte) → Rodada (dados até, próxima) → Conferência com carimbo.

### Achados e listas pautadas
- **Achados:** tabela numerada com cabeçalho de `regra` na tinta; colunas código (mono), rótulo 600, valor 650 à direita, prova em 12px `tinta-2`, carimbo de conferência (todo achado tem um), ação. No celular vira grade de três colunas.
- **Pauta:** `<ul>` com linha de 1px; linha marcada em `acento-fundo`; painel embutido na linha (`linha-painel`) para confirmar e editar.
- **Tabela:** cabeçalho 12px 600 com regra forte, células com padding 10px 12px, primeira e última coluna sem padding externo, rodapé com regra na tinta.

### Navigation
- **Trilho:** grafite, itens de 40px, ícones lucide, selos vermelhos de contagem; atual = aba de papel; recolhível (`data-mini`). Grupos em frase 600 `trilho-tinta-2`.
- **Abas:** ARIA com setas; ativa em 650 com sublinhado de 2px na `tinta`.
- **Faixa de proveniência:** linha fixa sob o cabeçalho com até quando, rodada e conferência (ex.: "CONFERIDA 08/10 14:00"); vira âmbar quando desatualizado.

### Quadros e estados
- **Quadro de aviso:** borda inteira e fundo suave do tom (erro, ok, conferir, nota), ícone lucide no início.
- **Vazio:** borda tracejada que diz o que fazer. **Carregando:** esqueleto com varredura de 1,4s. **Erro:** caixa vermelha.
- **Interruptor, menu, toast:** interruptor liga em `carimbo-verde`; menu com Esc; toast grafite com sombra de camada.
- **Movimento:** 150 a 180ms, curva `cubic-bezier(0.16, 1, 0.3, 1)`; `surge` de 3px para camadas; `prefers-reduced-motion` zera tudo.

## Do's and Don'ts

### Do:
- **Do** dar a todo valor-chave um código de item e a cadeia de proveniência (fonte, rodada, conferência), com código estável por tela.
- **Do** expressar todo estado como carimbo com texto; use `conferir` (âmbar) para qualquer valor sem fonte ou ainda não conferido.
- **Do** manter a tela como pergunta (H1) e uma frase de conclusão, seguida de achados com prova e ação primária.
- **Do** usar regra de 1px e tom de papel para separar; hierarquia por peso e tamanho da escala fixa.
- **Do** usar `tabular-nums` em todo valor e alinhar números à direita.
- **Do** usar ícones lucide (SVG) e esconder valores quando o modo privacidade está ligado.
- **Do** reservar a sombra de camada para o que flutua e respeitar `prefers-reduced-motion`.

### Don't:
- **Don't** usar cartões com sombra, grades de cartões do mesmo tamanho ou número grande com gráfico decorativo; o painel recusa o app de banco digital.
- **Don't** usar âmbar para destaque ou aviso genérico; ele é só "a conferir".
- **Don't** deixar a cor sozinha no estado, nem usar glifos Unicode ou emoji no lugar de ícone ou texto.
- **Don't** usar mono em valor monetário ou prosa.
- **Don't** usar caixa alta espaçada como rótulo de seção, grupo ou campo; ela é do carimbo.
- **Don't** usar borda lateral grossa, gradiente em texto, vidro ou sombra deslocada; nem girar carimbos.
- **Don't** usar cantos arredondados grandes; o teto é 2px (1px para carimbo e código).
- **Don't** repetir no título de grupo o estado que a linha já carimba.
