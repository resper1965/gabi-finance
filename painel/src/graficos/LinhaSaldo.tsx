import { dataCurta, num } from "../lib/formato";

export interface Ponto { data: string; valor: string; projecao: boolean }

const brl = (n: number) => `R$ ${Math.round(n).toLocaleString("pt-BR")}`;
const brlCheio = (n: number) => `R$ ${n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** Saldo realizado (cheio) e projetado (tracejado), com a marca de "hoje" e o ponto de menor saldo marcado e rotulado. SVG próprio. */
export function LinhaSaldo({ pontos, oculto = false, largura = 680, altura = 230 }: { pontos: Ponto[]; oculto?: boolean; largura?: number; altura?: number }) {
  if (pontos.length < 2) return <p className="suave">Poucos dias de saldo para desenhar a linha.</p>;
  const W = largura, H = altura, L = 64, R = 16, T = 30, B = 26;
  const vs = pontos.map((p) => num(p.valor));
  let min = Math.min(...vs), max = Math.max(...vs);
  const folga = (max - min) * 0.12 || 1;
  min -= folga; max += folga;
  const x = (i: number) => L + (i * (W - L - R)) / (pontos.length - 1);
  const y = (v: number) => T + ((max - v) / (max - min)) * (H - T - B);
  const reais = pontos.map((p, i) => [p, i] as const).filter(([p]) => !p.projecao);
  const proj = pontos.map((p, i) => [p, i] as const).filter(([p, i]) => p.projecao || (i === (reais[reais.length - 1]?.[1] ?? -1)));
  const caminho = (l: (readonly [Ponto, number])[]) => l.map(([p, i], k) => `${k ? "L" : "M"}${x(i).toFixed(1)},${y(num(p.valor)).toFixed(1)}`).join("");
  const ticks = [0, 1, 2, 3].map((k) => min + ((max - min) * k) / 3);
  const hoje = reais.length ? reais[reais.length - 1][1] : 0;
  const area = reais.length ? `${caminho(reais)}L${x(hoje).toFixed(1)},${H - B}L${x(reais[0][1]).toFixed(1)},${H - B}Z` : "";
  const xt = [...new Set([0, Math.floor((pontos.length - 1) / 2), pontos.length - 1])];
  // ponto de menor saldo: entre os projetados quando há projeção, senão em toda a série
  const candidatos = proj.length > 1 ? proj.filter(([p]) => p.projecao) : pontos.map((p, i) => [p, i] as const);
  const [pMin, iMin] = candidatos.reduce((a, b) => (num(b[0].valor) < num(a[0].valor) ? b : a));
  const mx = x(iMin), my = y(num(pMin.valor)), negativo = num(pMin.valor) < 0;
  const ancora = mx > W - 150 ? "end" : mx < L + 90 ? "start" : "middle";
  const ly = my > H - B - 34 ? my - 14 : my + 22;
  return (
    <svg role="img" aria-label={`Saldo dos últimos dias e projeção; menor saldo ${oculto ? "oculto" : brlCheio(num(pMin.valor))} em ${dataCurta(pMin.data)}`} viewBox={`0 0 ${W} ${H}`} className="grafico" style={{ width: "100%", height: "auto", overflow: "visible" }}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} style={{ stroke: "var(--regra)" }} />
          <text x={L - 8} y={y(t) + 3} style={{ textAnchor: "end" }}>{oculto ? "••••" : brl(t)}</text>
        </g>
      ))}
      {min < 0 && max > 0 && <line x1={L} x2={W - R} y1={y(0)} y2={y(0)} style={{ stroke: "var(--carimbo-vermelho)", strokeDasharray: "2 3" }} />}
      {area && <path d={area} style={{ fill: "var(--tinta)", fillOpacity: 0.06 }} />}
      {proj.length > 1 && <>
        <line x1={x(hoje)} x2={x(hoje)} y1={T - 12} y2={H - B} style={{ stroke: "var(--regra-forte)", strokeDasharray: "2 3" }} />
        <text x={x(hoje)} y={T - 16} style={{ textAnchor: "middle" }}>hoje</text>
      </>}
      <path d={caminho(reais)} style={{ fill: "none", stroke: "var(--tinta)", strokeWidth: 2, strokeLinejoin: "round" }} />
      {proj.length > 1 && <path data-projecao d={caminho(proj)} style={{ fill: "none", stroke: "var(--acento)", strokeWidth: 2, strokeDasharray: "5 4" }} />}
      <g data-menor-saldo>
        <line x1={mx} x2={mx} y1={my} y2={H - B} style={{ stroke: negativo ? "var(--carimbo-vermelho)" : "var(--tinta-2)", strokeWidth: 1 }} />
        <circle cx={mx} cy={my} r={4.5} style={{ fill: "var(--papel)", stroke: negativo ? "var(--carimbo-vermelho)" : "var(--tinta)", strokeWidth: 2 }} />
        <text x={mx + (ancora === "start" ? 8 : ancora === "end" ? -8 : 0)} y={ly} className="rotulo-forte" style={{ textAnchor: ancora, fill: negativo ? "var(--carimbo-vermelho)" : undefined, paintOrder: "stroke", stroke: "var(--papel)", strokeWidth: 5, strokeLinejoin: "round" }}>
          menor saldo {oculto ? "R$ ••••" : brlCheio(num(pMin.valor))} · {dataCurta(pMin.data)}
        </text>
      </g>
      {xt.map((i) => <text key={i} x={x(i)} y={H - 6} style={{ textAnchor: i === 0 ? "start" : i === pontos.length - 1 ? "end" : "middle" }}>{dataCurta(pontos[i].data)}</text>)}
    </svg>
  );
}
