import type { CSSProperties, ReactNode } from "react";

/** Cartão/seção do sistema Industry: classe .blueprint com as quatro marcas "+" nos cantos. */
export function Bloco({ titulo, nota, children, style }: { titulo?: string; nota?: ReactNode; children: ReactNode; style?: CSSProperties }) {
  return (
    <section className="blueprint" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12, minWidth: 0, ...style }}>
      <i className="corner tl" /><i className="corner tr" /><i className="corner bl" /><i className="corner br" />
      {titulo && (
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "baseline" }}>
          <h3 style={{ margin: 0, fontSize: 20 }}>{titulo}</h3>
          {nota && <span style={{ fontSize: 12.5, color: "var(--ink2)" }}>{nota}</span>}
        </div>
      )}
      {children}
    </section>
  );
}
