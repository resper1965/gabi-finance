import { vi } from "vitest";
import { act, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { Envios } from "../src/telas/Envios";
import { App } from "../src/App";
import { apiFalsa } from "./apiFalsa";

const env = (dados: unknown) => ({ dados_ate: null, desatualizado: false, fontes: [], dados });
interface Chamada { metodo: string; url: string; corpo: unknown }
const base = { estado: "pendente", motivo: null, criada_em: "2026-10-22T12:00:00Z", vence_em: "2026-10-22T18:00:00Z", decidida_em: null, enviada_em: null };
const EVENTO = { ...base, id: 1, tipo: "evento", conta: "resper@ness.com.br", hash: "h-evento", conteudo: { conta: "resper@ness.com.br", provedor: "graph", titulo: "Reunião de alinhamento", inicio_utc: "2026-10-22T18:00:00Z", fim_utc: "2026-10-22T19:00:00Z", fuso: "America/Sao_Paulo", convidados: ["ana@x.com", "bia@y.com"], descricao: "Pauta", online: true } };
const TEAMS = { ...base, id: 2, tipo: "teams_chat", conta: "resper@ness.com.br", hash: "h-teams", conteudo: { conta: "resper@ness.com.br", chat_id: "c1", destino_nome: "Carlos Souza", texto: "Oi Carlos,\nsegue o texto completo <b>e & mais</b>." } };
const CANAL = { ...base, id: 3, tipo: "teams_canal", conta: "resper@ness.com.br", hash: "h-canal", conteudo: { conta: "resper@ness.com.br", equipe_id: "e", canal_id: "k", equipe_nome: "Time Forense", canal_nome: "Geral", texto: "Aviso" } };

function fake(pendentes: unknown[], o: { escrita?: string; decididas?: unknown[]; resposta?: unknown; convites?: unknown[]; erroPropor?: { status: number; erro: string; mensagem: string } } = {}) {
  const { escrita = "ligado", decididas = [], resposta = { id: 1, estado: "enviada" }, convites = [], erroPropor } = o;
  const chamadas: Chamada[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const metodo = init?.method ?? "GET";
    chamadas.push({ metodo, url, corpo: init?.body ? JSON.parse(String(init.body)) : undefined });
    const ok = (j: unknown) => ({ ok: true, status: 200, json: async () => j }) as Response;
    if (metodo !== "GET" && erroPropor && /convites/.test(url)) return { ok: false, status: erroPropor.status, json: async () => ({ erro: erroPropor.erro, mensagem: erroPropor.mensagem }) } as Response;
    if (metodo !== "GET") return ok(env(resposta));
    if (/\/envios\/convites/.test(url)) return ok(env({ itens: convites }));
    return ok(env({ itens: /estado=decididas/.test(url) ? decididas : pendentes, escrita }));
  }));
  return chamadas;
}
const montar = () => render(<ToastProvider><Envios /></ToastProvider>);
const posts = (c: Chamada[]) => c.filter((x) => x.metodo !== "GET");
afterEach(async () => { await act(async () => { await new Promise((r) => setTimeout(r, 0)); }); vi.unstubAllGlobals(); });

test("cartão de evento mostra conta, título, horário de Brasília, e-mails e validade", async () => {
  fake([EVENTO]);
  montar();
  const li = (await screen.findByText(/Reunião de alinhamento/)).closest("li")!;
  expect(li.textContent).toContain("resper@ness.com.br");
  expect(li.textContent).toContain("qui 22/10 15:00–16:00");
  expect(li.textContent).toContain("ana@x.com");
  expect(li.textContent).toContain("bia@y.com");
  expect(li.textContent).toMatch(/vence .*22\/10 15:00/);
});

test("cartão de Teams mostra o destino e o texto completo", async () => {
  fake([TEAMS, CANAL]);
  montar();
  const li = (await screen.findByText(/Carlos Souza/)).closest("li")!;
  expect(li.textContent).toContain("Oi Carlos,");
  expect(li.textContent).toContain("segue o texto completo <b>e & mais</b>.");
  const canal = screen.getByText(/Time Forense/).closest("li")!;
  expect(canal.textContent).toContain("Geral");
  expect(canal.textContent).toContain("Aviso");
});

test("cartão de chat de grupo avisa (grupo); conversa a dois e proposta antiga sem tipo não", async () => {
  const GRUPO = { ...TEAMS, id: 4, hash: "h-grupo", conteudo: { ...TEAMS.conteudo, chat_id: "g1", destino_nome: "Bruno Lima", tipo: "grupo" } };
  const DOIS = { ...TEAMS, id: 5, hash: "h-dois", conteudo: { ...TEAMS.conteudo, chat_id: "c5", destino_nome: "Dora Reis", tipo: "um_a_um" } };
  fake([TEAMS, GRUPO, DOIS]);
  montar();
  expect((await screen.findByText(/Bruno Lima/)).closest("li")!.textContent).toContain("Bruno Lima (grupo)");
  expect(screen.getByText(/Dora Reis/).closest("li")!.textContent).not.toContain("(grupo)");
  expect(screen.getByText(/Carlos Souza/).closest("li")!.textContent).not.toContain("(grupo)");
});

test("Enviar manda o hash da listagem e recarrega", async () => {
  const c = fake([EVENTO]);
  montar();
  fireEvent.click(await screen.findByRole("button", { name: /Enviar/ }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0]).toMatchObject({ metodo: "POST", url: "/api/v1/envios/1/enviar", corpo: { hash: "h-evento" } });
  await waitFor(() => expect(c.filter((x) => x.metodo === "GET" && x.url.endsWith("estado=pendente"))).toHaveLength(2));
});

test("Enviar que termina em falhou mostra o resultado", async () => {
  fake([EVENTO], { resposta: { id: 1, estado: "falhou", motivo: "provedor_recusou" } });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: /Enviar/ }));
  expect(await screen.findAllByText(/falhou/i)).not.toHaveLength(0);
  expect((await screen.findAllByText(/provedor_recusou/)).length).toBeGreaterThan(0);
});

test("Recusar chama /recusar", async () => {
  const c = fake([TEAMS]);
  montar();
  fireEvent.click(await screen.findByRole("button", { name: /Recusar/ }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0].url).toBe("/api/v1/envios/2/recusar");
});

test("com escrita desligada mostra a faixa Envios desligados", async () => {
  fake([EVENTO], { escrita: "desligado" });
  montar();
  expect(await screen.findByText(/Envios desligados/)).toBeInTheDocument();
});

test("decididas mostram estado e motivo", async () => {
  fake([], { decididas: [{ ...EVENTO, id: 7, estado: "vencida", motivo: "vencida" }, { ...TEAMS, id: 8, estado: "falhou", motivo: "conta_nao_permitida" }] });
  montar();
  const li = (await screen.findByText(/Carlos Souza/)).closest("li")!;
  expect(li.textContent).toContain("falhou");
  expect(li.textContent).toContain("conta_nao_permitida");
  expect(screen.getByText(/Reunião de alinhamento/).closest("li")!.textContent).toContain("vencida");
});

test("#envios na URL abre a área", async () => {
  apiFalsa();
  const antes = vi.fn(async (url: string) => ({ ok: true, status: 200, json: async () => env({ itens: [], escrita: "ligado" }) }) as Response);
  const fetchBase = globalThis.fetch;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => /\/envios/.test(url) ? antes(url) : fetchBase(url, init)));
  window.location.hash = "#envios";
  render(<App />);
  expect(await screen.findByRole("heading", { level: 1, name: "Envios" })).toBeInTheDocument();
  window.location.hash = "";
});

const CONVITE = { evento_id: 10, conta: "resper@ness.com.br", titulo: "Planejamento Q4", inicio_utc: "2026-10-22T18:00:00Z", fim_utc: "2026-10-22T19:00:00Z", organizador_nome: "Marta Dias", conflita_com: ["Reunião de alinhamento"], proposta_id: null };
const LIVRE = { ...CONVITE, evento_id: 11, titulo: "Café com o time", organizador_nome: "Paulo Lins", conflita_com: [] };
const RESPOSTA = { ...base, id: 20, tipo: "convite_resposta", conta: "resper@ness.com.br", hash: "h-conv", conteudo: { conta: "resper@ness.com.br", provedor: "graph", evento_id: 10, externo_id: "x", serie_id: null, titulo: "Planejamento Q4", inicio_utc: "2026-10-22T18:00:00Z", fim_utc: "2026-10-22T19:00:00Z", organizador_nome: "Marta Dias", resposta: "talvez", conflita_com: ["Reunião de alinhamento"] } };

test("convites recebidos: com conflito e sem conflito", async () => {
  fake([], { convites: [CONVITE, LIVRE] });
  montar();
  expect(await screen.findByText("Convites recebidos · 2")).toBeInTheDocument();
  const a = screen.getByText(/Planejamento Q4/).closest("li")!;
  expect(a.textContent).toContain("qui 22/10 15:00–16:00");
  expect(a.textContent).toContain("de Marta Dias");
  expect(a.textContent).toContain("Conflita com Reunião de alinhamento");
  expect(screen.getByText(/Café com o time/).closest("li")!.textContent).toContain("Sem conflito");
  expect(screen.getByRole("button", { name: "Aceitar convite Planejamento Q4" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Talvez convite Planejamento Q4" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Recusar convite Planejamento Q4" })).toBeInTheDocument();
});

test("Aceitar cria a proposta e recarrega as duas listas", async () => {
  const c = fake([], { convites: [CONVITE] });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Aceitar convite Planejamento Q4" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0]).toMatchObject({ url: "/api/v1/envios/convites/10/propor", corpo: { conta: "resper@ness.com.br", resposta: "aceitar" } });
  await waitFor(() => expect(c.filter((x) => x.metodo === "GET" && x.url.endsWith("estado=pendente"))).toHaveLength(2));
  await waitFor(() => expect(c.filter((x) => x.metodo === "GET" && /envios\/convites/.test(x.url))).toHaveLength(2));
});

test("convite com proposta mostra o aviso e fica sem botões", async () => {
  fake([], { convites: [{ ...CONVITE, proposta_id: 20 }] });
  montar();
  expect(await screen.findByText(/Proposta enviada para o OK/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /convite Planejamento Q4/ })).toBeNull();
});

test("erro 409 proposta_duplicada mostra o erro e relê as listas", async () => {
  const c = fake([], { convites: [CONVITE], erroPropor: { status: 409, erro: "proposta_duplicada", mensagem: "já existe proposta para este convite" } });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Recusar convite Planejamento Q4" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("já existe proposta para este convite");
  await waitFor(() => expect(c.filter((x) => x.metodo === "GET" && /envios\/convites/.test(x.url))).toHaveLength(2));
  expect(c.filter((x) => x.metodo === "GET" && x.url.endsWith("estado=pendente"))).toHaveLength(2);
});

test("cartão convite_resposta mostra título, período, resposta e conflito", async () => {
  fake([RESPOSTA]);
  montar();
  const li = (await screen.findByText("Responder convite · resper@ness.com.br")).closest("li")!;
  expect(li.textContent).toContain("Planejamento Q4");
  expect(li.textContent).toContain("qui 22/10 15:00–16:00");
  expect(li.textContent).toContain("Talvez");
  expect(li.textContent).toContain("Conflita com Reunião de alinhamento");
  expect(screen.getByRole("button", { name: "Enviar proposta 20" })).toBeInTheDocument();
});

test("sem convites o bloco some", async () => {
  fake([EVENTO]);
  montar();
  await screen.findByText(/Reunião de alinhamento/);
  expect(screen.queryByText(/Convites recebidos/)).toBeNull();
});
