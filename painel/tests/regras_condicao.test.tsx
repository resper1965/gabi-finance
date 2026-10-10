import { textoCondicao } from "../src/telas/Regras";

test("descreve a condição da regra em português", () => {
  expect(textoCondicao(null)).toBe("");
  expect(textoCondicao({})).toBe("");
  expect(textoCondicao({ conta_id: [1, 2], dias_semana: [5, 6] })).toBe("só se: conta 1, 2 · sáb, dom");
  expect(textoCondicao({ valor_min: 1000, valor_max: 5000 })).toBe("só se: de R$ 10,00 a R$ 50,00");
  expect(textoCondicao({ valor_min: 5000 })).toBe("só se: a partir de R$ 50,00");
  expect(textoCondicao({ valor_max: 5000 })).toBe("só se: até R$ 50,00");
});
