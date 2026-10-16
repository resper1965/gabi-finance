import { vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { Reembolso } from "../src/telas/Reembolso";
import { apiFalsa } from "./apiFalsa";

const montar = (ui: React.ReactElement) => render(<ToastProvider><FiltrosProvider>{ui}</FiltrosProvider></ToastProvider>);
const env = (dados: unknown) => ({ dados_ate: "2026-10-16T12:00:00Z", desatualizado: false, fontes: [], dados });
const doc = (id: number, estado: string) => ({ id, documento: "nf", caso: "consulta", estado, data: "2026-10-03" });
const dossie = (n: number, estado: string, extra: object = {}) =>
  ({ dossie: n, paciente: "Bia Souza", prestador: "Dra. Ana Lima", mes: "2026-10", estado, parado_desde: "2026-10-04", faltam: [], documentos: [doc(n * 10, estado), doc(n * 10 + 1, estado)], ...extra });
const DOSSIES = [dossie(1, "a_pedir", { faltam: ["CRM/CRP"] }), dossie(2, "pedido"), dossie(3, "a_conferir"), dossie(4, "recebido"), dossie(5, "sem_nf")];

beforeEach(() => { localStorage.clear(); window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

test("amostra real da API: mostra o dossiê com paciente, prestador e o resumo da semana", async () => {
  apiFalsa();
  montar(<Reembolso />);
  const d = await screen.findByRole("article", { name: "Dossiê 1" });
  expect(d.textContent).toContain("Helena (sintética)");
  expect(d.textContent).toContain("2 documentos");
  expect(await screen.findByText("Resumo da semana")).toBeTruthy();
});

test("mostra mês, estado, o que falta em português, parado desde e filtra por estado", async () => {
  apiFalsa({ "reembolso-dossies": env({ dossies: DOSSIES }), "reembolso-semana": env({ texto: "Dossiê 1 (10/2026): falta CRM/CRP", linhas: [] }) });
  montar(<Reembolso />);
  const d1 = await screen.findByRole("article", { name: "Dossiê 1" });
  expect(d1.textContent).toContain("10/2026");
  expect(d1.textContent).toContain("A pedir");
  expect(d1.textContent).toContain("Falta: CRM/CRP");
  expect(d1.textContent).toContain("parado desde 04/10");
  expect(d1.textContent).toContain("Dra. Ana Lima");
  expect((await screen.findByRole("region", { name: "Resumo da semana" })).textContent).toContain("falta CRM/CRP");
  expect(screen.getAllByRole("article")).toHaveLength(5);
  fireEvent.click(screen.getByRole("button", { name: "Pedido" }));
  expect(screen.getAllByRole("article").map((a) => a.getAttribute("aria-label"))).toEqual(["Dossiê 2"]);
  fireEvent.click(screen.getByRole("button", { name: "Recebido" }));
  expect(screen.getAllByRole("article").map((a) => a.getAttribute("aria-label"))).toEqual(["Dossiê 4"]);
  fireEvent.click(screen.getByRole("button", { name: "Todos" }));
  expect(screen.getAllByRole("article")).toHaveLength(5);
});

test("Marquei como pedido e Recebi chamam a rota de intenção, só nos estados certos", async () => {
  const chamadas = apiFalsa({ "reembolso-dossies": env({ dossies: DOSSIES }), "reembolso-semana": env({ texto: "x", linhas: [] }) });
  montar(<Reembolso />);
  const d1 = await screen.findByRole("article", { name: "Dossiê 1" });
  expect(within(screen.getByRole("article", { name: "Dossiê 2" })).queryByRole("button", { name: "Marquei como pedido" })).toBeNull();
  expect(within(d1).queryByRole("button", { name: "Recebi" })).toBeNull();
  expect(within(screen.getByRole("article", { name: "Dossiê 4" })).queryByRole("button")).toBeNull();
  fireEvent.click(within(d1).getByRole("button", { name: "Marquei como pedido" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /dossies\/1\/pedi$/.test(c.url))).toBe(true));
  fireEvent.click(within(screen.getByRole("article", { name: "Dossiê 3" })).getByRole("button", { name: "Recebi" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /dossies\/3\/recebi$/.test(c.url))).toBe(true));
});

test("sem dossiês: estado vazio; com erro: aviso de erro", async () => {
  apiFalsa({ "reembolso-dossies": env({ dossies: [] }), "reembolso-semana": env({ texto: "Nenhum reembolso de saúde a pedir nem a conferir.", linhas: [] }) });
  montar(<Reembolso />);
  expect(await screen.findByText("Nenhum dossiê de reembolso ainda.")).toBeTruthy();
});

test("erro 403 da rota mostra o estado de erro, sem dossiês", async () => {
  apiFalsa();
  const normal = globalThis.fetch;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) =>
    /reembolso-saude\/dossies/.test(url) ? ({ ok: false, status: 403, json: async () => ({ erro: "sem_escopo", mensagem: "Você não tem acesso a isto." }) } as Response) : normal(url, init)));
  montar(<Reembolso />);
  await waitFor(() => expect(screen.queryByText(/Carregando/i)).toBeNull());
  expect(screen.queryByRole("article")).toBeNull();
  expect(document.body.textContent).toContain("Você não tem acesso a isto.");
});
