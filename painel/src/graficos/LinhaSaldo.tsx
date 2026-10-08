import { dataCurta, num } from "../lib/formato";

export interface Ponto { data: string; valor: string; projecao: boolean }

const brl = (n: number) => `R$ ${Math.round(n).toLocaleString("pt-BR")}`;

/** Saldo realizado (cheio) e projetado (tracejado) com área, grade, marca de "hoje" e eixos. SVG próprio. */
export function LinhaSaldo({ pontos, oculto = false }: { pontos: Ponto[]; oculto?: boolean }) {
  if (pontos.length < 2) return <p style={{ color: "var(--ink2)", margin: 0 }}>Poucos dias de saldo para desenhar a linha.</p>;
  const W = 640, H = 200, L = 52, R = 10, T = 10, B = 24;
  const vs = pontos.map((p) => num(p.valor));
  let min = Math.min(...vs), max = Math.max(...vs);
  const folga = (max - min) * 0.1 || 1;
  min -= folga; max += folga;
  const x = (i: number) => L + (i * (W - L - R)) / (pontos.length - 1);
  const y = (v: number) => T + ((max - v) / (max - min)) * (H - T - B);
  const reais = pontos.map((p, i) => [p, i] as const).filter(([p]) => !p.projecao);
  const proj = pontos.map((p, i) => [p, i] as const).filter(([p, i]) => p.projecao || (i === (reais[reais.length - 1]?.[1] ?? -1)));
  const caminho = (l: (readonly [Ponto, number])[]) => l.map(([p, i], k) => `${k ? "L" : "M"}${x(i).toFixed(1)},${y(num(p.valor)).toFixed(1)}`).join("");
  const ticks = [0, 1, 2, 3].map((k) => min + ((max - min) * k) / 3);
  const hoje = reais.length ? reais[reais.length - 1][1] : 0;
  const area = reais.length ? `${caminho(reais)}L${x(hoje).toFixed(1)},${H - B}L${x(reais[0][1]).toFixed(1)},${H - B}Z` : "";
  const xt = [0, Math.floor((pontos.length - 1) / 2), pontos.length - 1];
  return (
    <svg role="img" aria-label="Saldo dos últimos dias e projeção" viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block", overflow: "visible" }}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} style={{ stroke: "var(--line2)" }} />
          <text x={L - 6} y={y(t) + 3} style={{ fill: "var(--ink2)", font: "500 10.5px var(--mono)", textAnchor: "end" }}>{oculto ? "••••" : brl(t)}</text>
        </g>
      ))}
      {area && <path d={area} style={{ fill: "var(--color-accent)", fillOpacity: 0.1 }} />}
      {proj.length > 1 && <line x1={x(hoje)} x2={x(hoje)} y1={T} y2={H - B} style={{ stroke: "var(--line3)", strokeDasharray: "2 3" }} />}
      <path d={caminho(reais)} style={{ fill: "none", stroke: "var(--color-accent-700)", strokeWidth: 2 }} />
      {proj.length > 1 && <path data-projecao d={caminho(proj)} style={{ fill: "none", stroke: "var(--color-accent)", strokeWidth: 2, strokeDasharray: "5 4" }} />}
      {xt.map((i) => <text key={i} x={x(i)} y={H - 6} style={{ fill: "var(--ink2)", font: "500 10.5px var(--mono)", textAnchor: "middle" }}>{dataCurta(pontos[i].data)}</text>)}
    </svg>
  );
}
