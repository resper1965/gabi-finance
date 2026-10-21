import { vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { Hoje } from "../src/telas/Trabalho/Hoje";
import { Frentes } from "../src/telas/Trabalho/Frentes";
import { Agenda } from "../src/telas/Trabalho/Agenda";
import { Mensagens } from "../src/telas/Trabalho/Mensagens";
import { Tarefas } from "../src/telas/Trabalho/Tarefas";
import { apiFalsa } from "./apiFalsa";

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

test("Frentes sugestao so entra ao clicar Entra", async () => {
  const chamadas = apiFalsa();
  montar(<Frentes />);
  fireEvent.click(await screen.findByRole("button", { name: /Acme/ }));
  const entra = await screen.findByRole("button", { name: "Entra" });
  expect(chamadas.some((c) => c.metodo === "POST")).toBe(false);
  fireEvent.click(entra);
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /\/frentes\/1\/itens\/\d+\/confirmar$/.test(c.url))).toBe(true));
});

test("Agenda proposta so sai apos confirmar", async () => {
  apiFalsa();
  montar(<Agenda />);
  expect(await screen.findByText(/a Gabi propõe/)).toBeInTheDocument();
  expect(screen.getByText(/só sai após você confirmar/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /enviar/i })).toBeNull();
});

test("Mensagens mostra só cabeçalho e nunca oferece apagar", async () => {
  apiFalsa();
  montar(<Mensagens />);
  expect(await screen.findByText("Contrato Atlas para assinar")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /apagar/i })).toBeNull();
});

test("Tarefas marcar chama concluir na origem", async () => {
  const chamadas = apiFalsa();
  montar(<Tarefas />);
  fireEvent.click(await screen.findByRole("checkbox", { name: /Concluir Enviar proposta/ }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /\/tarefas\/1\/concluir$/.test(c.url))).toBe(true));
  expect(screen.getByRole("checkbox", { name: /Concluir Renovar domínio/ })).toBeDisabled();
});

test("Cadastros caixas: liberar chama PATCH e cadastrar nasce a decidir", async () => {
  const chamadas = apiFalsa();
  const { CadastrosCaixas } = await import("../src/telas/CadastrosCaixas");
  montar(<CadastrosCaixas />);
  fireEvent.change(await screen.findByLabelText("Estado de ricardo@ionic.exemplo"), { target: { value: "sim" } });
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "PATCH" && /\/caixas-email\/2$/.test(c.url) && (c.corpo as { estado: string }).estado === "sim")).toBe(true));
  fireEvent.change(screen.getByLabelText("Endereço da nova caixa"), { target: { value: "x@y.com" } });
  fireEvent.click(screen.getByRole("button", { name: "+ Cadastrar" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /\/caixas-email$/.test(c.url))).toBe(true));
});
