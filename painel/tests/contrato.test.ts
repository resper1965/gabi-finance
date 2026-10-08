import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

function arquivos(d: string): string[] {
  return readdirSync(d).flatMap((f) => (statSync(join(d, f)).isDirectory() ? arquivos(join(d, f)) : [join(d, f)]));
}

test("telas so usam rotas que existem em docs/openapi.json", () => {
  const openapi = JSON.parse(readFileSync(join(__dirname, "..", "..", "docs", "openapi.json"), "utf-8")).paths as Record<string, Record<string, unknown>>;
  const rotas = Object.entries(openapi).map(([p, m]) => ({ rx: new RegExp(`^${p.replace(/\{[^}]+\}/g, "[^/]+")}$`), metodos: Object.keys(m).map((x) => x.toUpperCase()) }));
  const usos: string[] = [];
  for (const f of arquivos(join(__dirname, "..", "src")).filter((x) => /\.tsx?$/.test(x))) {
    for (const linha of readFileSync(f, "utf-8").split("\n")) {
      for (const m of linha.matchAll(/[`"'](\/api\/v1\/[^`"'?]*)/g)) {
        const metodo = /api\.post/.test(linha) ? "POST" : /api\.patch/.test(linha) ? "PATCH" : "GET";
        usos.push(`${metodo} ${m[1].replace(/\$\{[^}]*\}/g, "x")} (${f.split("/src/")[1]})`);
      }
    }
  }
  expect(usos.length).toBeGreaterThan(10);
  const faltam = usos.filter((u) => {
    const [metodo, caminho] = u.split(" ");
    return !rotas.some((r) => r.rx.test(caminho) && r.metodos.includes(metodo));
  });
  expect(faltam).toEqual([]);
});
