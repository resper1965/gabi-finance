import { render } from "@testing-library/react";
import { LinhaSaldo } from "../src/graficos/LinhaSaldo";

test("LinhaSaldo com o mesmo saldo todos os dias não fica com faixa de altura zero", () => {
  const pontos = ["2026-11-01", "2026-11-02", "2026-11-03"].map((data) => ({ data, valor: "1000.00", projecao: false }));
  const { container } = render(<LinhaSaldo pontos={pontos} />);
  const d = container.querySelector("path")?.getAttribute("d") ?? "";
  const ys = [...d.matchAll(/[ML]\s*[\d.]+[ ,]([\d.]+)/g)].map((m) => Number(m[1]));
  expect(ys.length).toBeGreaterThan(0);
  expect(ys.every((y) => Number.isFinite(y))).toBe(true);
  expect(ys.some((y) => Math.abs(y - 16) > 1)).toBe(true); // sem a correção a linha inteira cola no topo (y = 16)
});
