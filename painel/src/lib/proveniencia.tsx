import { createContext, useContext } from "react";
import type { Fonte } from "./api";

/** O que o envelope da API diz sobre a validade dos dados da tela: até quando, de quais fontes e se a rodada foi conferida. */
export interface Proveniencia { dadosAte: string | null; desatualizado: boolean; fontes: Fonte[]; proximaRodada?: string | null }

export const ProvContext = createContext<Proveniencia | null>(null);
export const useProveniencia = () => useContext(ProvContext);

/** Uma entrada que alimenta um número: o nome como aparece no envelope (ou o registro interno de onde sai) e o papel dela no cálculo. */
export interface FonteEvidencia { nome: string; papel: string }

/** Entradas conhecidas. open-finance e notas-nibo vêm no envelope com estado; a planilha e o cadastro de despesas são registros
 *  internos que o envelope não descreve (o quadro diz isso em vez de inventar um estado). */
export const FONTE = {
  extrato: (papel = "saldos e extratos do banco"): FonteEvidencia => ({ nome: "open-finance", papel }),
  notas: (papel = "notas fiscais do Nibo"): FonteEvidencia => ({ nome: "notas-nibo", papel }),
  planilha: (papel = "contas a pagar do mês"): FonteEvidencia => ({ nome: "planilha de compromissos", papel }),
  despesas: (papel = "saídas previstas"): FonteEvidencia => ({ nome: "cadastro de despesas", papel }),
};
