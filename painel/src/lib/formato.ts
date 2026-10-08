const dois = (n: number) => String(n).padStart(2, "0");
/** "2026-10-08" → "08/10" (sem passar por Date, para não deslocar o dia por fuso). */
export const dataCurta = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
/** "2026-10" → "out/26" */
export const mesCurto = (ym: string) => `${MESES[Number(ym.slice(5, 7)) - 1]}/${ym.slice(2, 4)}`;
export const num = (s: string | number | null | undefined) => Number(s ?? 0);
export { dois };
