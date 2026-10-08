import { useApi } from "../lib/useApi";

interface Custo { dia_usd: number; mes_usd: number; teto_dia_usd: number; teto_mes_usd: number }

const usd = (n: number) => `US$ ${n.toFixed(2).replace(".", ",")}`;

/** Cartão "Custo da Gabi" (dia e mês contra o teto, marca aos 70%); sempre visível na barra lateral. */
export function CustoGabi() {
  const c = useApi<Custo>("/api/v1/custo").env?.dados;
  if (!c) return null;
  const pDia = Math.min(100, (c.dia_usd / c.teto_dia_usd) * 100), pMes = Math.min(100, (c.mes_usd / c.teto_mes_usd) * 100);
  const aviso = pMes >= 70;
  const barra = (pct: number, cor: string) => (
    <span style={{ position: "relative", height: 5, background: "var(--line2)", display: "block" }}>
      <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${pct}%`, background: cor }} />
      <span style={{ position: "absolute", left: "70%", top: -2, bottom: -2, width: 1, background: "var(--warn)" }} />
    </span>
  );
  return (
    <div aria-label="Custo da Gabi" style={{ margin: "0 10px 10px", padding: 10, border: "1px solid var(--color-divider)", display: "flex", flexDirection: "column", gap: 6 }}>
      <span style={{ display: "flex", justifyContent: "space-between", font: "600 10.5px/1 var(--font-body)", letterSpacing: ".08em", textTransform: "uppercase", color: "var(--ink2)" }}>
        <span>Custo da Gabi</span>{aviso && <span style={{ color: "var(--warn)" }}>▲ {Math.round(pMes)}% do mês</span>}
      </span>
      <span style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}><span>Hoje</span><span style={{ fontVariantNumeric: "tabular-nums" }}>{usd(c.dia_usd)} / {usd(c.teto_dia_usd)}</span></span>
      {barra(pDia, "var(--color-accent)")}
      <span style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}><span>Mês</span><span style={{ fontVariantNumeric: "tabular-nums" }}>{usd(c.mes_usd)} / {usd(c.teto_mes_usd)}</span></span>
      {barra(pMes, aviso ? "var(--warn)" : "var(--color-accent)")}
    </div>
  );
}
