import { vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { Hoje } from "../src/telas/Trabalho/Hoje";
import { Agenda } from "../src/telas/Trabalho/Agenda";
import { apiFalsa, amostra } from "./apiFalsa";

const montar = (ui: React.ReactElement) => render(<ToastProvider><FiltrosProvider>{ui}</FiltrosProvider></ToastProvider>);
function celular(ativo: boolean) {
  window.matchMedia = ((q: string) => ({ matches: ativo && q.includes("759"), media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia;
}
beforeEach(() => { localStorage.clear(); celular(false); });
afterEach(() => { vi.unstubAllGlobals(); });

test("Hoje mostra a frase, a agenda e o dinheiro", async () => {
  apiFalsa();
  montar(<Hoje />);
  expect(await screen.findByText(/1 coisa pede você hoje/)).toBeInTheDocument();
  expect(screen.getByText("Revisão Atlas", { exact: false })).toBeInTheDocument();
  expect(screen.getByText(/Em atraso: 1/)).toBeInTheDocument();
  expect(screen.queryByRole("group", { name: "Filtro" })).toBeNull();
});

test("Hoje celular mostra abas", async () => {
  celular(true);
  apiFalsa();
  montar(<Hoje />);
  const abas = await screen.findAllByRole("tab");
  expect(abas.map((a) => a.textContent)).toEqual(["Fazer", "Agenda", "Dinheiro", "E-mails"]);
  fireEvent.click(screen.getByRole("tab", { name: "Dinheiro" }));
  expect(screen.getByText(/Sai hoje/, { selector: "li" })).toBeInTheDocument();
});

test("Agenda proposta so sai apos confirmar", async () => {
  apiFalsa();
  montar(<Agenda />);
  expect(await screen.findByText(/a Gabi propõe/)).toBeInTheDocument();
  expect(screen.getByText(/só sai após você confirmar/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /enviar/i })).toBeNull();
});

test("Hoje não mostra link de reunião que não seja http(s)", async () => {
  const base = amostra("hoje");
  base.dados.agenda[0].link_reuniao = "javascript:x";
  apiFalsa({ hoje: base });
  montar(<Hoje />);
  await screen.findByText("Revisão Atlas", { exact: false });
  expect(screen.queryByRole("link", { name: "entrar" })).toBeNull();
});
