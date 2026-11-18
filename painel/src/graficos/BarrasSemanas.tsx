import { dataCurta, num } from "../lib/formato";

export interface Item { categoria: string; valor: string }
export interface Semana { inicio: string; fim: string; entradas: Item[]; saidas: Item[]; saldo: string | null; projecao: boolean }

const ENTRADA = ["var(--entrada-1)", "var(--entrada-2)"];
const SAIDA = ["var(--serie-1)", "var(--serie-2)", "var(--serie-3)", "var(--serie-4)", "var(--serie-5)"];
const soma = (l: Item[]) => l.reduce((s, i) => s + Math.abs(num(i.valor)), 0);

/** Ordem estável das categorias (maior total primeiro) para que a mesma categoria tenha sempre a mesma cor. */
export function ordemCategorias(semanas: Semana[], lado: "entradas" | "saidas"): string[] {
  const t = new Map<string, number>();
  semanas.forEach((s) => s[lado].forEach((i) => t.set(i.categoria, (t.get(i.categoria) ?? 0) + Math.abs(num(i.valor)))));
  return [...t.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([c]) => c);
}
export const corDe = (lado: "entradas" | "saidas", ordem: string[], cat: string) => {
  const paleta = lado === "entradas" ? ENTRADA : SAIDA;
  return paleta[Math.min(Math.max(0, ordem.indexOf(cat)), paleta.length - 1)];
};

/** Barras empilhadas por semana (entradas acima do eixo, saídas abaixo) e linha do saldo acumulado.
 *  Semanas futuras: opacidade .4 e contorno tracejado. Clicar numa semana a escolhe. */
export function BarrasSemanas({ semanas, escolhida, aoEscolher, oculto = false }: { semanas: Semana[]; escolhida: string | null; aoEscolher: (inicio: string) => void; oculto?: boolean }) {
  const W = 760, H = 300, L = 60, R = 70, T = 14, B = 26;
  const ent = ordemCategorias(semanas, "entradas"), sai = ordemCategorias(semanas, "saidas");
  const topo = Math.max(1, ...semanas.map((s) => soma(s.entradas))), fundo = Math.max(1, ...semanas.map((s) => soma(s.saidas)));
  const yz = T + ((H - T - B) * topo) / (topo + fundo);
  const k = (yz - T) / topo; // px por real, igual nos dois lados
  const larg = (W - L - R) / Math.max(1, semanas.length);
  const cx = (i: number) => L + larg * i + larg / 2;
  const saldos = semanas.map((s) => (s.saldo === null ? null : num(s.saldo)));
  const reais = saldos.filter((v): v is number => v !== null);
  const sMin = Math.min(...reais, 0), sMax = Math.max(...reais, 1);
  const ys = (v: number) => T + 14 + ((sMax - v) / (sMax - sMin || 1)) * (H - T - B - 28);
  const pts = semanas.map((s, i) => (s.saldo === null ? null : { i, x: cx(i), y: ys(num(s.saldo)), proj: s.projecao }));
  const trecho = (proj: boolean) => {
    const l = pts.filter((p): p is NonNullable<typeof p> => !!p && (p.proj === proj || (proj && !p.proj && !!pts[p.i + 1]?.proj)));
    return l.map((p, n) => `${n ? "L" : "M"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join("");
  };
  return (
    <>
      <svg role="img" aria-label="Barras empilhadas por semana com saldo acumulado" viewBox={`0 0 ${W} ${H}`} className="grafico" style={{ width: "100%", height: "auto", overflow: "visible" }}>
        {semanas.map((s, i) => {
          const x = cx(i) - larg * 0.3, w = larg * 0.6;
          const estilo = { fillOpacity: s.projecao ? 0.4 : 1, strokeDasharray: s.projecao ? "3 2" : undefined, strokeWidth: 1 };
          let y1 = yz, y2 = yz;
          return (
            <g key={s.inicio} data-semana={s.inicio} data-projecao={s.projecao}>
              {s.inicio === escolhida && <rect x={cx(i) - larg / 2} y={T} width={larg} height={H - T - B} style={{ fill: "var(--acento-fundo)" }} />}
              {s.entradas.map((e) => { const h = Math.abs(num(e.valor)) * k; y1 -= h; return <rect key={e.categoria} x={x} y={y1} width={w} height={h} style={{ ...estilo, fill: corDe("entradas", ent, e.categoria), stroke: s.projecao ? "var(--tinta-3)" : "none" }} />; })}
              {s.saidas.map((e) => { const h = Math.abs(num(e.valor)) * k; const y = y2; y2 += h; return <rect key={e.categoria} x={x} y={y} width={w} height={h} style={{ ...estilo, fill: corDe("saidas", sai, e.categoria), stroke: s.projecao ? "var(--tinta-3)" : "none" }} />; })}
            </g>
          );
        })}
        <line x1={L} x2={W - R} y1={yz} y2={yz} style={{ stroke: "var(--tinta)" }} />
        <text x={L - 6} y={T + 8} style={{ fill: "var(--tinta-3)", font: "500 10.5px var(--mono)", textAnchor: "end" }}>{oculto ? "••••" : `+${Math.round(topo).toLocaleString("pt-BR")}`}</text>
        <text x={L - 6} y={H - B} style={{ fill: "var(--tinta-3)", font: "500 10.5px var(--mono)", textAnchor: "end" }}>{oculto ? "••••" : `-${Math.round(fundo).toLocaleString("pt-BR")}`}</text>
        <path d={trecho(false)} style={{ fill: "none", stroke: "var(--tinta)", strokeWidth: 1.75 }} />
        <path d={trecho(true)} style={{ fill: "none", stroke: "var(--tinta)", strokeWidth: 1.75, strokeDasharray: "4 4", strokeOpacity: 0.6 }} />
        {pts.map((p) => p && <circle key={p.i} cx={p.x} cy={p.y} r={3} style={{ fill: p.proj ? "var(--papel)" : "var(--tinta)", stroke: "var(--tinta)", strokeWidth: 1.25 }} />)}
        <text x={W - R + 8} y={T + 18} style={{ fill: "var(--tinta-3)", font: "500 10.5px var(--mono)" }}>{oculto ? "••••" : Math.round(sMax).toLocaleString("pt-BR")}</text>
        <text x={W - R + 8} y={H - B - 10} style={{ fill: "var(--tinta-3)", font: "500 10.5px var(--mono)" }}>{oculto ? "••••" : Math.round(sMin).toLocaleString("pt-BR")}</text>
        {semanas.map((s, i) => <text key={s.inicio} x={cx(i)} y={H - 8} style={{ fill: "var(--tinta-3)", font: `${s.inicio === escolhida ? 700 : 500} 10.5px var(--mono)`, textAnchor: "middle" }}>{dataCurta(s.inicio)}</text>)}
        {semanas.map((s, i) => (
          <rect key={s.inicio} x={cx(i) - larg / 2} y={T} width={larg} height={H - T - B} role="button" tabIndex={0} aria-label={`Semana de ${dataCurta(s.inicio)}`} aria-pressed={s.inicio === escolhida}
            onClick={() => aoEscolher(s.inicio)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && aoEscolher(s.inicio)} style={{ fill: "transparent", cursor: "pointer" }} />
        ))}
      </svg>
      <div className="legenda">
        {ent.map((c) => <span key={c}><span className="amostra-cor" style={{ background: corDe("entradas", ent, c) }} />{c}</span>)}
        {sai.map((c) => <span key={c}><span className="amostra-cor" style={{ background: corDe("saidas", sai, c) }} />{c}</span>)}
        <span><span className="amostra-traco" />saldo acumulado</span>
        <span><span className="amostra-cor" style={{ border: "1px dashed var(--tinta-3)" }} />projeção</span>
      </div>
    </>
  );
}
