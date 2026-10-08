import type { ReactNode } from "react";
import { Etiqueta, type TipoEtiqueta } from "./Etiqueta";

/** Instrumento clicável da visão geral: .blueprint, rótulo em caixa alta, número grande, nota em cinza e sinal opcional. */
export function Kpi({ rotulo, children, nota, sinal, aoClicar }: {
  rotulo: string; children: ReactNode; nota?: ReactNode; sinal?: { tipo: TipoEtiqueta; texto: string }; aoClicar?: () => void;
}) {
  return (
    <button className="blueprint" onClick={aoClicar} style={{ textAlign: "left", background: "transparent", color: "inherit", padding: "14px 14px 12px", display: "flex", flexDirection: "column", gap: 6, cursor: aoClicar ? "pointer" : "default", minWidth: 0, font: "inherit" }}>
      <i className="corner tl" /><i className="corner tr" /><i className="corner bl" /><i className="corner br" />
      <span style={{ font: "600 10.5px/1.25 var(--font-body)", letterSpacing: ".08em", textTransform: "uppercase", color: "var(--ink2)" }}>{rotulo}</span>
      <span style={{ font: "600 27px/1.05 var(--font-heading)", fontVariantNumeric: "tabular-nums", letterSpacing: "-.01em", whiteSpace: "nowrap" }}>{children}</span>
      {nota && <span style={{ fontSize: 12, color: "var(--ink2)", lineHeight: 1.35 }}>{nota}</span>}
      {sinal && <span style={{ alignSelf: "flex-start" }}><Etiqueta tipo={sinal.tipo} texto={sinal.texto} /></span>}
    </button>
  );
}

/** Número de uma faixa de totais (Semanas): linha fina em cima, sem moldura. */
export function Estat({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <div style={{ borderTop: "1px solid var(--color-text)", paddingTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={{ font: "600 10.5px/1.25 var(--font-body)", letterSpacing: ".08em", textTransform: "uppercase", color: "var(--ink2)" }}>{rotulo}</span>
      <span style={{ font: "600 23px/1.1 var(--font-heading)", fontVariantNumeric: "tabular-nums" }}>{children}</span>
    </div>
  );
}

/** Grade de instrumentos: colunas automáticas de no mínimo `min` px, gap 14. */
export function GradeKpi({ children, min = 168 }: { children: ReactNode; min?: number }) {
  return <div style={{ display: "grid", gridTemplateColumns: `repeat(auto-fit,minmax(min(100%,${min}px),1fr))`, gap: 14 }}>{children}</div>;
}
