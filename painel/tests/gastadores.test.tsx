import { vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { Lancamentos } from "../src/telas/Gastos/Lancamentos";
import { ParaOndeVai } from "../src/telas/Gastos/ParaOndeVai";
import { amostra, apiFalsa } from "./apiFalsa";

const montar = (ui: React.ReactElement) => render(<ToastProvider><FiltrosProvider>{ui}</FiltrosProvider></ToastProvider>);
beforeEach(() => { localStorage.clear(); window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

const P = (id: string, nome: string) => ({ id, nome, papel: null, telefone: null, dados: {}, origem: "x", excluido_em: null });
const pessoas = { ...amostra("cadastros-pessoas"), dados: { itens: [P("ricardo", "Ricardo"), P("louise", "Louise"), P("carla", "Carla")] } };
const comLanc = (extra: object) => {
  const base = amostra("lancamentos-pendentes");
  return { ...base, dados: { ...base.dados, itens: [{ ...base.dados.itens[0], estabelecimento: "ZARA", gastador: { id: null, nome: null, origem: null }, ...extra }] } };
};

test("cartao compartilhado oferece so os portadores e indicar envia gastador_id", async () => {
  const chamadas = apiFalsa({ "lancamentos-pendentes": comLanc({ portadores: ["ricardo", "louise"] }), "cadastros-pessoas": pessoas });
  montar(<Lancamentos />);
  const grupo = await screen.findByRole("group", { name: "Quem gastou: ZARA" });
  expect(within(grupo).getAllByRole("button").map((b) => b.textContent)).toEqual(["Ricardo", "Louise"]);
  fireEvent.click(within(grupo).getByRole("button", { name: "Louise" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && c.url.includes("/lancamentos/lote")
    && JSON.stringify((c.corpo as { mudancas: object }).mudancas) === JSON.stringify({ gastador_id: "louise" }))).toBe(true));
});

test("cartao de um portador nao pede quem gastou", async () => {
  apiFalsa({ "lancamentos-pendentes": comLanc({ portadores: ["ricardo"] }), "cadastros-pessoas": pessoas });
  montar(<Lancamentos />);
  await screen.findByText("ZARA");
  expect(screen.queryByRole("group", { name: "Quem gastou: ZARA" })).toBeNull();
});

test("filtro a indicar pede pendente=gastador", async () => {
  const chamadas = apiFalsa({ "cadastros-pessoas": pessoas });
  montar(<Lancamentos />);
  fireEvent.click(await screen.findByRole("button", { name: "Quem gastou: a indicar" }));
  await waitFor(() => expect(chamadas.some((c) => c.url.includes("pendente=gastador"))).toBe(true));
});

test("Para onde vai tem a vista Quem gastou", async () => {
  const chamadas = apiFalsa();
  montar(<ParaOndeVai />);
  fireEvent.click(await screen.findByRole("button", { name: "Quem gastou" }));
  await waitFor(() => expect(chamadas.some((c) => c.url.includes("por=gastador"))).toBe(true));
  expect(screen.getByRole("button", { name: "Para quem foi" })).toBeTruthy();
});
