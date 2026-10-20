import { vi } from "vitest";
import { act, render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { useAcao } from "../src/lib/useAcao";
import { ContatosPropostas } from "../src/telas/ContatosPropostas";

const env = (dados: unknown) => ({ dados_ate: null, desatualizado: false, fontes: [], dados });
interface Chamada { metodo: string; url: string; corpo: unknown }
const prop = (o: Record<string, unknown>) => ({ id: 1, tipo: "corrigir", conta: "resper@gmail.com", nome_antes: "Ana", telefone_antes: "+551191234567", nome_depois: "Ana", telefone_depois: "+5511991234567", origem: "telefone_invalido", estado: "pendente", motivo: null, criada_em: "2026-10-20T10:00:00", decidida_em: null, decidida_por: null, aplicada_em: null, ...o });
const CRIAR = prop({ id: 2, tipo: "criar", nome_antes: null, telefone_antes: null, nome_depois: "Bia", telefone_depois: "+5511988887777", origem: "whatsapp", conta: "resper@ness.com.br" });

function fake(itens: unknown[], escrita = "ligado", falha?: RegExp) {
  const chamadas: Chamada[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const metodo = init?.method ?? "GET";
    chamadas.push({ metodo, url, corpo: init?.body ? JSON.parse(String(init.body)) : undefined });
    const ok = (j: unknown) => ({ ok: true, status: 200, json: async () => j }) as Response;
    if (metodo !== "GET") {
      if (falha?.test(url)) return { ok: false, status: 500, json: async () => ({ erro: "interno", mensagem: "deu ruim" }) } as Response;
      if (/aprovar-correcoes/.test(url)) return ok(env({ aprovadas: 2 }));
      return ok(env({ id: 1, estado: "aprovada" }));
    }
    return ok(env({ itens, escrita }));
  }));
  return chamadas;
}
function Tela() { const acao = useAcao(); return <ContatosPropostas acao={acao} />; }
const montar = () => render(<ToastProvider><Tela /></ToastProvider>);
const posts = (c: Chamada[]) => c.filter((x) => x.metodo !== "GET");
let erros: ReturnType<typeof vi.spyOn>;
beforeEach(() => { erros = vi.spyOn(console, "error").mockImplementation(() => {}); });
afterEach(async () => { await act(async () => { await new Promise((r) => setTimeout(r, 0)); }); const n = erros.mock.calls.length; erros.mockRestore(); vi.unstubAllGlobals(); expect(n).toBe(0); });

test("lista pendentes com antes e depois lado a lado", async () => {
  const c = fake([prop({}), CRIAR]);
  montar();
  const li = (await screen.findByText(/\+551191234567/)).closest("li")!;
  expect(li.textContent).toContain("resper@gmail.com");
  expect(li.textContent).toContain("Ana +551191234567");
  expect(li.textContent).toContain("Ana +5511991234567");
  const novo = screen.getByText(/\+5511988887777/).closest("li")!;
  expect(novo.textContent).toContain("— (novo)");
  expect(c[0].url).toBe("/api/v1/escuta/contatos/propostas?estado=pendente");
});

test.each([["Aprovar", "aprovada"], ["Recusar", "recusada"]])("%s envia a decisão e recarrega", async (rotulo, estado) => {
  const c = fake([prop({ id: 7 })]);
  montar();
  const li = (await screen.findByText(/\+551191234567/)).closest("li")!;
  fireEvent.click(within(li).getByRole("button", { name: new RegExp(`^${rotulo}`) }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0]).toMatchObject({ metodo: "POST", url: "/api/v1/escuta/contatos/propostas/7/decisao", corpo: { estado } });
  await waitFor(() => expect(c.filter((x) => x.metodo === "GET")).toHaveLength(2));
});

test("botão em lote só com correção pendente e chama a rota em lote", async () => {
  const c = fake([prop({}), CRIAR]);
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Aprovar todas as correções de telefone" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0]).toMatchObject({ metodo: "POST", url: "/api/v1/escuta/contatos/propostas/aprovar-correcoes" });
  expect(await screen.findByText("2 correção(ões) aprovada(s).")).toBeTruthy();
});

test("sem correção pendente não há botão em lote", async () => {
  fake([CRIAR]);
  montar();
  await screen.findByText(/\+5511988887777/);
  expect(screen.queryByRole("button", { name: /Aprovar todas/ })).toBeNull();
});

test("aviso de gravação desligada aparece só quando desligado", async () => {
  fake([CRIAR], "desligado");
  montar();
  expect(await screen.findByText("A gravação está desligada: aprovar não grava ainda. Ligue em contatos.escrita quando quiser.")).toBeTruthy();
});
test("sem aviso quando a gravação está ligada", async () => {
  fake([CRIAR], "ligado");
  montar();
  await screen.findByText(/\+5511988887777/);
  expect(screen.queryByText(/A gravação está desligada/)).toBeNull();
});

test("estado vazio", async () => {
  fake([]);
  montar();
  expect(await screen.findByText(/Nenhuma proposta pendente\./)).toBeTruthy();
});

test("erro da decisão aparece e a lista continua", async () => {
  fake([CRIAR], "ligado", /decisao/);
  montar();
  fireEvent.click(await screen.findByRole("button", { name: /^Aprovar/ }));
  expect(await screen.findByText(/deu ruim/, { selector: "p" })).toBeTruthy();
  expect(screen.getByText(/\+5511988887777/)).toBeTruthy();
});
