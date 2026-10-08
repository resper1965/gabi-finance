# painel (gabi.brain)

React + Vite. O build sai em `../gabi/painel/` e a API serve em `/` (com `/assets`). Sem build, `/` mostra a página de verificação da Fase 0.

## Comandos
| comando | faz |
|---|---|
| `npm run dev` | servidor de desenvolvimento; `/api` vai para `127.0.0.1:8000` |
| `npm test` | Vitest (fidelidade ao design, componentes, telas) |
| `npm run build` | `tsc` + build de produção em `../gabi/painel/` |
| `npm run analisar` | falha se algum JS passar de 150 KB gzip |

## Regras
- **R17, design Industry:** `src/tema/industry.css` é o CSS do protótipo, byte a byte, sem a linha `@import` (as fontes vêm de `@fontsource`, locais, em `src/main.tsx`). `src/tema/gabi.css` só acrescenta; nunca redefine token do Industry fora do tema escuro. Testes: `tests/fidelidade.test.ts`.
- Classes do sistema (`.blueprint`, `.btn`, `.table`) são reutilizadas, nunca recriadas.
- Sem CDN. Sem URL externa no build.
- Um componente = um arquivo em `src/componentes/`; uma tela = um arquivo em `src/telas/`.
- Dinheiro chega da API como string `"1234.56"`; o painel só formata (`Valor`), nunca calcula.
- Preferências (tema, menu, olho, última aba por área) ficam em `localStorage` com `try/catch` (`src/lib/local.ts`).
