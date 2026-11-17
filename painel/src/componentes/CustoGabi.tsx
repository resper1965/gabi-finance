import { useApi } from "../lib/useApi";

interface Custo { dia_usd: number; mes_usd: number; teto_dia_usd: number; teto_mes_usd: number; cambio_usd_brl?: string | null }

const virgula = (n: number) => n.toFixed(2).replace(".", ",");

/** "Custo da Gabi" no pé do trilho: dia e mês contra o teto, com a marca dos 70%; passou dela, a barra fica âmbar. */
export function CustoGabi() {
  const c = useApi<Custo>("/api/v1/custo").env?.dados;
  if (!c) return null;
  const cambio = c.cambio_usd_brl ? Number(c.cambio_usd_brl) : null; // câmbio vem de `parametro` (editável); sem ele, fica em dólar
  const usd = (n: number) => (cambio ? `R$ ${virgula(n * cambio)}` : `US$ ${virgula(n)}`);
  const pDia = Math.min(100, (c.dia_usd / c.teto_dia_usd) * 100), pMes = Math.min(100, (c.mes_usd / c.teto_mes_usd) * 100);
  const barra = (pct: number) => (
    <span className="custo-barra"><span style={{ width: `${pct}%` }} data-alto={pct >= 70} /><i /></span>
  );
  return (
    <div aria-label="Custo da Gabi" className="custo">
      <span className="custo-cab"><span>Custo da Gabi</span>{pMes >= 70 && <b>{Math.round(pMes)}% do mês</b>}</span>
      <span className="custo-linha"><span>Hoje</span><span className="num">{usd(c.dia_usd)} / {usd(c.teto_dia_usd)}</span></span>
      {barra(pDia)}
      <span className="custo-linha"><span>Mês</span><span className="num">{usd(c.mes_usd)} / {usd(c.teto_mes_usd)}</span></span>
      {barra(pMes)}
    </div>
  );
}
