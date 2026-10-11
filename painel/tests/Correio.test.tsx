import { vi } from "vitest";
import { act, render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { CadastrosCorreio } from "../src/telas/CadastrosCorreio";
import { Prioridades } from "../src/telas/Trabalho/Prioridades";

const env = (dados: unknown) => ({ dados_ate: null, desatualizado: false, fontes: [], dados });
interface Chamada { metodo: string; url: string; corpo: unknown }
interface Opcoes { fontes?: unknown[]; parametros?: Record<string, unknown>; prioridades?: unknown[]; lixeira?: unknown[]; falha?: RegExp; negar?: boolean }

const FONTE = { id: 1, conta: "a@x.com", provedor: "google", estado: "a_decidir", lixeira: 0, sincronizada_em: null, ultimo_erro: null, mensagens: 0, na_lixeira: 0 };
const MSG = { id: 7, conta: "a@x.com", remetente: "banco@x.com", assunto: "Boleto vence hoje", recebida_em: "2026-10-12T13:00:00+00:00", classe: "emergencial", prioridade: 3, motivo: "prazo hoje" };

function fake(o: Opcoes = {}) {
  const chamadas: Chamada[] = [];
  let lixeira = o.lixeira ?? [];
  const parametros = { criterios_emergencia: "", vips: [], lixeira_confianca: 0.9, janela_dias: 14, retencao_dias: 30, ...o.parametros };
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const metodo = init?.method ?? "GET";
    chamadas.push({ metodo, url, corpo: init?.body ? JSON.parse(String(init.body)) : undefined });
    const ok = (j: unknown) => ({ ok: true, status: 200, json: async () => j }) as Response;
    if (o.negar) return { ok: false, status: 403, json: async () => ({ erro: "sem_escopo", mensagem: "Você não tem acesso a isto." }) } as Response;
    if (metodo !== "GET") {
      if (o.falha?.test(url)) return { ok: false, status: 503, json: async () => ({ erro: "fonte_indisponivel", mensagem: "o Gmail não confirmou a restauração" }) } as Response;
      if (/restaurar/.test(url)) lixeira = [];
      return ok(env({}));
    }
    if (/correio\/fontes/.test(url)) return ok(env({ fontes: o.fontes ?? [] }));
    if (/correio\/parametros/.test(url)) return ok(env(parametros));
    if (/correio\/prioridades/.test(url)) return ok(env({ mensagens: o.prioridades ?? [] }));
    if (/correio\/lixeira/.test(url)) return ok(env({ mensagens: lixeira }));
    return { ok: false, status: 404, json: async () => ({ erro: "nao_encontrado", mensagem: url }) } as Response;
  }));
  return chamadas;
}
const montar = (tela = <CadastrosCorreio />) => render(<ToastProvider><FiltrosProvider>{tela}</FiltrosProvider></ToastProvider>);
const mudancas = (c: Chamada[]) => c.filter((x) => x.metodo !== "GET");
const assentar = async () => { for (let i = 0; i < 3; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); }); };
let erros: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  localStorage.clear();
  window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia;
  erros = vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(async () => { await assentar(); const n = erros.mock.calls.length; erros.mockRestore(); vi.unstubAllGlobals(); expect(n).toBe(0); }); // sem act() warnings nem erros

test("sem contas mostra o estado vazio", async () => {
  fake();
  montar();
  expect(await screen.findByText(/Nenhuma conta cadastrada/)).toBeTruthy();
});

test("liberar a leitura envia PATCH com estado sim e não oferece a lixeira antes", async () => {
  const c = fake({ fontes: [FONTE] });
  montar();
  expect(screen.queryByRole("button", { name: /Ligar lixeira/ })).toBeNull();
  fireEvent.click(await screen.findByRole("button", { name: "Liberar leitura de a@x.com" }));
  await waitFor(() => expect(mudancas(c)).toEqual([{ metodo: "PATCH", url: "/api/v1/correio/fontes/1", corpo: { estado: "sim" } }]));
});

test("ligar a lixeira pede confirmação e envia um PATCH só da lixeira", async () => {
  const c = fake({ fontes: [{ ...FONTE, estado: "sim" }] });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Ligar lixeira de a@x.com" }));
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(mudancas(c)).toEqual([]); // nada foi enviado antes de confirmar
  fireEvent.click(screen.getByRole("button", { name: "Confirmar lixeira de a@x.com" }));
  await waitFor(() => expect(mudancas(c)).toEqual([{ metodo: "PATCH", url: "/api/v1/correio/fontes/1", corpo: { lixeira: 1 } }]));
});

test("cancelar a confirmação não envia nada", async () => {
  const c = fake({ fontes: [{ ...FONTE, estado: "sim" }] });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Ligar lixeira de a@x.com" }));
  fireEvent.click(await screen.findByRole("button", { name: "Cancelar" }));
  expect(screen.queryByRole("alert")).toBeNull();
  expect(mudancas(c)).toEqual([]);
});

test("com a lixeira ligada oferece desligar", async () => {
  const c = fake({ fontes: [{ ...FONTE, estado: "sim", lixeira: 1, mensagens: 30, na_lixeira: 4, sincronizada_em: "2026-10-12T12:00:00+00:00" }] });
  montar();
  expect(await screen.findByText(/lixeira ligada/)).toBeTruthy();
  expect(screen.getByText(/4 na lixeira/)).toBeTruthy();
  expect(screen.getByText(/última leitura 12\/10,? 09:00/)).toBeTruthy(); // 12:00 UTC = 09:00 em Brasília
  fireEvent.click(screen.getByRole("button", { name: "Desligar lixeira de a@x.com" }));
  await waitFor(() => expect(mudancas(c)[0].corpo).toEqual({ lixeira: 0 }));
});

test("erro na linha aparece na linha e mantém a tela", async () => {
  fake({ fontes: [FONTE], falha: /fontes\/1/ });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Liberar leitura de a@x.com" }));
  const alerta = await screen.findByRole("alert");
  expect(alerta.closest("li")?.textContent).toContain("a@x.com");
  expect(screen.getByRole("button", { name: "Liberar leitura de a@x.com" })).toBeTruthy();
});

test("cadastrar conta envia POST e limpa o campo", async () => {
  const c = fake();
  montar();
  fireEvent.change(await screen.findByLabelText("Conta de e-mail"), { target: { value: " nova@x.com " } });
  fireEvent.click(screen.getByRole("button", { name: "Cadastrar conta" }));
  await waitFor(() => expect(mudancas(c)).toEqual([{ metodo: "POST", url: "/api/v1/correio/fontes", corpo: { conta: "nova@x.com", provedor: "google" } }]));
  await waitFor(() => expect((screen.getByLabelText("Conta de e-mail") as HTMLInputElement).value).toBe(""));
});

test("ajustes recusam confiança fora da faixa antes de enviar e mandam só o que mudou", async () => {
  const c = fake();
  montar();
  const limiar = await screen.findByLabelText(/Confiança mínima/);
  fireEvent.change(limiar, { target: { value: "0,3" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar ajustes" }));
  expect((await screen.findByRole("alert")).textContent).toContain("de 0,5 a 1");
  expect(mudancas(c)).toEqual([]);
  fireEvent.change(limiar, { target: { value: "0,95" } });
  fireEvent.change(screen.getByLabelText("VIPs"), { target: { value: "chefe@x.com\n\n bia@x.com " } });
  fireEvent.change(screen.getByLabelText("Critérios de emergência"), { target: { value: "banco com prazo" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar ajustes" }));
  await waitFor(() => expect(mudancas(c)).toEqual([{ metodo: "PUT", url: "/api/v1/correio/parametros", corpo: { criterios_emergencia: "banco com prazo", vips: ["chefe@x.com", "bia@x.com"], lixeira_confianca: 0.95 } }]));
});

test("quem não é o dono vê uma mensagem só", async () => {
  fake({ negar: true });
  montar();
  expect(await screen.findByText("Só o dono configura o e-mail.")).toBeTruthy();
  expect(screen.queryByRole("button")).toBeNull();
});

test("prioridades mostra emergencial primeiro com horário de Brasília e a lixeira com restaurar", async () => {
  fake({ prioridades: [MSG, { ...MSG, id: 8, classe: "importante", assunto: "Proposta", remetente: "ana@x.com", motivo: "cliente" }], lixeira: [{ ...MSG, id: 9, classe: "lixo", assunto: "Oferta", remetente: "promo@loja.com", motivo: "promoção" }] });
  montar(<Prioridades />);
  const emergencial = (await screen.findByText(/Boleto vence hoje/)).closest("li")!;
  expect(emergencial.textContent).toContain("Emergencial");
  expect(emergencial.textContent).toContain("10:00"); // 13:00 UTC = 10:00 em Brasília
  expect(screen.getByText(/Proposta/).closest("li")!.textContent).not.toContain("Emergencial");
  expect(screen.getByRole("button", { name: "Restaurar Oferta" })).toBeTruthy();
});

test("restaurar envia POST, relê e a mensagem some da lixeira", async () => {
  const c = fake({ lixeira: [{ ...MSG, id: 9, classe: "lixo", assunto: "Oferta", remetente: "promo@loja.com", motivo: "promoção" }] });
  montar(<Prioridades />);
  fireEvent.click(await screen.findByRole("button", { name: "Restaurar Oferta" }));
  await waitFor(() => expect(mudancas(c)).toEqual([{ metodo: "POST", url: "/api/v1/correio/mensagens/9/restaurar", corpo: {} }]));
  await waitFor(() => expect(screen.queryByRole("button", { name: "Restaurar Oferta" })).toBeNull());
  expect(screen.getByText(/Nada foi para a lixeira/)).toBeTruthy();
});

test("erro ao restaurar aparece na linha e a mensagem continua na lixeira", async () => {
  fake({ lixeira: [{ ...MSG, id: 9, classe: "lixo", assunto: "Oferta", remetente: "promo@loja.com", motivo: "promoção" }], falha: /restaurar/ });
  montar(<Prioridades />);
  fireEvent.click(await screen.findByRole("button", { name: "Restaurar Oferta" }));
  const alerta = await screen.findByRole("alert");
  expect(within(alerta.closest("li")!).getByRole("button", { name: "Restaurar Oferta" })).toBeTruthy();
  expect(alerta.textContent).toContain("o Gmail não confirmou");
});

test("prioridades vazias mostram as duas frases e 403 mostra uma só", async () => {
  fake();
  montar(<Prioridades />);
  expect(await screen.findByText(/Nada importante esperando/)).toBeTruthy();
  expect(await screen.findByText(/Nada foi para a lixeira/)).toBeTruthy();
});

test("prioridades para quem não é o dono", async () => {
  fake({ negar: true });
  montar(<Prioridades />);
  expect(await screen.findByText("Só o dono vê o e-mail.")).toBeTruthy();
});
