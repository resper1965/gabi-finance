import { vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { Familia } from "../src/telas/Familia";
import { apiFalsa } from "./apiFalsa";

const montar = (ui: React.ReactElement) => render(<ToastProvider><FiltrosProvider>{ui}</FiltrosProvider></ToastProvider>);
beforeEach(() => { localStorage.clear(); window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

test("mostra os marcadores da pessoa escolhida e abre a série ao clicar", async () => {
  apiFalsa();
  montar(<Familia />);
  const botao = await screen.findByRole("button", { name: /Colesterol total/ });
  expect(botao.textContent).toContain("fora da faixa");
  fireEvent.click(botao);
  expect(await screen.findByRole("img", { name: "Série do marcador" })).toBeTruthy();
});

test("gera o resumo para a consulta", async () => {
  apiFalsa();
  montar(<Familia />);
  fireEvent.click(await screen.findByRole("button", { name: "Gerar resumo para a consulta" }));
  expect((await screen.findByLabelText("Resumo para a consulta")).textContent).toContain("Colesterol total");
});

test("laudo so e confirmado com a pessoa escolhida (a sugestao vem pre-selecionada)", async () => {
  const chamadas = apiFalsa();
  montar(<Familia />);
  const confirmar = await screen.findByRole("button", { name: "Confirmar e registrar" });
  fireEvent.click(confirmar);
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /laudos\/55\/confirmar$/.test(c.url))).toBe(true));
  expect(chamadas.find((c) => /confirmar$/.test(c.url))!.corpo).toEqual({ pessoa_id: "p-lia" });
});

test("sem ser boss (403 nos laudos) a tela nao mostra a area de laudos", async () => {
  apiFalsa();
  const normal = globalThis.fetch;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) =>
    /familia\/laudos/.test(url) ? ({ ok: false, status: 403, json: async () => ({ erro: "sem_escopo", mensagem: "Você não tem acesso a isto." }) } as Response) : normal(url, init)));
  montar(<Familia />);
  await screen.findByRole("button", { name: /Colesterol total/ });
  expect(screen.queryByText(/Laudos para confirmar/)).toBeNull();
});
