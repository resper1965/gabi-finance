import { num } from "../lib/formato";

export interface Celula { nome: string; valor: string }

/** Treemap simples (fatias alternando horizontal/vertical): área = quanto saiu. Tocar numa célula chama aoEscolher(nome). */
export function Treemap({ itens, aoEscolher, largura = 760, altura = 320 }: { itens: Celula[]; aoEscolher: (nome: string) => void; largura?: number; altura?: number }) {
  const lista = itens.filter((i) => num(i.valor) > 0).sort((a, b) => num(b.valor) - num(a.valor));
  const total = lista.reduce((s, i) => s + num(i.valor), 0) || 1;
  const celulas: { nome: string; valor: string; x: number; y: number; w: number; h: number }[] = [];
  let x = 0, y = 0, w = largura, h = altura, resto = total, horizontal = w >= h;
  lista.forEach((it, i) => {
    const frac = num(it.valor) / resto;
    if (i === lista.length - 1) celulas.push({ ...it, x, y, w, h });
    else if (horizontal) { const lw = w * frac; celulas.push({ ...it, x, y, w: lw, h }); x += lw; w -= lw; }
    else { const lh = h * frac; celulas.push({ ...it, x, y, w, h: lh }); y += lh; h -= lh; }
    resto -= num(it.valor);
    if (i % 2 === 1) horizontal = w >= h;
  });
  return (
    <div style={{ position: "relative", height: altura, maxWidth: largura }}>
      {celulas.map((c) => (
        <button key={c.nome} onClick={() => aoEscolher(c.nome)} style={{ position: "absolute", left: c.x, top: c.y, width: c.w, height: c.h, border: "1px solid var(--line3)", background: "transparent", color: "inherit", padding: 8, display: "flex", flexDirection: "column", alignItems: "flex-start", textAlign: "left", cursor: "pointer", overflow: "hidden", font: "inherit" }}>
          <span style={{ fontWeight: 600, fontSize: 13, lineHeight: 1.2 }}>{c.nome}</span>
          <span style={{ font: "500 11.5px var(--mono)", color: "var(--ink2)" }}>{Math.round((num(c.valor) / total) * 100)}%</span>
        </button>
      ))}
    </div>
  );
}
