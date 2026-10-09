import { vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { Lancamentos } from "../src/telas/Gastos/Lancamentos";
import { Cadastros } from "../src/telas/Cadastros";
import { amostra, apiFalsa } from "./apiFalsa";

const montar = (ui: React.ReactElement) => render(<ToastProvider><FiltrosProvider>{ui}</FiltrosProvider></ToastProvider>);
beforeEach(() => { localStorage.clear(); window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

const com = (nome: string, dados: object) => ({ ...amostra(nome), dados });
const P = (id: string, nome: string, papel: string | null, dados: object = {}) => ({ id, nome, papel, telefone: null, dados, origem: "x", excluido_em: null });
const pessoas = () => com("cadastros-pessoas", { itens: [
  P("ricardo", "Ricardo Esper", "titular"), P("louise", "Louise Lavrik Esper", "filha"), P("giovanna", "Giovanna Della Torre Esper", "filha"),
  P("carla", "Carla Noce Della Torre", "ex-esposa", { beneficiario: false }), P("casa", "Casa (todos)", "coletivo")] });
const lanc = (conta: string) => {
  const base = amostra("lancamentos-pendentes");
  return { ...base, dados: { ...base.dados, itens: [{ ...base.dados.itens[0], conta }] } };
};
const contas = (usuarios: string[]) => com("cadastros-contas", { itens: [{ id: 9, externo_id: "x", instituicao: "Itaú", tipo: "CREDIT", apelido: "VISA INFINITE  ", pj: false, estado: "sim", titular: "RICARDO", limite: null, nibo_account_id: null, usuarios, origem: "open_finance", excluido_em: null }] });

test("cartao com dois usuarios so oferece eles e os donos coletivos; quem so recebe nunca aparece", async () => {
  apiFalsa({ "lancamentos-pendentes": lanc("VISA INFINITE"), "cadastros-pessoas": pessoas(), "cadastros-contas": contas(["ricardo", "louise"]) });
  montar(<Lancamentos />);
  const grupo = await screen.findByRole("group", { name: /Para quem:/ });
  const nomes = within(grupo).getAllByRole("button").map((b) => b.textContent);
  expect(nomes).toEqual(["Ricardo Esper", "Louise Lavrik Esper", "Casa (todos)"]);
});

test("conta sem usuarios definidos oferece todos os beneficiarios, menos quem so recebe", async () => {
  apiFalsa({ "lancamentos-pendentes": lanc("OUTRA CONTA"), "cadastros-pessoas": pessoas(), "cadastros-contas": contas([]) });
  montar(<Lancamentos />);
  const grupo = await screen.findByRole("group", { name: /Para quem:/ });
  const nomes = within(grupo).getAllByRole("button").map((b) => b.textContent);
  expect(nomes).toEqual(["Ricardo Esper", "Louise Lavrik Esper", "Giovanna Della Torre Esper", "Casa (todos)"]);
});

test("Cadastros: marcar quem usa o cartao envia PATCH com a lista e nao oferece quem so recebe", async () => {
  const chamadas = apiFalsa({ "cadastros-pessoas": pessoas(), "cadastros-contas": contas(["ricardo"]) });
  montar(<Cadastros />);
  const grupo = await screen.findByRole("group", { name: "Quem usa VISA INFINITE" });
  const botoes = within(grupo).getAllByRole("button").map((b) => b.textContent);
  expect(botoes).toContain("Louise");
  expect(botoes).not.toContain("Carla");
  fireEvent.click(within(grupo).getByRole("button", { name: "Louise" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "PATCH" && /cadastros\/contas\/9$/.test(c.url))).toBe(true));
  expect(chamadas.find((c) => c.metodo === "PATCH")!.corpo).toEqual({ usuarios: ["ricardo", "louise"] });
});
