import { readFileSync, readdirSync, existsSync, statSync } from "node:fs";
import { join } from "node:path";

const ler = (p: string) => readFileSync(join(__dirname, "..", p), "utf-8");
const tokens = ler("src/tema/tokens.css");
const claro = tokens.split('[data-theme="dark"]')[0];
const escuro = tokens.split('[data-theme="dark"]')[1].split(":root {")[0];
const cores = (bloco: string) => Object.fromEntries([...bloco.matchAll(/(--[\w-]+):\s*oklch\(([\d.]+) ([\d.]+) ([\d.]+)/g)].map((m) => [m[1], [Number(m[2]), Number(m[3]), Number(m[4])]]));

/** OKLCH → luminância relativa (sRGB linear, recortado), para a razão de contraste da WCAG. */
function luminancia([L, C, h]: number[]) {
  const a = C * Math.cos((h * Math.PI) / 180), b = C * Math.sin((h * Math.PI) / 180);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3, m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3, s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const rgb = [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s, -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s].map((x) => Math.min(1, Math.max(0, x)));
  return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
}
const contraste = (x: number[], y: number[]) => { const [a, b] = [luminancia(x), luminancia(y)].sort((p, q) => q - p); return (a + 0.05) / (b + 0.05); };

test("tokens: claro e escuro definem os mesmos papéis de cor", () => {
  const c = Object.keys(cores(claro)).sort(), e = Object.keys(cores(escuro)).sort();
  expect(e).toEqual(c);
  for (const t of ["--papel", "--folha", "--tinta", "--tinta-2", "--trilho", "--ambar", "--carimbo-vermelho", "--carimbo-verde", "--carimbo-azul", "--acento"]) expect(c).toContain(t);
});

test("texto com contraste de pelo menos 4,5:1 nos dois temas", () => {
  const pares: [string, string][] = [["--tinta", "--papel"], ["--tinta-2", "--papel"], ["--tinta-3", "--papel"], ["--tinta-2", "--papel-2"], ["--tinta-3", "--folha"],
    ["--acento", "--papel"], ["--sobre-acento", "--acento"], ["--carimbo-vermelho", "--papel"], ["--carimbo-verde", "--papel"], ["--carimbo-azul", "--papel"],
    ["--carimbo-grafite", "--papel"], ["--ambar-tinta", "--ambar"], ["--tinta", "--ambar-fundo"], ["--trilho-tinta", "--trilho"], ["--trilho-tinta-2", "--trilho"]];
  for (const bloco of [claro, escuro]) {
    const t = cores(bloco);
    for (const [frente, fundo] of pares) expect([frente, fundo, contraste(t[frente], t[fundo]) >= 4.5]).toEqual([frente, fundo, true]);
  }
});

test("tema sem @import nem URL externa", () => {
  for (const f of ["src/tema/tokens.css", "src/tema/laudo.css"]) expect(ler(f)).not.toMatch(/@import|https?:\/\//);
});

test("fontes servidas localmente (sem CDN) no codigo-fonte", () => {
  const raiz = join(__dirname, "..", "src");
  const arquivos: string[] = [];
  const andar = (d: string) => readdirSync(d).forEach((f) => {
    const p = join(d, f);
    statSync(p).isDirectory() ? andar(p) : arquivos.push(p);
  });
  andar(raiz);
  const ruins = arquivos.filter((a) => /googleapis|gstatic|cdn\./i.test(readFileSync(a, "utf-8")));
  expect(ruins).toEqual([]);
  expect(ler("src/main.tsx")).toContain("@fontsource-variable/public-sans");
  expect(ler("src/main.tsx")).toContain("@fontsource/jetbrains-mono");
});

test("nenhuma URL externa no build", () => {
  const dist = join(__dirname, "..", "..", "gabi", "painel");
  if (!existsSync(dist)) return; // so vale depois de `npm run build`
  const achados: string[] = [];
  const andar = (d: string) => readdirSync(d).forEach((f) => {
    const p = join(d, f);
    if (statSync(p).isDirectory()) return andar(p);
    if (/\.(js|css|html)$/.test(f) && /googleapis|gstatic|cdn\.jsdelivr|unpkg/.test(readFileSync(p, "utf-8"))) achados.push(p);
  });
  andar(dist);
  expect(achados).toEqual([]);
});
