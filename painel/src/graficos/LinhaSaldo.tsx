import { useEffect, useRef, useState, type ReactNode } from "react";
import { Evidencia, type InfoEvidencia } from "../componentes/Evidencia";
import { Valor } from "../componentes/Valor";
import { dataCurta, num } from "../lib/formato";

export interface Ponto { data: string; valor: string; projecao: boolean }

const DIA = 86_400_000;
const dia = (iso: string) => Date.UTC(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10))) / DIA;
const brl = (n: number) => `R$ ${Math.round(n).toLocaleString("pt-BR")}`;

/** Passo "redondo" (1, 2, 2,5, 5 × 10ⁿ) para 3 a 4 marcas no eixo. */
function passo(faixa: number) {
  const bruto = faixa / 3 || 1, mag = 10 ** Math.floor(Math.log10(bruto));
  return ([1, 2, 2.5, 5, 10].find((m) => m * mag >= bruto) ?? 10) * mag;
}

interface Rotulo { x: number; y: number; conteudo: ReactNode; chars: number; cor?: string }

/** Saldo realizado (cheio) e projetado (tracejado) no tempo real (x pela data, não pela posição na lista), com "hoje",
 *  o menor saldo projetado marcado (com a etiqueta de evidência) e, se for outro ponto, o menor saldo do período.
 *  Os rótulos são HTML sobre o desenho: ficam legíveis em qualquer largura e nunca cruzam a linha. */
export function LinhaSaldo({ pontos, oculto = false, largura = 680, altura = 230, evidencia }: { pontos: Ponto[]; oculto?: boolean; largura?: number; altura?: number; evidencia?: InfoEvidencia }) {
  const caixa = useRef<HTMLDivElement>(null);
  const [px, setPx] = useState(largura);
  useEffect(() => {
    const el = caixa.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setPx(e.contentRect.width || largura));
    ro.observe(el);
    return () => ro.disconnect();
  }, [largura]);
  if (pontos.length < 2) return <p className="suave">Poucos dias de saldo para desenhar a linha.</p>;

  const W = largura, H = altura, L = 70, R = 14, T = 16, B = 26;
  const k = W / Math.max(1, px); // unidades do desenho por pixel na tela
  const vs = pontos.map((p) => num(p.valor));
  const st = passo(Math.max(...vs) - Math.min(...vs));
  const lo = Math.floor(Math.min(...vs) / st) * st;
  const teto = Math.ceil(Math.max(...vs) / st) * st;
  const hi = teto > lo ? teto : lo + st; // saldo igual todos os dias (ou zero): a faixa nunca fica com altura zero
  const d0 = dia(pontos[0].data), d1 = dia(pontos[pontos.length - 1].data);
  const x = (iso: string) => L + ((dia(iso) - d0) / Math.max(1, d1 - d0)) * (W - L - R);
  const y = (v: number) => T + ((hi - v) / (hi - lo || 1)) * (H - T - B);
  const ticks: number[] = [];
  for (let t = lo; t <= hi + st / 2; t += st) ticks.push(t);
  const reais = pontos.filter((p) => !p.projecao);
  const ultimoReal = reais[reais.length - 1];
  const proj = pontos.filter((p) => p.projecao);
  const trechoProj = ultimoReal && proj.length ? [ultimoReal, ...proj] : proj;
  const caminho = (l: Ponto[]) => l.map((p, i) => `${i ? "L" : "M"}${x(p.data).toFixed(1)},${y(num(p.valor)).toFixed(1)}`).join("");
  const xy = pontos.map((p) => [x(p.data), y(num(p.valor))] as const);
  const yNaLinha = (xv: number) => {
    for (let i = 1; i < xy.length; i++) if (xv <= xy[i][0]) { const [a, b] = [xy[i - 1], xy[i]]; return a[1] + ((b[1] - a[1]) * (xv - a[0])) / ((b[0] - a[0]) || 1); }
    return null;
  };

  const menorDe = (l: Ponto[]) => l.reduce((a, b) => (num(b.valor) < num(a.valor) ? b : a));
  const menorProj = proj.length ? menorDe(proj) : null;
  const menorGeral = menorDe(pontos);
  const marcas: { p: Ponto; principal: boolean }[] = [];
  if (menorProj) marcas.push({ p: menorProj, principal: true });
  if (!menorProj || num(menorGeral.valor) < num(menorProj.valor)) marcas.push({ p: menorGeral, principal: !menorProj });

  // posição do rótulo: a primeira, entre oito candidatas, que não cruza a linha, não sai da área e não cobre outro rótulo
  const ocupados: [number, number, number, number][] = [];
  const posicionar = (mx: number, my: number, chars: number): [number, number] => {
    const w = (chars * 7 + 14) * k, h = 22 * k, g = 7 * k;
    const cands: [number, number][] = [[mx + g, my - g - h], [mx - g - w, my - g - h], [mx + g, my + g], [mx - g - w, my + g],
      [mx - w / 2, my - 2 * g - h], [mx - w / 2, my + 2 * g], [mx - w / 2, T], [L + 4 * k, H - B - h - 2 * k]];
    const livre = ([bx, by]: [number, number]) => {
      if (bx < L - 2 || bx + w > W - R + 2 || by < 0 || by + h > H - B) return false;
      for (let xv = bx; xv <= bx + w; xv += 2) { const yl = yNaLinha(xv); if (yl !== null && yl > by - 3 * k && yl < by + h + 3 * k) return false; }
      return !ocupados.some(([ox, oy, ow, oh]) => bx < ox + ow && bx + w > ox && by < oy + oh && by + h > oy);
    };
    const achado = cands.find(livre);
    const [bx, by] = achado ?? [Math.min(Math.max(L, cands[0][0]), W - R - w), Math.min(Math.max(0, cands[0][1]), H - B - h)];
    ocupados.push([bx, by, w, h]);
    return [bx, by];
  };
  // junto do ponto vai só a etiqueta de evidência (curta, cabe sem cruzar a linha); o texto inteiro de cada marca vai na legenda abaixo
  const rotulos: Rotulo[] = marcas.filter((m) => m.principal && evidencia).map(({ p, principal }) => {
    const curto = principal && evidencia ? evidencia.codigo : `mín. ${dataCurta(p.data)}`;
    const [bx, by] = posicionar(x(p.data), y(num(p.valor)), curto.length);
    return {
      x: bx, y: by, chars: curto.length, cor: num(p.valor) < 0 ? "var(--carimbo-vermelho)" : undefined,
      conteudo: principal && evidencia ? <Evidencia {...evidencia}>{null}</Evidencia> : <span>{curto}</span>,
    };
  });
  const titulo = (principal: boolean, p: Ponto) => (principal && p.projecao ? "menor saldo projetado" : "menor saldo no período");

  return (
    <div ref={caixa} className="linha-saldo" style={{ position: "relative" }}>
      <svg role="img" aria-label={`Saldo dos últimos dias e projeção; menor saldo ${menorProj ? "projetado " : ""}${oculto ? "oculto" : brl(num((menorProj ?? menorGeral).valor))} em ${dataCurta((menorProj ?? menorGeral).data)}`}
        viewBox={`0 0 ${W} ${H}`} className="grafico" style={{ width: "100%", height: "auto", overflow: "visible" }}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} style={{ stroke: t === 0 ? "var(--carimbo-vermelho)" : "var(--regra)" }} />
            <text x={L - 8} y={y(t) + 3.5} className="eixo" style={{ textAnchor: "end" }}>{oculto ? "R$ ••••" : brl(t)}</text>
          </g>
        ))}
        {ultimoReal && proj.length > 0 && <>
          <line x1={x(ultimoReal.data)} x2={x(ultimoReal.data)} y1={T} y2={H - B} style={{ stroke: "var(--regra-forte)", strokeDasharray: "2 3" }} />
          <text x={x(ultimoReal.data) - 4} y={T + 8} style={{ textAnchor: "end" }}>hoje</text>
        </>}
        <path d={caminho(reais)} style={{ fill: "none", stroke: "var(--tinta)", strokeWidth: 2, strokeLinejoin: "round" }} />
        {trechoProj.length > 1 && <path data-projecao d={caminho(trechoProj)} style={{ fill: "none", stroke: "var(--acento)", strokeWidth: 2, strokeDasharray: "5 4" }} />}
        {marcas.map(({ p, principal }) => {
          const neg = num(p.valor) < 0;
          return <circle key={p.data} data-menor-saldo={principal || undefined} cx={x(p.data)} cy={y(num(p.valor))} r={principal ? 5 : 4}
            style={{ fill: "var(--papel)", stroke: neg ? "var(--carimbo-vermelho)" : principal ? "var(--acento)" : "var(--tinta)", strokeWidth: 2 }} />;
        })}
        {[...new Set([0, Math.floor((pontos.length - 1) / 2), pontos.length - 1])].map((i) => (
          <text key={i} x={x(pontos[i].data)} y={H - 6} style={{ textAnchor: i === 0 ? "start" : i === pontos.length - 1 ? "end" : "middle" }}>{dataCurta(pontos[i].data)}</text>))}
      </svg>
      {rotulos.map((r, i) => (
        <span key={i} className="grafico-rotulo" style={{ left: `${(r.x / W) * 100}%`, top: `${(r.y / H) * 100}%`, color: r.cor }}>{r.conteudo}</span>
      ))}
      <ul className="grafico-marcas">
        {marcas.map(({ p, principal }) => (
          <li key={p.data} style={{ color: num(p.valor) < 0 ? "var(--carimbo-vermelho)" : undefined }}>
            <span className="grafico-marca" data-principal={principal || undefined} aria-hidden="true" />
            <span>{titulo(principal, p)} <strong className="num"><Valor valor={p.valor} /></strong> em <span className="mono">{dataCurta(p.data)}</span>{principal && evidencia ? <> · <span className="mono">{evidencia.codigo}</span></> : null}</span>
          </li>))}
      </ul>
    </div>
  );
}
