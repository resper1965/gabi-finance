import { vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { Agentes } from "../src/telas/Gabi/Agentes";

const env = (dados: unknown) => ({ dados_ate: null, desatualizado: false, fontes: [], dados });
const ESCOPOS = ["agenda", "documentos", "financeiro", "sensivel"];
const AGENTES = [
  { id: 1, nome: "Hermes", escopos: ["agenda", "financeiro"], criado_em: "2026-11-01T10:00:00", revogado_em: null, ativo: true, ultimo_uso: "2026-11-09T08:30:00", chamadas_7d: 12 },
  { id: 2, nome: "Claude Code", escopos: ["agenda"], criado_em: "2026-11-02T10:00:00", revogado_em: null, ativo: true, ultimo_uso: null, chamadas_7d: 0 },
  { id: 3, nome: "Antigo", escopos: ["agenda"], criado_em: "2026-10-01T10:00:00", revogado_em: "2026-10-20T10:00:00", ativo: false, ultimo_uso: "2026-10-19T10:00:00", chamadas_7d: 0 },
];
const CONEXAO = { url: "https://gabi.exemplo/mcp", escopos_padrao: ["agenda", "documentos", "financeiro"], escopos_validos: ESCOPOS };
interface Cham { metodo: string; url: string; corpo: any }

function fetchFalso(posts: Record<string, unknown> = {}) {
  const chamadas: Cham[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const metodo = init?.method ?? "GET";
    chamadas.push({ metodo, url, corpo: init?.body ? JSON.parse(String(init.body)) : undefined });
    const ok = (j: unknown) => ({ ok: true, status: 200, json: async () => env(j) }) as Response;
    if (metodo !== "GET") return ok(posts[`${metodo} ${url.replace(/\/\d+/, "/N")}`] ?? {});
    if (url.endsWith("/conexao")) return ok(CONEXAO);
    if (url.endsWith("/chamadas")) return ok({ itens: [{ quando: "2026-11-09T08:30:00", ferramenta: "agenda_financeira", status: "ok" }] });
    return ok({ itens: AGENTES });
  }));
  return chamadas;
}
const montar = () => render(<ToastProvider><Agentes /></ToastProvider>);
const achar = (c: Cham[], metodo: string, fim: string) => c.find((x) => x.metodo === metodo && x.url.endsWith(fim));
beforeEach(() => { window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

test("lista chaves com último uso, chamadas em 7 dias e revogadas esmaecidas", async () => {
  fetchFalso(); montar();
  expect(await screen.findByText("Hermes")).toBeTruthy();
  expect(screen.getByText(/12 chamadas em 7 dias/)).toBeTruthy();
  expect(screen.getByText(/nunca usada/)).toBeTruthy();
  const revogada = screen.getByText(/Antigo \(revogada\)/).closest("li")!;
  expect(revogada.style.opacity).toBe("0.55");
  expect(within(revogada).queryByText("Revogar")).toBeNull();
});

test("nova chave vem com os escopos do Hermes marcados e sem sensivel", async () => {
  fetchFalso(); montar();
  await screen.findByText("Hermes");
  const form = screen.getByText("Emitir chave").closest("form")!;
  const marcado = (n: string) => (within(form).getByLabelText(n) as HTMLInputElement).checked;
  expect(marcado("agenda") && marcado("documentos") && marcado("financeiro")).toBe(true);
  expect(marcado("sensivel")).toBe(false);
});

test("nome vazio bloqueia o envio", async () => {
  const c = fetchFalso(); montar();
  await screen.findByText("Hermes");
  const botao = screen.getByText("Emitir chave") as HTMLButtonElement;
  expect(botao.disabled).toBe(true);
  fireEvent.submit(botao.closest("form")!);
  expect(c.some((x) => x.metodo === "POST")).toBe(false);
});

test("ao emitir mostra a chave uma vez com botão Copiar e some ao fechar", async () => {
  const escrever = vi.fn(async () => {});
  Object.defineProperty(navigator, "clipboard", { value: { writeText: escrever }, configurable: true });
  const c = fetchFalso({ "POST /api/v1/agentes": { id: 9, nome: "Novo", escopos: ["agenda"], chave: "gb_segredo123" } });
  montar();
  await screen.findByText("Hermes");
  fireEvent.change(screen.getByLabelText("Nome do agente"), { target: { value: "Novo" } });
  fireEvent.click(screen.getByText("Emitir chave"));
  expect(await screen.findByText("gb_segredo123")).toBeTruthy();
  expect(achar(c, "POST", "/api/v1/agentes")!.corpo).toEqual({ nome: "Novo", escopos: ["agenda", "documentos", "financeiro"] });
  fireEvent.click(screen.getByText("Copiar"));
  await waitFor(() => expect(escrever).toHaveBeenCalledWith("gb_segredo123"));
  fireEvent.click(screen.getByText("Fechar"));
  expect(screen.queryByText(/gb_/)).toBeNull();
});

test("revogar pede confirmação", async () => {
  const c = fetchFalso(); montar();
  await screen.findByText("Claude Code");
  fireEvent.click(screen.getByLabelText("Revogar Claude Code"));
  expect(achar(c, "POST", "/2/revogar")).toBeUndefined();
  fireEvent.click(screen.getByLabelText("Confirmar revogar Claude Code"));
  await waitFor(() => expect(achar(c, "POST", "/2/revogar")).toBeTruthy());
});

test("rotacionar e revogar a chave do Hermes pedem confirmação reforçada", async () => {
  fetchFalso({ "POST /api/v1/agentes/N/rotacionar": { id: 10, nome: "Hermes", escopos: ["agenda"], chave: "gb_nova" } });
  montar();
  await screen.findByText("Hermes");
  fireEvent.click(screen.getByLabelText("Revogar Hermes"));
  expect(screen.getByRole("alert").textContent).toMatch(/Telegram e no WhatsApp/);
  fireEvent.click(screen.getByLabelText("Rotacionar Hermes"));
  expect(screen.getByRole("alert").textContent).toMatch(/Telegram e no WhatsApp/);
  fireEvent.click(screen.getByLabelText("Confirmar rotacionar Hermes"));
  expect(await screen.findByText("gb_nova")).toBeTruthy();
});

test("editar escopos chama PATCH sem mostrar chave", async () => {
  const c = fetchFalso(); montar();
  await screen.findByText("Claude Code");
  fireEvent.click(screen.getByLabelText("Editar escopos de Claude Code"));
  const linha = screen.getByLabelText("Salvar escopos de Claude Code").closest("li")!;
  fireEvent.click(within(linha).getByLabelText("financeiro"));
  fireEvent.click(screen.getByLabelText("Salvar escopos de Claude Code"));
  await waitFor(() => expect(achar(c, "PATCH", "/2/escopos")).toBeTruthy());
  expect(achar(c, "PATCH", "/2/escopos")!.corpo).toEqual({ escopos: ["agenda", "financeiro"] });
  expect(screen.queryByText(/gb_/)).toBeNull();
});

test("ver chamadas lista ferramenta, status e quando", async () => {
  fetchFalso(); montar();
  await screen.findByText("Hermes");
  fireEvent.click(screen.getByLabelText("Ver chamadas de Hermes"));
  expect(await screen.findByText(/agenda_financeira · ok/)).toBeTruthy();
  expect(screen.getByText(/^09\/11 08:30 · agenda_financeira/)).toBeTruthy();
});
