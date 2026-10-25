import { vi } from "vitest";
import { act, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { CadastrosDocumentos } from "../src/telas/CadastrosDocumentos";
import { App } from "../src/App";
import { apiFalsa } from "./apiFalsa";

const env = (dados: unknown) => ({ dados_ate: null, desatualizado: false, fontes: [], dados });
interface Chamada { metodo: string; url: string; corpo: unknown }
const isoDias = (dias: number) => { const d = new Date(); d.setDate(d.getDate() + dias); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const BREVE = isoDias(30), LONGE = isoDias(400), PASSADO = isoDias(-20);
const dd = (s: string) => `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}`;

const docBase = { pais: "BR", emissor: null, origem: "leitura", criado_em: "2026-10-01", atualizado_em: "2026-10-01", excluido_em: null };
const PASSAPORTE = { ...docBase, id: 1, titular_tipo: "pessoa", titular_id: "lia", tipo: "passaporte", emissor: "PF", paperless_id: 77,
  numeros: [{ nome: "numero", valor: "FK077009" }], datas: [{ tipo: "emissao", data: "2020-01-01" }, { tipo: "validade", data: BREVE }] };
const CPF = { ...docBase, id: 2, titular_tipo: "pessoa", titular_id: "lia", tipo: "cpf", paperless_id: null, numeros: [{ nome: "numero", valor: "111.444.777-35" }], datas: [] };
const RG = { ...docBase, id: 3, titular_tipo: "pessoa", titular_id: "lia", tipo: "rg", paperless_id: null, numeros: [{ nome: "numero", valor: "RG999" }], datas: [{ tipo: "validade", data: PASSADO }] };
const CRLV = { ...docBase, id: 4, titular_tipo: "bem", titular_id: "carro", tipo: "crlv", paperless_id: null, numeros: [{ nome: "placa", valor: "ABC1D23" }], datas: [{ tipo: "vencimento", data: LONGE }] };
const TITULARES = {
  pessoas: [
    { id: "lia", nome: "Lia", nome_completo: "Lia Souza", apelido: "Lilica", parentesco: "filha", nascimento: "2015-03-04",
      telefones: ["+5511999990000"], emails: ["lia@x.com"], enderecos: [{ logradouro: "Rua Exemplo, 10", cidade: "São Paulo", uf: "SP" }], documentos: [PASSAPORTE, CPF, RG] },
    { id: "bia", nome: "Beatriz", nome_completo: null, apelido: null, parentesco: null, nascimento: null, telefones: [], emails: [], enderecos: [], documentos: [] },
  ],
  bens: [{ id: "carro", tipo: "veiculo", nome: "Carro", dados: { modelo: "Onix" }, documentos: [CRLV] }],
  paperless_url: "https://paperless.exemplo",
};
const DOC_PROPOSTO = { titular_tipo: "pessoa", titular_id: "lia", tipo: "passaporte", pais: "BR", emissor: null,
  numeros: [{ nome: "numero", valor: "FK077009" }], datas: [{ tipo: "validade", data: "2031-02-03" }] };
const PROPOSTA = { id: 5, titular: { tipo: "pessoa", id: "lia", nome: "Lia" }, doc: DOC_PROPOSTO, bem_novo: null, conferir: true,
  motivos: ["validade antes da emissão"], paperless_id: 88, origem: "leitura", estado: "pendente", criada_em: "2026-10-22T12:00:00Z", atual: null };
const BEM_NOVO = { ...PROPOSTA, id: 6, titular: null, doc: { ...DOC_PROPOSTO, titular_tipo: "bem", titular_id: null, tipo: "iptu", numeros: [{ nome: "inscricao_iptu", valor: "123.456" }] },
  bem_novo: { tipo: "imovel", nome: "Apartamento Rua das Flores", dados: {} }, motivos: ["titular não encontrado"], paperless_id: null };
const HIST = { id: 9, pessoa_id: "lia", campo: "telefones", antes: [], depois: ["+5511999990000"], quem: "hermes", quando: "2026-10-20T10:00:00", desfeito_em: null };

function fake(o: { propostas?: unknown[]; titulares?: unknown; vencimentos?: unknown[] } = {}) {
  const chamadas: Chamada[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const metodo = init?.method ?? "GET";
    chamadas.push({ metodo, url, corpo: init?.body ? JSON.parse(String(init.body)) : undefined });
    const ok = (j: unknown) => ({ ok: true, status: 200, json: async () => env(j) }) as Response;
    if (metodo !== "GET") return ok({});
    if (/\/documentos\/propostas/.test(url)) return ok({ itens: o.propostas ?? [PROPOSTA], paperless_url: "https://paperless.exemplo" });
    if (/\/documentos\/titulares/.test(url)) return ok(o.titulares ?? TITULARES);
    if (/\/documentos\/vencimentos/.test(url)) return ok({ itens: o.vencimentos ?? [] });
    if (/\/familia\/historico/.test(url)) return ok({ itens: [HIST] });
    return ok({ itens: [] });
  }));
  return chamadas;
}
const montar = () => render(<ToastProvider><CadastrosDocumentos /></ToastProvider>);
const posts = (c: Chamada[]) => c.filter((x) => x.metodo !== "GET");
let erros: ReturnType<typeof vi.spyOn>;
beforeEach(() => { erros = vi.spyOn(console, "error").mockImplementation(() => {}); });
afterEach(async () => { await act(async () => { await new Promise((r) => setTimeout(r, 0)); }); const n = erros.mock.calls.length; erros.mockRestore(); vi.unstubAllGlobals(); expect(n).toBe(0); });

test("cartão mostra titular, motivos de conferir e link do Paperless", async () => {
  fake(); montar();
  const card = (await screen.findByRole("button", { name: "Aprovar proposta 5" })).closest("li")!;
  expect(card.textContent).toContain("Lia");
  expect(card.textContent).toContain("PASSAPORTE");
  expect(card.textContent).toContain("FK077009");
  expect(card.textContent).toContain("03/02/2031");
  expect(card.textContent).toContain("conferir");
  expect(card.textContent).toContain("validade antes da emissão");
  const a = screen.getByRole("link", { name: "Paperless #88" });
  expect(a.getAttribute("href")).toBe("https://paperless.exemplo/documents/88/details");
});

test("cartão sem titular mostra o bem novo", async () => {
  fake({ propostas: [BEM_NOVO] }); montar();
  const card = (await screen.findByRole("button", { name: "Aprovar proposta 6" })).closest("li")!;
  expect(card.textContent).toContain("bem novo: Apartamento Rua das Flores");
  expect(card.textContent).toContain("titular não encontrado");
});

test("aprovar sem editar posta só o estado; recusar posta recusada", async () => {
  const c = fake(); montar();
  fireEvent.click(await screen.findByRole("button", { name: "Aprovar proposta 5" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0]).toMatchObject({ metodo: "POST", url: "/api/v1/documentos/propostas/5/decisao", corpo: { estado: "aprovada" } });
  expect(posts(c)[0].corpo).not.toHaveProperty("correcao");
  await waitFor(() => expect(screen.getByRole("button", { name: "Recusar proposta 5" })).not.toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: "Recusar proposta 5" }));
  await waitFor(() => expect(posts(c)).toHaveLength(2));
  expect(posts(c)[1].corpo).toEqual({ estado: "recusada" });
});

test("aprovar depois de corrigir um campo posta a correcao só desse campo", async () => {
  const c = fake(); montar();
  fireEvent.click(await screen.findByRole("button", { name: "Corrigir proposta 5" }));
  fireEvent.change(screen.getByLabelText("validade da proposta 5"), { target: { value: "2032-04-05" } });
  fireEvent.click(screen.getByRole("button", { name: "Aprovar proposta 5" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0].corpo).toEqual({ estado: "aprovada", correcao: { datas: [{ tipo: "validade", data: "2032-04-05" }] } });
});

test("corrigir o número e escolher outro titular vão na correcao", async () => {
  const c = fake(); montar();
  fireEvent.click(await screen.findByRole("button", { name: "Corrigir proposta 5" }));
  fireEvent.change(screen.getByLabelText("numero da proposta 5"), { target: { value: "FK077010" } });
  fireEvent.change(screen.getByLabelText("Titular da proposta 5"), { target: { value: "bem:carro" } });
  fireEvent.click(screen.getByRole("button", { name: "Aprovar proposta 5" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0].corpo).toEqual({ estado: "aprovada", correcao: { numeros: [{ nome: "numero", valor: "FK077010" }], titular_tipo: "bem", titular_id: "carro" } });
});

test("lista por titular com contato, número completo e botão copiar", async () => {
  const escrever = vi.fn(async () => {});
  Object.defineProperty(navigator, "clipboard", { value: { writeText: escrever }, configurable: true });
  fake(); montar();
  expect(await screen.findByText("111.444.777-35")).toBeTruthy();
  expect(screen.getAllByText("+5511999990000").length).toBeGreaterThan(0);
  expect(screen.getByText("lia@x.com")).toBeTruthy();
  expect(screen.getByText("Rua Exemplo, 10, São Paulo/SP")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Copiar numero de CPF" }));
  await waitFor(() => expect(escrever).toHaveBeenCalledWith("111.444.777-35"));
  expect(await screen.findByText("Copiado.")).toBeTruthy();
});

test("vencido em destaque; vence em até 60 dias em atenção", async () => {
  fake(); montar();
  const rg = (await screen.findByText("RG999")).closest("li")!;
  expect(rg.textContent).toContain("Vencido");
  expect(rg.textContent).toContain(dd(PASSADO));
  const pass = screen.getByText(dd(BREVE)).closest("li")!;
  expect(pass.textContent).toContain("Vence em até 60 dias");
  expect(pass.textContent).not.toContain("Vencido");
  expect(screen.getByText("111.444.777-35").closest("li")!.textContent).not.toMatch(/Vencido|Vence em/);
});

test("bem aparece como titular com os documentos", async () => {
  fake(); montar();
  fireEvent.click(await screen.findByRole("button", { name: /Carro · 1/ }));
  const li = (await screen.findByText("ABC1D23")).closest("li")!;
  expect(li.textContent).toContain("CRLV");
  expect(li.textContent).toContain(dd(LONGE));
  expect(li.textContent).not.toMatch(/Vencido|Vence em/);
});

test("histórico de contato continua na aba, com Desfazer", async () => {
  const c = fake(); montar();
  fireEvent.click(await screen.findByRole("button", { name: "Desfazer mudança 9" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0].url).toBe("/api/v1/familia/historico/9/desfazer");
});

test("vencimentos listados com titular e data", async () => {
  fake({ vencimentos: [{ documento_id: 3, titular_tipo: "pessoa", titular_id: "lia", titular_nome: "Lia", tipo: "rg", data_tipo: "validade", data: PASSADO, vencido: true }] });
  montar();
  const li = (await screen.findByText(/Lia · RG/)).closest("li")!;
  expect(li.textContent).toContain("Vencido");
});

test("#cadastros/familia abre a aba Documentos", async () => {
  apiFalsa();
  const base = globalThis.fetch;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (/\/documentos\/|\/familia\//.test(url)) return { ok: true, status: 200, json: async () => env(/titulares/.test(url) ? TITULARES : { itens: [], paperless_url: null }) } as Response;
    return base(url, init);
  }));
  window.location.hash = "#cadastros/familia";
  render(<App />);
  expect(await screen.findByRole("tab", { name: "Documentos", selected: true })).toBeInTheDocument();
  expect(window.location.hash).toBe("#cadastros/documentos");
  window.location.hash = "";
  expect(await screen.findByText("Lia Souza")).toBeInTheDocument();
});

test("sem paperless_url mostra só o id do Paperless", async () => {
  fake({ propostas: [], titulares: { ...TITULARES, paperless_url: null } }); montar();
  expect(await screen.findByText("Paperless #77")).toBeTruthy();
  expect(screen.queryByRole("link", { name: /Paperless/ })).toBeNull();
});

test("Desfazer some na linha já desfeita", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ ok: true, status: 200, json: async () => env(
    /titulares/.test(url) ? TITULARES : /\/historico/.test(url) ? { itens: [{ ...HIST, desfeito_em: "2026-10-21T09:00:00" }] } : { itens: [], paperless_url: null }) }) as Response));
  montar();
  expect(await screen.findByText(/desfeito em 21\/10\/2026/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: /Desfazer mudança/ })).toBeNull();
});
