import { useState } from "react";

/** localStorage que nunca derruba a tela (modo privado, dados bloqueados). */
export function lerLocal(chave: string): string | null {
  try { return localStorage.getItem(chave); } catch { return null; }
}
export function gravarLocal(chave: string, valor: string): void {
  try { localStorage.setItem(chave, valor); } catch { /* preferência local é opcional */ }
}
export function useLocal(chave: string, padrao: string): [string, (v: string) => void] {
  const [v, setV] = useState(() => lerLocal(chave) ?? padrao);
  return [v, (novo) => { setV(novo); gravarLocal(chave, novo); }];
}
