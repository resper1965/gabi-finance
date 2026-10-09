import { readFileSync } from "node:fs";
import { join } from "node:path";
import { vi } from "vitest";

const amostra = (n: string) => JSON.parse(readFileSync(join(__dirname, "amostras", `${n}.json`), "utf-8"));

const ROTAS: [RegExp, string][] = [
  [/\/avisos/, "avisos"],
  [/\/categorias\/equivalencias\/pendentes/, "equivalencias-pendentes"],
  [/\/caixa\/resumo/, "caixa-resumo"], [/\/caixa\/semanas/, "caixa-semanas"], [/\/contas-pagar/, "contas-pagar"],
  [/\/lancamentos.*pendente=para_quem/, "lancamentos-pendentes"], [/\/lancamentos/, "lancamentos"],
  [/\/destino\/agrupado.*por=pessoa/, "destino-pessoa"], [/\/destino\/agrupado/, "destino-fornecedor"], [/\/destino/, "destino"],
  [/\/cartoes/, "cartoes"], [/\/parcelas/, "parcelas"], [/\/assinaturas/, "assinaturas"], [/\/sugestoes/, "sugestoes"], [/\/regras/, "regras"],
  [/\/custo/, "custo"], [/\/contagens/, "contagens"], [/\/rodadas/, "rodadas"], [/\/cobrar\/reembolsos/, "cobrar-reembolsos"], [/\/cobrar\/comprovantes/, "cobrar-comprovantes"],
  [/\/cobrar\/pedidos/, "cobrar-pedidos"], [/\/cobrar\/cobrancas/, "cobrar-cobrancas"], [/\/cadastros\/nibo/, "cadastros-nibo"], [/\/cadastros\/liberacoes/, "cadastros-liberacoes"], [/\/cadastros\/contas/, "cadastros-contas"], [/\/cadastros\/pessoas/, "cadastros-pessoas"],
  [/\/hoje/, "hoje"], [/\/frentes\/1/, "frente-1"], [/\/frentes/, "frentes"], [/\/agenda/, "agenda"], [/\/mensagens/, "mensagens"], [/\/tarefas/, "tarefas"], [/\/caixas-email/, "caixas-email"],
  [/\/cadastros\/categorias/, "cadastros-categorias"], [/\/cadastros\/empresas/, "cadastros-empresas"],
];

export interface Chamada { metodo: string; url: string; corpo: unknown }

/** fetch falso: GET devolve a amostra real da API; PATCH/POST gravam a chamada e devolvem um envelope vazio. `sobrescrever` troca uma amostra. */
export function apiFalsa(sobrescrever: Record<string, unknown> = {}, posts: [RegExp, unknown][] = []) {
  const chamadas: Chamada[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const metodo = init?.method ?? "GET";
    const corpo = init?.body ? JSON.parse(String(init.body)) : undefined;
    chamadas.push({ metodo, url, corpo });
    const ok = (j: unknown) => ({ ok: true, status: 200, json: async () => j }) as Response;
    if (metodo !== "GET") return ok(posts.find(([r]) => r.test(url))?.[1] ?? { dados_ate: null, desatualizado: false, fontes: [], dados: {} });
    const nome = ROTAS.find(([r]) => r.test(url))?.[1];
    if (!nome) return { ok: false, status: 404, json: async () => ({ erro: "nao_encontrado", mensagem: `sem amostra para ${url}` }) } as Response;
    return ok(sobrescrever[nome] ?? amostra(nome));
  }));
  return chamadas;
}
export { amostra };
