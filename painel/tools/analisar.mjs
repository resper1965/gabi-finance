// Falha se algum JS do build passar de 150 KB gzip (orçamento por rota, plano T1.11).
import { readdirSync, readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { join } from "node:path";

const dir = join(import.meta.dirname, "..", "..", "gabi", "painel", "assets");
let ruim = 0;
for (const f of readdirSync(dir).filter((x) => x.endsWith(".js"))) {
  const kb = gzipSync(readFileSync(join(dir, f))).length / 1024;
  console.log(`${f}: ${kb.toFixed(1)} KB gzip`);
  if (kb > 150) ruim++;
}
process.exit(ruim ? 1 : 0);
