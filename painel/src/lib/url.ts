/** Só deixa passar endereço http(s); qualquer outro esquema (javascript:, data:) ou texto solto vira null. */
export function urlSegura(u: string | null | undefined): string | null {
  if (!u) return null;
  try {
    const p = new URL(u).protocol;
    return p === "http:" || p === "https:" ? u : null;
  } catch {
    return null;
  }
}
