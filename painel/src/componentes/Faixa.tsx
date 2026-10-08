import { createContext, useContext } from "react";
import { createPortal } from "react-dom";

export interface FaixaProps {
  dadosAte: string | null; // ISO; vem do envelope (última rodada CONFERIDA)
  desatualizado?: boolean;
  fonte?: string; // qual fonte parou
}

/** Onde a Shell quer a faixa (acima do conteúdo, fora do padding). Sem Shell, a faixa sai no lugar. */
export const FaixaSlot = createContext<HTMLElement | null>(null);

const FORMATO = new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
/** "dados até DD/MM hh:mm" no horário de Brasília, qualquer que seja o fuso do navegador. */
export function formatarDadosAte(iso: string): string {
  const p = Object.fromEntries(FORMATO.formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
  return `${p.day}/${p.month} ${p.hour}:${p.minute}`;
}

/** Faixa "dados até DD/MM hh:mm" no topo de todo painel; amarela e com a fonte quando desatualizado. */
export function Faixa({ dadosAte, desatualizado, fonte }: FaixaProps) {
  const slot = useContext(FaixaSlot);
  const faixa = (
    <div
      role="status"
      data-estado={desatualizado ? "desatualizado" : "ok"}
      style={{
        display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", padding: "7px var(--pad)", font: "500 12px/1.4 var(--mono)",
        background: desatualizado ? "var(--warn-bg)" : "transparent",
        color: desatualizado ? "var(--warn)" : "var(--ink2)",
        borderBottom: `1px solid ${desatualizado ? "var(--warn)" : "var(--line2)"}`,
      }}
    >
      <span aria-hidden="true">{desatualizado ? "▲" : "●"}</span>
      {dadosAte
        ? <span>{desatualizado ? "Dados desatualizados · até" : "dados até"} <strong>{formatarDadosAte(dadosAte)}</strong></span>
        : <span>sem dados conferidos ainda</span>}
      {desatualizado && fonte && <span>{fonte} parou</span>}
    </div>
  );
  return slot ? createPortal(faixa, slot) : faixa;
}
