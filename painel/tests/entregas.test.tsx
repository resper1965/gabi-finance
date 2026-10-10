import { vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { Entregas } from "../src/telas/Trabalho/Entregas";
import { apiFalsa } from "./apiFalsa";

beforeEach(() => { localStorage.clear(); window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

test("lista as entregas da Linear sem nenhum controle de escrita", async () => {
  apiFalsa();
  render(<ToastProvider><FiltrosProvider><Entregas /></FiltrosProvider></ToastProvider>);
  expect(await screen.findByText("ION-12")).toBeTruthy();
  expect(screen.getByText("Entregar laudo do cliente")).toBeTruthy();
  expect(screen.queryAllByRole("button")).toHaveLength(0);
});
