const dois = (n: number) => String(n).padStart(2, "0");
/** "2026-10-08" → "08/10" (sem passar por Date, para não deslocar o dia por fuso). */
export const dataCurta = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
/** "2026-10" → "out/26" */
export const mesCurto = (ym: string) => `${MESES[Number(ym.slice(5, 7)) - 1]}/${ym.slice(2, 4)}`;
export const num = (s: string | number | null | undefined) => Number(s ?? 0);
export { dois };

const SIMBOLO: Record<string, string> = { USD: "US$", EUR: "€", GBP: "£" };
const fmt = (s: string) => Math.abs(Number(s)).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
/** "US$ 6,01 → R$ 31,32" para compra em moeda estrangeira; null em BRL. Só formata (a API manda strings decimais). */
export function originalEmReais(l: { valor: string; moeda?: string; valor_original?: string | null; convertido?: boolean }): string | null {
  if (!l.moeda || l.valor_original == null) return null;
  const orig = `${SIMBOLO[l.moeda] ?? l.moeda} ${fmt(l.valor_original)}`;
  return l.convertido === false ? `${orig} (sem conversão para reais)` : `${orig} → R$ ${fmt(l.valor)}`;
}
