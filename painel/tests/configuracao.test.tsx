import { vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { Configuracao } from "../src/telas/Configuracao";
import { apiFalsa } from "./apiFalsa";

beforeEach(() => { localStorage.clear(); window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

test("mostra os 7 passos e testa a conexao de um deles", async () => {
  const chamadas = apiFalsa({}, [[/setup\/nibo$/, { dados_ate: null, desatualizado: false, fontes: [], dados: { ok: false, detalhe: "O Nibo não está configurado", estado: "pendente" } }]]);
  render(<ToastProvider><FiltrosProvider><Configuracao /></FiltrosProvider></ToastProvider>);
  expect(await screen.findByText(/1\. Microsoft 365/)).toBeTruthy();
  expect(screen.getAllByRole("button", { name: "Testar conexão" })).toHaveLength(7);
  fireEvent.click(screen.getAllByRole("button", { name: "Testar conexão" })[3]);
  await waitFor(() => expect(chamadas.find((c) => c.metodo === "POST" && /setup\/nibo$/.test(c.url))!.corpo).toEqual({ acao: "testar" }));
  expect((await screen.findAllByRole("status")).some((e) => /✗ O Nibo não está configurado/.test(e.textContent ?? ""))).toBe(true);
});

test("nenhum campo pede senha ou token", async () => {
  apiFalsa();
  render(<ToastProvider><FiltrosProvider><Configuracao /></FiltrosProvider></ToastProvider>);
  await screen.findByText(/1\. Microsoft 365/);
  expect(document.querySelectorAll("input")).toHaveLength(0);
});
