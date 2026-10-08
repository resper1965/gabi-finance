import { createContext, useContext, type ReactNode } from "react";
import { useLocal } from "./local";

export const PERIODOS = [["semana", "Semana"], ["mes", "Mês"], ["12m", "12 meses"]] as const;
export interface Filtros { periodo: string; conta: string; setPeriodo: (p: string) => void; setConta: (c: string) => void }
const Ctx = createContext<Filtros>({ periodo: "mes", conta: "", setPeriodo: () => {}, setConta: () => {} });
export const useFiltros = () => useContext(Ctx);

export function FiltrosProvider({ children }: { children: ReactNode }) {
  const [periodo, setPeriodo] = useLocal("gabi.periodo", "mes");
  const [conta, setConta] = useLocal("gabi.conta", "");
  return <Ctx.Provider value={{ periodo, conta, setPeriodo, setConta }}>{children}</Ctx.Provider>;
}
