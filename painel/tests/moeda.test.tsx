import { originalEmReais } from "../src/lib/formato";

test("compra em moeda estrangeira mostra original e reais", () => {
  expect(originalEmReais({ valor: "-31.32", moeda: "USD", valor_original: "-6.01", convertido: true })).toBe("US$ 6,01 → R$ 31,32");
  expect(originalEmReais({ valor: "10.00", moeda: "EUR", valor_original: "2.00", convertido: true })).toBe("€ 2,00 → R$ 10,00");
  expect(originalEmReais({ valor: "-5.00", moeda: "PEN", valor_original: "-1.50", convertido: true })).toBe("PEN 1,50 → R$ 5,00");
});
test("sem moeda estrangeira não mostra nada; sem conversão avisa", () => {
  expect(originalEmReais({ valor: "-5.00" })).toBeNull();
  expect(originalEmReais({ valor: "-6.01", moeda: "USD", valor_original: "-6.01", convertido: false })).toBe("US$ 6,01 (sem conversão para reais)");
});
