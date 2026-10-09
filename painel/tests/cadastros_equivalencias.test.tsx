import { vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { CadastrosEquivalencias } from "../src/telas/CadastrosEquivalencias";
import { amostra, apiFalsa } from "./apiFalsa";

const montar = (ui: React.ReactElement) => render(<ToastProvider><FiltrosProvider>{ui}</FiltrosProvider></ToastProvider>);
beforeEach(() => { localStorage.clear(); window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

const env = (nome: string, dados: object) => ({ ...amostra("cadastros-categorias"), dados });
const pendentes = (itens: object[]) => env("x", { itens });
const categorias = () => env("x", { itens: [
  { id: 1, nome: "Pessoal", pai_id: null, nibo_category_id: null, excluido_em: null },
  { id: 2, nome: "Mercado", pai_id: 1, nibo_category_id: null, excluido_em: null }] });

test("lista as categorias do banco sem equivalencia, com o volume, e oferece so categorias (nao grupos)", async () => {
  apiFalsa({ "equivalencias-pendentes": pendentes([{ origem_pluggy: "Eating out", lancamentos: 639 }]), "cadastros-categorias": categorias() });
  montar(<CadastrosEquivalencias />);
  const bloco = await screen.findByRole("region", { name: "Categorias do banco sem equivalência" });
  expect(within(bloco).getByText("Eating out")).toBeTruthy();
  expect(within(bloco).getByText("639 lançamentos")).toBeTruthy();
  const opcoes = within(bloco).getAllByRole("option").map((o) => o.textContent);
  expect(opcoes).toContain("Mercado");
  expect(opcoes).not.toContain("Pessoal");
});

test("escolher a categoria e salvar envia a equivalencia (PUT) e o botao so vale depois de escolher", async () => {
  const chamadas = apiFalsa({ "equivalencias-pendentes": pendentes([{ origem_pluggy: "Groceries", lancamentos: 368 }]), "cadastros-categorias": categorias() });
  montar(<CadastrosEquivalencias />);
  const bloco = await screen.findByRole("region", { name: "Categorias do banco sem equivalência" });
  const salvar = within(bloco).getByRole("button", { name: "Salvar Groceries" }) as HTMLButtonElement;
  expect(salvar.disabled).toBe(true);
  fireEvent.change(within(bloco).getByLabelText("Categoria para Groceries"), { target: { value: "2" } });
  expect(salvar.disabled).toBe(false);
  fireEvent.click(salvar);
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "PUT" && /categorias\/equivalencias$/.test(c.url))).toBe(true));
  expect(chamadas.find((c) => c.metodo === "PUT")!.corpo).toEqual({ origem_pluggy: "Groceries", categoria_id: 2 });
});

test("sem pendencias mostra que esta tudo equivalente", async () => {
  apiFalsa({ "equivalencias-pendentes": pendentes([]), "cadastros-categorias": categorias() });
  montar(<CadastrosEquivalencias />);
  expect(await screen.findByText("Todas as categorias que o banco usa já têm equivalência.")).toBeTruthy();
});
