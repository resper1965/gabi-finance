import { createContext, useContext } from "react";
import { createPortal } from "react-dom";
import { Clock, FileCheck2, TriangleAlert } from "lucide-react";
import type { Fonte } from "../lib/api";
import { Etiqueta } from "./Etiqueta";

export interface FaixaProps {
  dadosAte: string | null; // ISO; vem do envelope (última rodada CONFERIDA)
  desatualizado?: boolean;
  fonte?: string; // qual fonte parou
  proximaRodada?: string | null; // ISO; próxima captura agendada
  fontes?: Fonte[]; // fontes do envelope, com o estado de cada uma
}

/** Onde a Shell quer a faixa (entre o cabeçalho e o conteúdo). Sem Shell, a faixa sai no lugar. */
export const FaixaSlot = createContext<HTMLElement | null>(null);

const FORMATO = new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
/** "dados até DD/MM hh:mm" no horário de Brasília, qualquer que seja o fuso do navegador. */
export function formatarDadosAte(iso: string): string {
  const p = Object.fromEntries(FORMATO.formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
  return `${p.day}/${p.month} ${p.hour}:${p.minute}`;
}

const HORA = new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit", hour12: false });
/** "15h" (ou "15h30") no horário de Brasília. */
export function formatarHora(iso: string): string {
  const [h, m] = HORA.format(new Date(iso)).split(":");
  return m === "00" ? `${Number(h)}h` : `${Number(h)}h${m}`;
}

/** Faixa de proveniência no topo de todo painel: até quando os dados valem, se a rodada foi conferida, de que fontes vieram
 *  e quando é a próxima captura. Desatualizada, fica âmbar e diz qual fonte parou. */
export function Faixa({ dadosAte, desatualizado, fonte, proximaRodada, fontes = [] }: FaixaProps) {
  const slot = useContext(FaixaSlot);
  const faixa = (
    <div role="status" className="faixa" data-estado={desatualizado ? "desatualizado" : "ok"}>
      <span className="faixa-item">
        {desatualizado ? <TriangleAlert size={14} strokeWidth={1.8} aria-hidden="true" /> : <FileCheck2 size={14} strokeWidth={1.8} aria-hidden="true" />}
        {dadosAte
          ? <span>{desatualizado ? "Dados desatualizados · até" : "dados até"} <b className="mono">{formatarDadosAte(dadosAte)}</b></span>
          : <span>sem dados conferidos ainda</span>}
      </span>
      {dadosAte && (desatualizado ? <Etiqueta tipo="conferir" texto="a conferir" /> : <Etiqueta tipo="ok" texto="rodada conferida" />)}
      {desatualizado && fonte && <span className="faixa-item"><b>{fonte} parou</b></span>}
      {fontes.length > 0 && <>
        <span className="faixa-sep faixa-fontes" aria-hidden="true" />
        <span className="faixa-item faixa-fontes"><span>fontes: {fontes.map((f, i) => <span key={f.nome}>{i ? ", " : ""}<span className="mono">{f.nome}</span>{f.estado !== "ok" ? ` (${f.estado})` : ""}</span>)}</span></span>
      </>}
      {proximaRodada && <span className="faixa-item"><Clock size={13} strokeWidth={1.8} aria-hidden="true" />próxima rodada às {formatarHora(proximaRodada)}</span>}
    </div>
  );
  return slot ? createPortal(faixa, slot) : faixa;
}
