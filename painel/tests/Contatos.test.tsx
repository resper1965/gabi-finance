import { vi } from "vitest";
import { act, render, screen, fireEvent, within } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { IrContext } from "../src/lib/ocultar";
import { Contatos } from "../src/telas/Trabalho/Contatos";
import { amostra, apiFalsa } from "./apiFalsa";

const rota = (area: string, aba: string | null) => ({ area, aba });
const aberto = (o: object) => ({ qtd: 1, desde: null, dias: null, quando: null, detalhe: null, ...o });
const CHEIO = { ...amostra("contatos"), dados: { total: 3, itens: [
  { chave: "p:ana", pessoa_id: "ana", nome: "Ana <b>Souza</b>", urgencia: 0, dias: 5, tipos: ["email", "whatsapp"], abertos: [
    aberto({ tipo: "email", rotulo: "E-mail emergencial sem resposta (2)", qtd: 2, dias: 5, rota: rota("msgs", "prioridades") }),
    aberto({ tipo: "whatsapp", rotulo: "Pediu algo no WhatsApp", dias: 1, rota: rota("cadastros", "escuta") })] },
  { chave: "e:bia@y.com", pessoa_id: null, nome: "bia@y.com", urgencia: 1, dias: 0, tipos: ["agenda"], abertos: [
    aberto({ tipo: "agenda", rotulo: "Reunião amanhã", quando: "2026-10-09T17:00:00+00:00", detalhe: "Compromisso privado", rota: rota("agenda", null) })] },
  { chave: "w:abc", pessoa_id: null, nome: "+55 *******4321", urgencia: 2, dias: 3, tipos: ["whatsapp"], abertos: [
    aberto({ tipo: "whatsapp", rotulo: "Pediu algo no WhatsApp (2 mensagens)", qtd: 2, dias: 3, rota: rota("cadastros", "escuta") })] },
] } };

const montar = (ir = () => {}) => render(<ToastProvider><FiltrosProvider><IrContext.Provider value={ir}><Contatos /></IrContext.Provider></FiltrosProvider></ToastProvider>);
const linhas = () => screen.getAllByText(/./, { selector: "[data-contato] > strong" }).map((e) => e.textContent);
let erros: ReturnType<typeof vi.spyOn>;
beforeEach(() => { erros = vi.spyOn(console, "error").mockImplementation(() => {}); });
afterEach(async () => { await act(async () => { await new Promise((r) => setTimeout(r, 0)); }); const n = erros.mock.calls.length; erros.mockRestore(); vi.unstubAllGlobals(); expect(n).toBe(0); });

test("sem nada em aberto mostra o estado vazio", async () => {
  apiFalsa();
  montar();
  expect(await screen.findByText(/Ninguém com algo em aberto agora/)).toBeInTheDocument();
});

test("lista na ordem da API com rótulos, há quanto tempo e nome como texto puro", async () => {
  apiFalsa({ contatos: CHEIO });
  montar();
  await screen.findByText("Ana <b>Souza</b>");
  expect(linhas()).toEqual(["Ana <b>Souza</b>", "bia@y.com", "+55 *******4321"]);
  expect(screen.getByText("E-mail emergencial sem resposta (2)")).toBeInTheDocument();
  expect(screen.getByText(/há 5 dias/)).toBeInTheDocument();
  expect(screen.getByText(/há 3 dias/)).toBeInTheDocument();
  expect(screen.getByText(/há 1 dia$/)).toBeInTheDocument();
  expect(screen.getByText(/Compromisso privado/)).toBeInTheDocument();
  expect(document.querySelector("[data-contato] b")).toBeNull(); // R14: nada vira HTML
});

test("filtro WhatsApp mostra só quem pediu no WhatsApp e só essa linha", async () => {
  apiFalsa({ contatos: CHEIO });
  montar();
  await screen.findByText("Ana <b>Souza</b>");
  fireEvent.click(screen.getByRole("button", { name: "WhatsApp" }));
  expect(linhas()).toEqual(["Ana <b>Souza</b>", "+55 *******4321"]);
  expect(screen.queryByText(/E-mail emergencial/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Agenda" }));
  expect(linhas()).toEqual(["bia@y.com"]);
  fireEvent.click(screen.getByRole("button", { name: "E-mail" }));
  expect(linhas()).toEqual(["Ana <b>Souza</b>"]);
});

test("filtro sem resultado diz que não há nada ali", async () => {
  apiFalsa({ contatos: { ...CHEIO, dados: { total: 1, itens: [CHEIO.dados.itens[1]] } } });
  montar();
  await screen.findByText("bia@y.com");
  fireEvent.click(screen.getByRole("button", { name: "E-mail" }));
  expect(screen.getByText(/Nenhum contato com algo em aberto neste filtro/)).toBeInTheDocument();
});

test("o link leva à aba certa e nada é enviado (só GET)", async () => {
  const chamadas = apiFalsa({ contatos: CHEIO });
  const ir = vi.fn();
  montar(ir);
  await screen.findByText("bia@y.com");
  fireEvent.click(screen.getByRole("button", { name: "Ver Prioridades: Ana <b>Souza</b>" }));
  expect(ir).toHaveBeenLastCalledWith("msgs", "prioridades");
  fireEvent.click(screen.getByRole("button", { name: "Ver Agenda: bia@y.com" }));
  expect(ir).toHaveBeenLastCalledWith("agenda", undefined);
  expect(chamadas.every((c) => c.metodo === "GET")).toBe(true);
});

test("erro da API aparece como erro, sem derrubar a tela", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 503, json: async () => ({ erro: "indisponivel", mensagem: "banco fora do ar" }) }) as Response));
  montar();
  const alerta = await screen.findByRole("alert");
  expect(within(alerta).getByText(/banco fora do ar/)).toBeInTheDocument();
});
