/** Tipos do fluxo origem → categoria → destino e cor do destino (usados por ParaOndeVai). */
export interface No { nome: string; tipo: "origem" | "categoria" | "destino" }
export interface Fluxo { de: string; para: string; valor: string }

const EMPRESA: [RegExp, string][] = [[/ness/i, "var(--ness)"], [/ionic/i, "var(--ionic)"], [/bekaa/i, "var(--bekaa)"]];
/** Cor do destino: cada empresa tem sempre a mesma cor; consumo pessoal usa a cor "pessoal". */
export const corDestino = (nome: string) => EMPRESA.find(([r]) => r.test(nome))?.[1] ?? "var(--pes)";
