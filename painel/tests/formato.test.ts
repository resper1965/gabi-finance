import { afterEach, expect, test, vi } from "vitest";
import { diaSP, formatarBRL, horaDe, quandoVence } from "../src/lib/formato";

afterEach(() => vi.useRealTimers());

test("formatarBRL: R$ pt-BR com espaço normal, sinal na frente e traço se não for número", () => {
  expect(formatarBRL("1234.5")).toBe("R$ 1.234,50");
  expect(formatarBRL(-1)).toBe("-R$ 1,00");
  expect(formatarBRL("-1")).toBe("-R$ 1,00");
  expect(formatarBRL("abc")).toBe("—");
});

test("horaDe: HH:MM do ISO, null sem hora", () => {
  expect(horaDe("2026-11-04T09:30:00")).toBe("09:30");
  expect(horaDe("2026-11-04")).toBeNull();
});

test("diaSP: dia no fuso de São Paulo, não no UTC", () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date("2026-11-05T01:00:00Z"));
  expect(diaSP()).toBe("2026-11-04");
  expect(diaSP(1)).toBe("2026-11-05");
});

test("quandoVence: data curta, com hora só quando tem_hora", () => {
  expect(quandoVence(null, false)).toBe("");
  expect(quandoVence("2026-11-04", false)).toBe("04/11");
  expect(quandoVence("2026-11-04T09:30:00", true)).toBe("04/11 às 09:30");
});
