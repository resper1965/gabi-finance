import { GRUPOS, rotaParaTela } from "../src/navegacao";
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

test("o menu só tem áreas financeiras, na ordem final", () => {
  const areas = GRUPOS.flatMap((g) => g.areas);
  expect(areas.map((a) => a.id)).toEqual(["caixa", "gastos", "cobrar", "regras", "cadastros", "gabi"]);
  const abas = (id: string) => areas.find((a) => a.id === id)!.abas.map(([aba]) => aba);
  expect(abas("caixa")).toEqual(["contas", "projecao", "fluxo", "visao"]);
  expect(abas("gastos")).toEqual(["lanc", "destino", "cartao", "parcelas", "assin"]);
  expect(abas("cobrar")).toEqual(["areceber", "notas"]);
  expect(abas("cadastros")).toEqual(["cadastros", "despesas"]);
  expect(abas("gabi")).toEqual(["agentes"]);
});

test("a tela inicial é Caixa > A pagar", () => {
  expect(GRUPOS[0].areas[0].id).toBe("caixa");
  expect(GRUPOS[0].areas[0].abas[0][0]).toBe("contas");
  expect(rotaParaTela("/qualquer/coisa")).toEqual(["caixa", "contas"]);
});

test("nenhuma tela de área que saiu continua registrada", () => {
  for (const aba of ["hoje", "agenda", "envios", "atividades", "projetos", "prioridades", "documentos", "listacontatos", "agendas", "correio", "teams", "qualidade"]) {
    expect(aba in TELAS).toBe(false);
  }
});
