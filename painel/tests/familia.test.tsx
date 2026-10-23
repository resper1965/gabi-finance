import { vi } from "vitest";
import { act, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { CadastrosFamilia } from "../src/telas/CadastrosFamilia";

const env = (dados: unknown) => ({ dados_ate: null, desatualizado: false, fontes: [], dados });
interface Chamada { metodo: string; url: string; corpo: unknown }
const iso = (meses: number) => { const d = new Date(); d.setMonth(d.getMonth() + meses); return d.toISOString().slice(0, 10); };
const BREVE = iso(3), LONGE = iso(24), PASSADO = iso(-2);
const dd = (s: string) => `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}`;

const FICHA = (o: Record<string, unknown> = {}) => ({
  id: "p1", nome: "Ana", nome_completo: "Ana Souza", apelido: "Aninha", parentesco: "filha", nascimento: "2015-03-04",
  telefones: ["+5511999990000"], emails: ["ana@x.com"], enderecos: ["Rua A, 1", { endereco: "Rua B, 2" }],
  documentos: [
    { id: 1, tipo: "passaporte", pais: "BR", numero: "AB123456", emissor: "PF", emissao: "2020-01-01", validade: BREVE, paperless_id: 77, origem: "carga", atualizado_em: "2026-10-01" },
    { id: 2, tipo: "cpf", pais: "BR", numero: "11144477735", emissor: null, emissao: null, validade: LONGE, paperless_id: null, origem: "legado", atualizado_em: "2026-10-01" },
  ],
  divergencias: [], paperless_url: "https://paperless.exemplo", ...o,
});
const PROPOSTA = { id: 5, pessoa_id: "p1", conferir: 1, origem: "carga", estado: "pendente",
  atual: { id: 1, tipo: "passaporte", pais: "BR", numero: "AB123456", validade: "2030-01-01" },
  proposto: { tipo: "passaporte", pais: "BR", numero: "AB123456", validade: "2031-02-03" } };
const HIST = { id: 9, pessoa_id: "p1", campo: "telefones", antes: [], depois: ["+5511999990000"], quem: "hermes", quando: "2026-10-20T10:00:00", desfeito_em: null };

function fake(ficha = FICHA()) {
  const chamadas: Chamada[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const metodo = init?.method ?? "GET";
    chamadas.push({ metodo, url, corpo: init?.body ? JSON.parse(String(init.body)) : undefined });
    const ok = (j: unknown) => ({ ok: true, status: 200, json: async () => env(j) }) as Response;
    if (metodo !== "GET") return ok({});
    if (/\/fichas\/p1/.test(url)) return ok(ficha);
    if (/\/fichas/.test(url)) return ok({ itens: [{ id: "p1", nome: "Ana", apelido: "Aninha", parentesco: "filha", nascimento: "2015-03-04", documentos_qtd: 2 }] });
    if (/\/propostas/.test(url)) return ok({ itens: [PROPOSTA] });
    if (/\/historico/.test(url)) return ok({ itens: [HIST] });
    return ok({ itens: [] });
  }));
  return chamadas;
}
const montar = () => render(<ToastProvider><CadastrosFamilia /></ToastProvider>);
const posts = (c: Chamada[]) => c.filter((x) => x.metodo !== "GET");
let erros: ReturnType<typeof vi.spyOn>;
beforeEach(() => { erros = vi.spyOn(console, "error").mockImplementation(() => {}); });
afterEach(async () => { await act(async () => { await new Promise((r) => setTimeout(r, 0)); }); const n = erros.mock.calls.length; erros.mockRestore(); vi.unstubAllGlobals(); expect(n).toBe(0); });

test("ficha mostra contato e documentos com número e validade; vence em 6 meses ganha destaque", async () => {
  fake(); montar();
  expect(await screen.findByText("AB123456")).toBeTruthy();
  expect(screen.getAllByText("+5511999990000").length).toBeGreaterThan(0);
  expect(screen.getByText("ana@x.com")).toBeTruthy();
  expect(screen.getByText("Rua B, 2")).toBeTruthy();
  expect(screen.getByText("11144477735")).toBeTruthy();
  expect(screen.getByText(dd(BREVE))).toBeTruthy();
  expect(screen.getByText(dd(LONGE))).toBeTruthy();
  expect(screen.getAllByText("Vence em breve")).toHaveLength(1);
  expect(screen.getByText(dd(BREVE)).closest("li")!.textContent).toContain("Vence em breve");
});

test("documento com validade passada mostra Vencido, não Vence em breve", async () => {
  fake(FICHA({ documentos: [{ id: 3, tipo: "rg", pais: "BR", numero: "RG999", emissor: null, emissao: null, validade: PASSADO, paperless_id: null, origem: "carga", atualizado_em: null }] })); montar();
  const li = (await screen.findByText("RG999")).closest("li")!;
  expect(li.textContent).toContain("Vencido");
  expect(li.textContent).not.toContain("Vence em breve");
});

test("Desfazer some na linha já desfeita", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ ok: true, status: 200, json: async () => env(
    /\/fichas\/p1/.test(url) ? FICHA() : /\/fichas/.test(url) ? { itens: [] } : /\/historico/.test(url) ? { itens: [{ ...HIST, desfeito_em: "2026-10-21T09:00:00" }] } : { itens: [] }) }) as Response));
  montar();
  expect(await screen.findByText(/desfeito em 21\/10\/2026/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: /Desfazer mudança/ })).toBeNull();
});

test("link do Paperless com paperless_url, senão só o id", async () => {
  fake(); montar();
  const a = await screen.findByRole("link", { name: /Paperless #77/ });
  expect(a.getAttribute("href")).toBe("https://paperless.exemplo/documents/77/details");
});
test("sem paperless_url mostra só o id", async () => {
  fake(FICHA({ paperless_url: null })); montar();
  expect(await screen.findByText("Paperless #77")).toBeTruthy();
  expect(screen.queryByRole("link", { name: /Paperless/ })).toBeNull();
});

test("proposta mostra atual e proposto, etiqueta conferir, e Aprovar posta a decisão", async () => {
  const c = fake(); montar();
  const li = (await screen.findByText(/2031/)).closest("li")!;
  expect(li.textContent).toContain("01/01/2030");
  expect(li.textContent).toContain("03/02/2031");
  expect(li.textContent).toMatch(/emissor.*emissão/);
  expect(li.textContent).toContain("conferir");
  fireEvent.click(screen.getByRole("button", { name: /Aprovar proposta 5/ }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0]).toMatchObject({ metodo: "POST", url: "/api/v1/familia/propostas/5/decisao", corpo: { estado: "aprovada" } });
});

test("Desfazer chama /historico/{id}/desfazer", async () => {
  const c = fake(); montar();
  fireEvent.click(await screen.findByRole("button", { name: /Desfazer mudança 9/ }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0].url).toBe("/api/v1/familia/historico/9/desfazer");
});

test("endereço em dict (forma do yaml) aparece como texto, não JSON", async () => {
  fake(FICHA({ enderecos: [{ tipo: "residencial", logradouro: "Rua Exemplo, 10", bairro: "Centro", cidade: "São Paulo", uf: "SP", cep: "", observacao: "portaria" }] }));
  montar();
  expect(await screen.findByText("Rua Exemplo, 10, Centro, São Paulo/SP")).toBeTruthy();
  expect(screen.queryByText(/logradouro/)).toBeNull();
});
