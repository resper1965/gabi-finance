import { readFileSync, readdirSync, existsSync, statSync } from "node:fs";
import { join } from "node:path";

const ler = (p: string) => readFileSync(join(__dirname, "..", p), "utf-8");
const semImport = (css: string) => css.split("\n").filter((l) => !l.startsWith("@import")).join("\n").trimEnd();
const props = (css: string) => new Set([...css.matchAll(/(--[a-z0-9-]+)\s*:/gi)].map((m) => m[1]));

test("industry.css identico ao do prototipo (exceto @import)", () => {
  expect(semImport(ler("src/tema/industry.css"))).toBe(semImport(ler("tests/referencia/industry-original.css")));
});

test("industry.css nao tem @import nem URL externa", () => {
  expect(ler("src/tema/industry.css")).not.toMatch(/@import|https?:\/\//);
});

test("gabi.css nao redefine tokens do industry fora do tema escuro", () => {
  const industry = props(ler("src/tema/industry.css"));
  const claro = ler("src/tema/gabi.css").split('[data-theme="dark"]')[0];
  const repetidos = [...props(claro)].filter((p) => industry.has(p));
  expect(repetidos).toEqual([]);
});

test("tokens do README presentes com o valor exato", () => {
  const industry = ler("src/tema/industry.css");
  const gabi = ler("src/tema/gabi.css").replace(/\s+/g, "");
  const dentro = (css: string, token: string, valor: string) =>
    new RegExp(`${token}\\s*:\\s*${valor.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`).test(css);
  expect(dentro(industry, "--color-accent", "#5980a6")).toBe(true);
  expect(dentro(industry, "--radius-md", "4px")).toBe(true);
  expect(dentro(industry, "--space-3", "10.2px")).toBe(true);
  for (const t of [
    "--ink2:#56575a", "--hover:rgba(89,128,166,.08)", "--sel:#dfeaf6", "--mark:rgba(29,31,32,.28)",
    "--ness:oklch(0.60.12230)", "--ionic:oklch(0.550.13305)", "--bekaa:oklch(0.680.1365)", "--pes:#8a8b8f",
    "--danger:oklch(0.50.1625)", "--warn:oklch(0.50.165)", "--ok:oklch(0.470.09155)",
    "--flow:#a3adb7", "--bg:#141618".replace("--bg", "--color-bg"), "--ink2:#a9acb1", "--color-accent:#94bce3",
  ]) expect(gabi).toContain(t);
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
  expect(ler("src/main.tsx")).toContain("@fontsource/barlow-condensed");
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
