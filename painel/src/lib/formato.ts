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

/** Valor digitado ("2.350,50", "800", "129.90", "R$ 1.500") → string decimal em reais com 2 casas ("2350.50"); null se não for valor.
 *  Só mexe no texto (nunca passa por número de ponto flutuante). Com vírgula, o ponto é milhar; sem vírgula, "1.500" é milhar e "129.90" é decimal. */
export function reaisDoTexto(texto: string): string | null {
  let s = texto.replace(/R\$/i, "").replace(/\s/g, "");
  if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
  else if (/^\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, "");
  const m = /^(\d+)(?:\.(\d{1,2}))?$/.exec(s);
  if (!m) return null;
  return `${m[1].replace(/^0+(?=\d)/, "")}.${(m[2] ?? "").padEnd(2, "0")}`;
}
