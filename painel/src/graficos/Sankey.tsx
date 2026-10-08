import { num } from "../lib/formato";

export interface No { nome: string; tipo: "origem" | "categoria" | "destino" }
export interface Fluxo { de: string; para: string; valor: string }

const RAMPA = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)"];
const EMPRESA: [RegExp, string][] = [[/ness/i, "var(--ness)"], [/ionic/i, "var(--ionic)"], [/bekaa/i, "var(--bekaa)"]];
/** Cor do destino: cada empresa tem sempre a mesma cor; consumo pessoal usa a cor "pessoal". */
export const corDestino = (nome: string) => EMPRESA.find(([r]) => r.test(nome))?.[1] ?? "var(--pes)";

/** Sankey origem → categoria → destino final em fitas (SVG próprio). Tocar num nó ou fluxo chama aoEscolher(nome). */
export function Sankey({ nos, fluxos, aoEscolher, escolhido }: { nos: No[]; fluxos: Fluxo[]; aoEscolher: (n: No) => void; escolhido?: string | null }) {
  const W = 760, A = 360, nw = 12, m = 150, pad = 8;
  const col: Record<No["tipo"], No[]> = { origem: [], categoria: [], destino: [] };
  nos.forEach((n) => col[n.tipo].push(n));
  const peso = (n: No) => Math.max(fluxos.filter((f) => f.de === n.nome).reduce((s, f) => s + num(f.valor), 0), fluxos.filter((f) => f.para === n.nome).reduce((s, f) => s + num(f.valor), 0));
  const total = Math.max(1, ...Object.values(col).map((c) => c.reduce((s, n) => s + peso(n), 0)));
  const maxN = Math.max(1, ...Object.values(col).map((c) => c.length));
  const k = (A - 2 * pad - (maxN - 1) * pad) / total;
  const xs = { origem: m, categoria: (W - nw) / 2, destino: W - m - nw };
  const pos = new Map<string, { x: number; y: number; h: number; saiu: number; entrou: number; cor: string; tipo: No["tipo"] }>();
  (Object.keys(col) as No["tipo"][]).forEach((t) => {
    let y = pad;
    col[t].sort((a, b) => peso(b) - peso(a)).forEach((n, i) => {
      const h = Math.max(3, peso(n) * k);
      pos.set(n.nome, { x: xs[t], y, h, saiu: 0, entrou: 0, tipo: t, cor: t === "origem" ? "var(--s2)" : t === "categoria" ? RAMPA[i % RAMPA.length] : corDestino(n.nome) });
      y += h + pad;
    });
  });
  const fita = (x0: number, y0: number, x1: number, y1: number, h: number) => {
    const xm = (x0 + x1) / 2;
    return `M${x0},${y0}C${xm},${y0} ${xm},${y1} ${x1},${y1}L${x1},${y1 + h}C${xm},${y1 + h} ${xm},${y0 + h} ${x0},${y0 + h}Z`;
  };
  const tipoDe = (nome: string) => nos.find((n) => n.nome === nome)!;
  return (
    <div style={{ overflowX: "auto" }}>
      <svg role="img" aria-label="Sankey: contas e cartões, categorias e destino final" viewBox={`0 0 ${W} ${A}`} style={{ width: "100%", minWidth: 560, height: "auto", display: "block", overflow: "visible" }}>
        {fluxos.map((f, i) => {
          const a = pos.get(f.de), b = pos.get(f.para);
          if (!a || !b) return null;
          const h = Math.max(1, num(f.valor) * k);
          const y0 = a.y + a.saiu, y1 = b.y + b.entrou;
          a.saiu += h; b.entrou += h;
          const ativo = !escolhido || escolhido === f.de || escolhido === f.para;
          return <path key={i} d={fita(a.x + nw, y0, b.x, y1, h)} onClick={() => aoEscolher(tipoDe(f.para))} style={{ fill: "var(--flow)", fillOpacity: ativo ? 0.5 : 0.15, cursor: "pointer" }}><title>{f.de} → {f.para}: {f.valor}</title></path>;
        })}
        {nos.map((n) => {
          const p = pos.get(n.nome)!;
          const direita = p.tipo === "destino";
          const lx = direita ? p.x - 6 : p.x + nw + 6;
          return (
            <g key={n.nome + n.tipo} role="button" tabIndex={0} aria-label={n.nome} onClick={() => aoEscolher(n)} onKeyDown={(e) => e.key === "Enter" && aoEscolher(n)} style={{ cursor: "pointer", opacity: !escolhido || escolhido === n.nome ? 1 : 0.55 }}>
              <rect x={p.x} y={p.y} width={nw} height={p.h} style={{ fill: p.cor }} />
              <text x={p.tipo === "origem" ? p.x - 6 : lx} y={p.y + Math.min(p.h / 2, 12) + 4} style={{ fill: "var(--color-text)", font: "600 12px var(--font-body)", textAnchor: p.tipo === "origem" ? "end" : direita ? "end" : "start", paintOrder: "stroke", stroke: "var(--color-bg)", strokeWidth: 3, strokeLinejoin: "round" }}>{n.nome}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
