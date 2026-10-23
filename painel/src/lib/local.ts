import { useState } from "react";

/** localStorage que nunca derruba a tela (modo privado, dados bloqueados). */
export function lerLocal(chave: string): string | null {
  try { return localStorage.getItem(chave); } catch { return null; }
}
export function gravarLocal(chave: string, valor: string): void {
  try { localStorage.setItem(chave, valor); } catch { /* preferência local é opcional */ }
}
/** A chave pode mudar entre renders (p.ex. `gabi.aba.<área>`): aí relê a chave nova em vez de manter o valor da antiga. */
export function useLocal(chave: string, padrao: string): [string, (v: string) => void] {
  const [estado, setEstado] = useState(() => ({ chave, v: lerLocal(chave) ?? padrao }));
  const v = estado.chave === chave ? estado.v : (lerLocal(chave) ?? padrao);
  return [v, (novo) => { setEstado({ chave, v: novo }); gravarLocal(chave, novo); }];
}
