import { GRUPOS } from "../src/navegacao";
import { TELAS } from "../src/App";

test("toda aba do menu tem uma tela registrada", () => {
  const sem = GRUPOS.flatMap((g) => g.areas.flatMap((a) => a.abas.map(([aba]) => aba))).filter((aba) => !(aba in TELAS));
  expect(sem).toEqual([]);
});
