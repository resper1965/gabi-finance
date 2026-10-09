import { vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { Avisos } from "../src/componentes/Avisos";
import { Shell } from "../src/componentes/Shell";
import { amostra, apiFalsa } from "./apiFalsa";

const montar = (ui: React.ReactElement) => render(<ToastProvider><FiltrosProvider>{ui}</FiltrosProvider></ToastProvider>);
beforeEach(() => { localStorage.clear(); window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

const lista = (itens: object[]) => ({ ...amostra("contagens"), dados: { itens } });
const aviso = (id: number, titulo: string, texto: string) => ({ id, tipo: "conta_atrasada", titulo, texto, criado_em: "2026-10-16T10:00:00+00:00" });

test("Avisos mostra titulo e texto de cada aviso aberto e marca como lido", async () => {
  const chamadas = apiFalsa({ avisos: lista([aviso(9, "Conta atrasada: Cristina Yabe", "venceu em 2026-10-07, R$ 370.00")]) });
  montar(<Avisos />);
  expect(await screen.findByText("Conta atrasada: Cristina Yabe")).toBeInTheDocument();
  expect(screen.getByText("venceu em 2026-10-07, R$ 370.00")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Marcar como lido: Conta atrasada: Cristina Yabe" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /\/avisos\/9\/lido$/.test(c.url))).toBe(true));
});

test("Avisos sem nada aberto diz que esta tudo em dia", async () => {
  apiFalsa({ avisos: lista([]) });
  montar(<Avisos />);
  expect(await screen.findByText("Nenhum aviso aberto.")).toBeInTheDocument();
});

test("o sino do Shell abre e fecha o painel de avisos", () => {
  render(<Shell tela={() => null} contagens={{ sino: 2, menu: { avisos: 2 } }} avisos={<p>painel-de-avisos</p>} />);
  expect(screen.queryByText("painel-de-avisos")).toBeNull();
  const sino = screen.getByRole("button", { name: "Alertas" });
  fireEvent.click(sino);
  expect(screen.getByText("painel-de-avisos")).toBeInTheDocument();
  fireEvent.click(sino);
  expect(screen.queryByText("painel-de-avisos")).toBeNull();
});
