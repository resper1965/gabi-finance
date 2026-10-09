/** Cliente da API. Toda leitura de dinheiro vem no envelope {dados_ate, desatualizado, fontes, dados}. */
export interface Fonte { nome: string; estado: string; ultima: string | null }
export interface Envelope<T> { dados_ate: string | null; desatualizado: boolean; proxima_rodada?: string | null; fontes: Fonte[]; dados: T }

export class ErroApi extends Error {
  constructor(public status: number, public codigo: string, mensagem: string) { super(mensagem); }
}

async function chamar<T>(metodo: string, url: string, corpo?: unknown): Promise<Envelope<T>> {
  let r: Response;
  try {
    r = await fetch(url, {
      method: metodo,
      headers: corpo === undefined ? undefined : { "Content-Type": "application/json" },
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
  } catch {
    throw new ErroApi(0, "sem_rede", "não consegui falar com o servidor");
  }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new ErroApi(r.status, j.erro ?? "erro", j.mensagem ?? `erro ${r.status}`);
  return j as Envelope<T>;
}

export const api = {
  get: <T>(url: string) => chamar<T>("GET", url),
  post: <T>(url: string, corpo: unknown = {}) => chamar<T>("POST", url, corpo),
  patch: <T>(url: string, corpo: unknown) => chamar<T>("PATCH", url, corpo),
};
