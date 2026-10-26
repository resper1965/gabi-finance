import { vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { Lancamentos } from "../src/telas/Gastos/Lancamentos";
import { Cartoes } from "../src/telas/Gastos/Cartoes";
import { amostra, apiFalsa } from "./apiFalsa";

const montar = (ui: React.ReactElement) => render(<ToastProvider><FiltrosProvider>{ui}</FiltrosProvider></ToastProvider>);
beforeEach(() => { localStorage.clear(); window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

const comCompra = (empresa: object) => {
  const base = amostra("lancamentos-pendentes");
  return { ...base, dados: { ...base.dados, itens: [{ ...base.dados.itens[0], valor: "-120.00", estabelecimento: "UBER", empresa }] } };
};

test("reembolso por compra em Lançamentos grava a empresa pelo id de texto", async () => {
  const chamadas = apiFalsa({ "lancamentos-pendentes": comCompra({ id: null, nome: null, origem: null }) });
  montar(<Lancamentos />);
  const sel = await screen.findByRole("combobox", { name: "Reembolso: UBER" });
  await screen.findByRole("option", { name: "Ness" });
  fireEvent.change(sel, { target: { value: "e1" } });
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "PATCH" && JSON.stringify(c.corpo) === JSON.stringify({ empresa_id: "e1" }))).toBe(true));
});

test("reembolso marcado pode voltar a pessoal", async () => {
  const chamadas = apiFalsa({ "lancamentos-pendentes": comCompra({ id: "e1", nome: "Ness", origem: "voce" }) });
  montar(<Lancamentos />);
  await screen.findByRole("option", { name: "Ness" });
  const sel = screen.getByRole("combobox", { name: "Reembolso: UBER" }) as HTMLSelectElement;
  await waitFor(() => expect(sel.value).toBe("e1"));
  fireEvent.change(sel, { target: { value: "" } });
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "PATCH" && JSON.stringify(c.corpo) === JSON.stringify({ empresa_id: null }))).toBe(true));
});

test("lote de Cartões manda o id da empresa como texto, não NaN", async () => {
  const chamadas = apiFalsa();
  montar(<Cartoes />);
  await waitFor(() => expect(document.querySelectorAll("tbody tr input[type=checkbox]").length).toBeGreaterThan(0));
  fireEvent.click(document.querySelector("tbody tr input[type=checkbox]")!);
  await screen.findByRole("option", { name: "Reembolso Ness" });
  fireEvent.change(screen.getByRole("combobox", { name: "Nova empresa" }), { target: { value: "e1" } });
  fireEvent.click(screen.getByRole("button", { name: "Aplicar" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && c.url.includes("/lancamentos/lote"))).toBe(true));
  const corpo = chamadas.find((c) => c.metodo === "POST" && c.url.includes("/lancamentos/lote"))!.corpo as { mudancas: { empresa_id: unknown } };
  expect(corpo.mudancas.empresa_id).toBe("e1");
});
