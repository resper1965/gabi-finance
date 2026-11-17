# Painel (React)

O painel é a interface do Ricardo: uma aplicação React 19 + TypeScript + Vite em `painel/`, com testes em vitest. Ele é **servido pela própria API** (`gabi.api` monta a pasta compilada `gabi/painel/` em `/`) e só é alcançado pelo `tailscale serve`; não existe login no painel, a identidade vem do cabeçalho `Tailscale-User-Login` (ADR-003, ADR-007). Se a pasta compilada não existir, a API cai numa página de verificação simples.

## Como rodar

```
cd painel
npm ci                  # dependências travadas por package-lock.json
npx vitest run          # testes (jsdom); `npm test` faz o mesmo
npm run build           # tsc --noEmit + vite build, saída em ../gabi/painel (ignorada pelo git)
npm run analisar        # falha se algum JS do build passar de 150 KB gzip
npm run dev             # servidor de desenvolvimento; o proxy manda /api para 127.0.0.1:8000
```

No desenvolvimento, suba a API local com `GABI_PERMITE_TCP_LOCAL=1` (a API normalmente só aceita socket Unix, R3) e as origens do painel em `GABI_ORIGENS_CONFIAVEIS` (proteção CSRF). No servidor, o `instalar.sh` **não** roda npm: ele copia a pasta `gabi/` inteira, inclusive `gabi/painel/`. Por isso o painel precisa estar compilado no clone ANTES de instalar (`cd painel && npm ci && npm run build`); sem isso a API sobe, mas mostra só a página de verificação.

## Navegação

O painel tem dois grupos e seis áreas (`painel/src/navegacao.ts`, uma única fonte para o menu e para os links dos avisos):

| Grupo | Área | Abas | Pergunta que responde |
|---|---|---|---|
| Dinheiro | **Caixa** | A pagar, Previsão, Semanas, Resumo | Tenho caixa? O que vence? |
| Dinheiro | **Gastos** | Lançamentos, Para onde vai, Cartões, Parcelas, Assinaturas | Para onde vai o dinheiro? |
| Dinheiro | **Cobrar** | A receber, Notas a receber | Quem me deve? |
| Dinheiro | **Regras** | Regras | O que a Gabi sugere classificar? |
| Cadastros | **Cadastros** | Cadastros, Despesas | O que a Gabi sabe, e o que só você sabe? |
| Cadastros | **Gabi** | Agentes | Quais agentes meus acessam a Gabi? |

As áreas de trabalho, projetos, atividades, envios, contatos, correio, documentos, Teams e a de qualidade do assistente **saíram no corte** junto com o que as alimentava. Um endereço antigo dessas áreas cai no Caixa (`rotaParaTela`).

## Telas e a API que cada uma usa

Toda chamada é `GET/POST/PATCH/DELETE /api/v1/...` e devolve o envelope com `dados_ate` (a hora da última rodada conferida) e o aviso de dado desatualizado. Os caminhos completos, com método e descrição, estão em [`api.md`](api.md) (gerado do código).

| Tela (`painel/src/telas/`) | Rotas principais |
|---|---|
| `Caixa/APagar` | `contas-pagar`, `despesas/{id}/encerrar`, `despesas/{id}/mes/{mes}/dispensar` |
| `Caixa/Projecao` | `caixa/projecao`, `cobrar/previsao` |
| `Caixa/Semanas` | `caixa/semanas`, `lancamentos` |
| `Caixa/Resumo` | `caixa/resumo` |
| `Caixa/DespesaForm` | `despesas`, `despesas/{id}`, `despesas/{id}/mes/{mes}` |
| `Gastos/Lancamentos` | `lancamentos`, `lancamentos/lote`, `sugestoes`, `sugestoes/{id}/aprovar` |
| `Gastos/ParaOndeVai` | `lancamentos`, cadastros (categorias, empresas, pessoas) |
| `Gastos/Cartoes` | `cartoes`, `lancamentos`, `lancamentos/lote`, `assinaturas` |
| `Gastos/Parcelas` | `parcelas` |
| `Gastos/Assinaturas` | `assinaturas`, `assinaturas/{id}` |
| `Cobrar/AReceber` | `cobrar/a-receber`, `cobrar/a-receber-manual/...` (cancelar, confirmar ou rejeitar proposta) |
| `Cobrar/NotasAReceber` | `cobrar/notas`, `cobrar/recebimentos`, `.../{id}/confirmar`, `.../{id}/rejeitar` |
| `Regras` | `regras`, `regras/{id}`, `sugestoes`, `sugestoes/{id}/aprovar`, `sugestoes/{id}/rejeitar` |
| `Cadastros`, `CadastrosCobranca`, `CadastrosEquivalencias` | `cadastros/contas`, `cadastros/pessoas`, `cadastros/empresas`, `cadastros/categorias` (e `equivalencias`), `cadastros/nibo` |
| `CadastrosDespesas` | `despesas`, `despesas/{id}`, `despesas/{id}/encerrar` |
| `Gabi/Agentes`, `ReceitasAgentes` | `agentes` (emitir, escopos, revogar tokens do MCP) e as receitas de conexão (`receitas.ts`) |

Componentes que aparecem em todas as telas: `Avisos` (`avisos`, marcar lido), `CustoGabi` (`custo`) e o `Shell` (menu, filtro, ocultar valores).

## O que o painel nunca faz

- **Não envia nada para fora** (R2) e não paga: aprovar uma sugestão só muda a classificação no banco.
- **A Gabi sugere, o Ricardo decide** (R1): sugestões de classificação, regras e baixas de nota/a receber ficam pendentes até o clique.
- **Valores** vêm como string decimal da API (centavos inteiros no banco, R7) e o painel só formata; `lib/ocultar.tsx` esconde os valores a pedido, e `lib/celular.ts` ajusta o layout no celular.
- **Níveis de acesso** (`terceiros`, `familia_vip`, `boss`): as rotas exigem `boss` por padrão; o painel não decide permissão, só mostra o que a API devolve.

## Testes

Os testes ficam em `painel/tests/` (um arquivo por tela ou componente, mais `navegacao.test.tsx` para o menu e `contrato.test.ts`, que confere o painel contra o contrato da API). `apiFalsa.ts` é a API de mentira usada pelas telas. Um teste do `navegacao` garante que as áreas removidas não voltam ao menu.

## Design

O visual é o sistema **Industry** do protótipo (R17): `painel/src/tema/industry.css` é o CSS do protótipo sem alteração (sem a linha `@import`; as fontes vêm de `@fontsource`, locais) e `tema/gabi.css` só acrescenta. Classes do sistema (`.blueprint`, `.btn`, `.table`) são reutilizadas, nunca recriadas; não há CDN nem URL externa no build. Tema claro e escuro, e layout de celular. As capturas lado a lado com o protótipo estão em [`design/GALERIA.md`](design/GALERIA.md). Regras de contribuição: [`../painel/README.md`](../painel/README.md).
