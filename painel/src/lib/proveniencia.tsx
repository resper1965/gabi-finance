import { createContext, useContext } from "react";
import type { Fonte } from "./api";

/** O que o envelope da API diz sobre a validade dos dados da tela: até quando, de quais fontes e se a rodada foi conferida. */
export interface Proveniencia { dadosAte: string | null; desatualizado: boolean; fontes: Fonte[]; proximaRodada?: string | null }

export const ProvContext = createContext<Proveniencia | null>(null);
export const useProveniencia = () => useContext(ProvContext);
