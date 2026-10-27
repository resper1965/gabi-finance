import { GRUPOS } from "../src/navegacao";
import { TELAS } from "../src/App";

test("toda aba do menu tem uma tela registrada", () => {
  const sem = GRUPOS.flatMap((g) => g.areas.flatMap((a) => a.abas.map(([aba]) => aba))).filter((aba) => !(aba in TELAS));
  expect(sem).toEqual([]);
});

test("Cadastros tem a aba Despesas", () => {
  const cadastros = GRUPOS.flatMap((g) => g.areas).find((a) => a.id === "cadastros")!;
  expect(cadastros.abas).toContainEqual(["despesas", "Despesas", "O que eu pago todo mês, e o que é uma vez só?"]);
  expect("despesas" in TELAS).toBe(true);
});
