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

const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
/** "1234.5" → "R$ 1.234,50" (espaço normal no lugar do NBSP); "—" se não for número. A API manda strings decimais: aqui só se formata. */
export function formatarBRL(v: string | number): string {
  const n = Number(v);
  return Number.isFinite(n) ? BRL.format(n).replace(/\u00a0/g, " ") : "—";
}

/** "HH:MM" de "AAAA-MM-DDTHH:MM..." (sem passar por Date); null se não casar o padrão. */
export const horaDe = (iso: string): string | null => /^\d{4}-\d{2}-\d{2}T(\d{2}:\d{2})/.exec(iso)?.[1] ?? null;

const FUSO = "America/Sao_Paulo";
const DIA_MS = 86_400_000;
/** "AAAA-MM-DD" de hoje + `n` dias no fuso de Brasília (sem passar pelo fuso do navegador). */
export const diaSP = (n = 0): string => new Intl.DateTimeFormat("sv-SE", { timeZone: FUSO }).format(new Date(Date.now() + n * DIA_MS));

/** "08/10" ou "08/10 às 09:30" de um prazo de atividade ("" sem data). */
export function quandoVence(vence_em: string | null, tem_hora: boolean): string {
  if (!vence_em) return "";
  const h = tem_hora ? horaDe(vence_em) : null;
  return h ? `${dataCurta(vence_em)} às ${h}` : dataCurta(vence_em);
}
