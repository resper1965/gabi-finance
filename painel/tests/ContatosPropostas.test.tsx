import { vi } from "vitest";
import { act, render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { useAcao } from "../src/lib/useAcao";
import { ContatosPropostas } from "../src/telas/ContatosPropostas";

const env = (dados: unknown) => ({ dados_ate: null, desatualizado: false, fontes: [], dados });
interface Chamada { metodo: string; url: string; corpo: unknown }
const prop = (o: Record<string, unknown>) => ({ id: 1, tipo: "corrigir", conta: "resper@gmail.com", nome_antes: "Ana", telefone_antes: "+551191234567", nome_depois: "Ana", telefone_depois: "+5511991234567", origem: "telefone_invalido", estado: "pendente", motivo: null, criada_em: "2026-10-20T10:00:00", decidida_em: null, decidida_por: null, aplicada_em: null, ...o });
const CRIAR = prop({ id: 2, tipo: "criar", nome_antes: null, telefone_antes: null, nome_depois: "Bia", telefone_depois: "+5511988887777", origem: "whatsapp", conta: "resper@ness.com.br" });
const APROVADA = prop({ id: 9, tipo: "criar", nome_antes: null, telefone_antes: null, nome_depois: "Caio", telefone_depois: "+5511977776666", origem: "whatsapp", conta: "resper@ness.com.br", estado: "aprovada" });

interface Opcoes { escrita?: string; falha?: RegExp; status?: number; mensagem?: string; aprovadas?: unknown[]; segurar?: Promise<void> }
function fake(itens: unknown[], o: Opcoes = {}) {
  const { escrita = "ligado", falha, status = 500, mensagem = "deu ruim", aprovadas = [], segurar } = o;
  const chamadas: Chamada[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const metodo = init?.method ?? "GET";
    chamadas.push({ metodo, url, corpo: init?.body ? JSON.parse(String(init.body)) : undefined });
    const ok = (j: unknown) => ({ ok: true, status: 200, json: async () => j }) as Response;
    if (metodo !== "GET") {
      if (segurar) await segurar;
      if (falha?.test(url)) return { ok: false, status, json: async () => ({ erro: status === 409 ? "conflito" : "interno", mensagem }) } as Response;
      if (/aprovar-correcoes/.test(url)) return ok(env({ aprovadas: 2 }));
      return ok(env({ id: 1, estado: "aprovada" }));
    }
    return ok(env({ itens: /estado=aprovada/.test(url) ? aprovadas : itens, escrita }));
  }));
  return chamadas;
}
function Tela() { const acao = useAcao(); return <ContatosPropostas acao={acao} />; }
const montar = () => render(<ToastProvider><Tela /></ToastProvider>);
const posts = (c: Chamada[]) => c.filter((x) => x.metodo !== "GET");
const gets = (c: Chamada[], estado: string) => c.filter((x) => x.metodo === "GET" && x.url.endsWith(`estado=${estado}`));
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
  expect(gets(c, "pendente")[0].url).toBe("/api/v1/escuta/contatos/propostas?estado=pendente");
});

test("nota diz que nada muda na Microsoft (conta ness) e não fala em Google", async () => {
  fake([CRIAR]);
  montar();
  expect(await screen.findByText(/Nada muda na Microsoft \(conta ness\) até você aprovar/)).toBeTruthy();
  expect(screen.queryByText(/Google/)).toBeNull();
});

test("rótulos acessíveis dos botões têm tipo e id, sem nome nem telefone", async () => {
  fake([prop({ id: 7 }), CRIAR]);
  montar();
  await screen.findByText(/\+551191234567/);
  expect(screen.getByRole("button", { name: "Aprovar proposta 7 (corrigir)" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Recusar proposta 2 (criar)" })).toBeTruthy();
  for (const b of screen.getAllByRole("button")) {
    const rotulo = b.getAttribute("aria-label") ?? "";
    expect(rotulo).not.toMatch(/Ana|Bia|\+55|\d{8,}/);
  }
});

test.each([["Aprovar", "aprovada"], ["Recusar", "recusada"]])("%s envia a decisão e recarrega", async (rotulo, estado) => {
  const c = fake([prop({ id: 7 })]);
  montar();
  const li = (await screen.findByText(/\+551191234567/)).closest("li")!;
  fireEvent.click(within(li).getByRole("button", { name: new RegExp(`^${rotulo}`) }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0]).toMatchObject({ metodo: "POST", url: "/api/v1/escuta/contatos/propostas/7/decisao", corpo: { estado } });
  await waitFor(() => expect(gets(c, "pendente")).toHaveLength(2));
  await waitFor(() => expect(gets(c, "aprovada")).toHaveLength(2));
});

test("botão em lote envia só os ids das correções na tela e avisa que não inclui contatos novos", async () => {
  const c = fake([prop({ id: 1 }), CRIAR, prop({ id: 3, telefone_antes: "+551193334444" })]);
  montar();
  expect(await screen.findByText(/Não inclui contatos novos\./)).toBeTruthy();
  fireEvent.click(await screen.findByRole("button", { name: "Aprovar todas as correções de telefone" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0]).toMatchObject({ metodo: "POST", url: "/api/v1/escuta/contatos/propostas/aprovar-correcoes", corpo: { ids: [1, 3] } });
  expect(await screen.findByText("2 correção(ões) aprovada(s).")).toBeTruthy();
});

test("o resumo do lote some quando outra ação roda", async () => {
  fake([prop({ id: 1 }), CRIAR]);
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Aprovar todas as correções de telefone" }));
  expect(await screen.findByText("2 correção(ões) aprovada(s).")).toBeTruthy();
  const recusar = screen.getByRole("button", { name: "Recusar proposta 2 (criar)" }) as HTMLButtonElement;
  await waitFor(() => expect(recusar.disabled).toBe(false)); // espera a releitura do lote terminar
  fireEvent.click(recusar);
  await waitFor(() => expect(screen.queryByText("2 correção(ões) aprovada(s).")).toBeNull());
});

test("sem correção pendente não há botão em lote", async () => {
  fake([CRIAR]);
  montar();
  await screen.findByText(/\+5511988887777/);
  expect(screen.queryByRole("button", { name: /Aprovar todas/ })).toBeNull();
});

test("aviso de gravação desligada aparece só quando desligado", async () => {
  fake([CRIAR], { escrita: "desligado" });
  montar();
  expect(await screen.findByText("A gravação está desligada: aprovar não grava ainda. Ligue em contatos.escrita quando quiser.")).toBeTruthy();
});
test("sem aviso quando a gravação está ligada", async () => {
  fake([CRIAR]);
  montar();
  await screen.findByText(/\+5511988887777/);
  expect(screen.queryByText(/A gravação está desligada/)).toBeNull();
});

test("estado vazio", async () => {
  fake([]);
  montar();
  expect(await screen.findByText(/Nenhuma proposta pendente\./)).toBeTruthy();
});

test("erro da decisão aparece, a lista continua e é relida", async () => {
  const c = fake([CRIAR], { falha: /decisao/ });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: /^Aprovar/ }));
  expect(await screen.findByText(/deu ruim/, { selector: "p" })).toBeTruthy();
  expect(screen.getByText(/\+5511988887777/)).toBeTruthy();
  await waitFor(() => expect(gets(c, "pendente")).toHaveLength(2));
});

test("409 (já decidida) mostra o erro e relê a lista", async () => {
  const c = fake([CRIAR], { falha: /decisao/, status: 409, mensagem: "A proposta já foi decidida." });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: /^Recusar/ }));
  expect(await screen.findByText(/A proposta já foi decidida\./, { selector: "p" })).toBeTruthy();
  await waitFor(() => expect(gets(c, "pendente")).toHaveLength(2));
  await waitFor(() => expect(gets(c, "aprovada")).toHaveLength(2));
});

test("botões ficam desabilitados enquanto o pedido está em andamento", async () => {
  let soltar!: () => void;
  const segurar = new Promise<void>((r) => { soltar = r; });
  const c = fake([prop({ id: 1 }), CRIAR], { segurar, aprovadas: [APROVADA] });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Aprovar proposta 1 (corrigir)" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  for (const b of screen.getAllByRole("button")) expect((b as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Recusar proposta 2 (criar)" }));
  expect(posts(c)).toHaveLength(1);
  await act(async () => { soltar(); });
  await waitFor(() => expect((screen.getByRole("button", { name: "Recusar proposta 2 (criar)" }) as HTMLButtonElement).disabled).toBe(false));
});

test("aprovadas aguardando gravação aparecem com Recusar, que desfaz a aprovação", async () => {
  const c = fake([CRIAR], { aprovadas: [APROVADA] });
  montar();
  const titulo = await screen.findByText(/Aprovadas aguardando gravação · 1/);
  expect(gets(c, "aprovada")[0].url).toBe("/api/v1/escuta/contatos/propostas?estado=aprovada");
  const li = screen.getByText(/\+5511977776666/).closest("li")!;
  expect(titulo).toBeTruthy();
  expect(within(li).queryByRole("button", { name: /^Aprovar/ })).toBeNull();
  fireEvent.click(within(li).getByRole("button", { name: "Recusar proposta 9 (criar)" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0]).toMatchObject({ metodo: "POST", url: "/api/v1/escuta/contatos/propostas/9/decisao", corpo: { estado: "recusada" } });
  await waitFor(() => expect(gets(c, "aprovada")).toHaveLength(2));
  await waitFor(() => expect(gets(c, "pendente")).toHaveLength(2));
});

test("sem aprovadas, a segunda lista não aparece", async () => {
  fake([CRIAR]);
  montar();
  await screen.findByText(/\+5511988887777/);
  expect(screen.queryByText(/Aprovadas aguardando gravação/)).toBeNull();
});
