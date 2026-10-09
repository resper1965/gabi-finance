import { useEffect, useState } from "react";

/** true abaixo de 760px (mesmo corte do Shell). */
export function useCelular(): boolean {
  const consulta = "(max-width: 759px)";
  const [v, setV] = useState(() => typeof window !== "undefined" && !!window.matchMedia?.(consulta).matches);
  useEffect(() => {
    const m = window.matchMedia?.(consulta);
    if (!m) return;
    const f = () => setV(m.matches);
    m.addEventListener?.("change", f);
    return () => m.removeEventListener?.("change", f);
  }, []);
  return v;
}
