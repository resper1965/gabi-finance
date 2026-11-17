# painel (gabi-finance)

Documentação completa do painel (telas, rotas, como rodar): [`docs/painel.md`](../docs/painel.md).

React + Vite. O build sai em `../gabi/painel/` e a API serve em `/` (com `/assets`). Sem build, `/` mostra a página de verificação da Fase 0.

## Comandos
| comando | faz |
|---|---|
| `npm run dev` | servidor de desenvolvimento; `/api` vai para `127.0.0.1:8000` |
| `npm test` | Vitest (fidelidade ao design, componentes, telas) |
| `npm run build` | `tsc` + build de produção em `../gabi/painel/` |
| `npm run analisar` | falha se algum JS passar de 150 KB gzip |

## Regras
- **Design (laudo):** toda cor, tipo, espaço e movimento vêm de `src/tema/tokens.css`; componentes e casca em `src/tema/laudo.css`. Fontes `@fontsource` locais em `src/main.tsx`. Testes: `tests/fidelidade.test.ts` (papéis de cor iguais nos dois temas, contraste ≥ 4,5:1, sem URL externa).
- Valor-chave vai em `Evidencia`/`Achados` (código de item e proveniência); estado vai em `Etiqueta` (carimbo). Classes do sistema (`.btn`, `.tabela`, `.seg`, `.chip`, `.pauta`) são reutilizadas, nunca recriadas.
- Sem CDN. Sem URL externa no build.
- Um componente = um arquivo em `src/componentes/`; uma tela = um arquivo em `src/telas/`.
- Dinheiro chega da API como string `"1234.56"`; o painel só formata (`Valor`), nunca calcula.
- Preferências (tema, menu, olho, última aba por área) ficam em `localStorage` com `try/catch` (`src/lib/local.ts`).
