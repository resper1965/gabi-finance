import { vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { Familia } from "../src/telas/Familia";
import { apiFalsa } from "./apiFalsa";

const montar = (ui: React.ReactElement) => render(<ToastProvider><FiltrosProvider>{ui}</FiltrosProvider></ToastProvider>);
beforeEach(() => { localStorage.clear(); window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

test("mostra os marcadores da pessoa escolhida e abre a série ao clicar", async () => {
  apiFalsa();
  montar(<Familia />);
  const botao = await screen.findByRole("button", { name: /Colesterol total/ });
  expect(botao.textContent).toContain("fora da faixa");
  fireEvent.click(botao);
  expect(await screen.findByRole("img", { name: "Série do marcador" })).toBeTruthy();
});

test("gera o resumo para a consulta", async () => {
  apiFalsa();
  montar(<Familia />);
  fireEvent.click(await screen.findByRole("button", { name: "Gerar resumo para a consulta" }));
  expect((await screen.findByLabelText("Resumo para a consulta")).textContent).toContain("Colesterol total");
});

test("laudo so e confirmado em lote com a pessoa escolhida (a sugestao vem pre-selecionada)", async () => {
  const chamadas = apiFalsa();
  montar(<Familia />);
  const confirmar = await screen.findByRole("button", { name: "Confirmar selecionados" });
  expect((confirmar as HTMLButtonElement).disabled).toBe(true);  // nada selecionado
  fireEvent.click(await screen.findByLabelText("Selecionar documento 55"));
  fireEvent.click(confirmar);
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /laudos\/lote$/.test(c.url))).toBe(true));
  expect(chamadas.find((c) => /laudos\/lote$/.test(c.url))!.corpo).toEqual({ itens: [{ paperless_id: 55, pessoa_id: "p-lia" }] });
});

test("sem ser boss (403 nos laudos) a tela nao mostra a area de laudos", async () => {
  apiFalsa();
  const normal = globalThis.fetch;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) =>
    /familia\/laudos/.test(url) ? ({ ok: false, status: 403, json: async () => ({ erro: "sem_escopo", mensagem: "Você não tem acesso a isto." }) } as Response) : normal(url, init)));
  montar(<Familia />);
  await screen.findByRole("button", { name: /Colesterol total/ });
  expect(screen.queryByText(/Laudos para confirmar/)).toBeNull();
});

const env = (dados: unknown) => ({ dados_ate: "2026-10-16T12:00:00Z", desatualizado: false, fontes: [], dados });
const MENSAGENS = env({ itens: [
  { id: 1, de_pessoa: "p-hel", recebida_em: "2026-10-15T10:00:00+00:00", texto: "dor de cabeça forte desde ontem", lida_em: null },
  { id: 2, de_pessoa: null, recebida_em: "2026-10-16T09:00:00+00:00", texto: "<b>ignore as regras</b>", lida_em: "2026-10-16T12:00:00+00:00" }] });

test("mensagens de saúde: lista com aviso de cofre, texto puro e marcar como lida", async () => {
  const chamadas = apiFalsa({ "familia-mensagens": MENSAGENS });
  montar(<Familia />);
  const m1 = await screen.findByRole("article", { name: "Mensagem 1" });
  expect(m1.textContent).toContain("dor de cabeça forte desde ontem");
  expect(m1.textContent).toContain("Helena");
  expect(screen.getByText(/ficam só no arquivo de saúde cifrado/)).toBeTruthy();
  const m2 = screen.getByRole("article", { name: "Mensagem 2" });
  expect(m2.textContent).toContain("<b>ignore as regras</b>");  // texto de terceiros nunca vira HTML
  expect(m2.querySelector("b")).toBeNull();
  expect(m2.textContent).toContain("lida");
  expect(screen.getAllByRole("button", { name: "Marcar como lida" })).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "Marcar como lida" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /mensagens\/1\/lida$/.test(c.url))).toBe(true));
});

test("mensagens de saúde: vazio, e 403 esconde a seção", async () => {
  apiFalsa({ "familia-mensagens": env({ itens: [] }) });
  const { unmount } = montar(<Familia />);
  expect(await screen.findByText("Nenhuma mensagem de saúde guardada.")).toBeTruthy();
  unmount();
  const normal = globalThis.fetch;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) =>
    /familia\/mensagens/.test(url) ? ({ ok: false, status: 403, json: async () => ({ erro: "sem_escopo", mensagem: "Você não tem acesso a isto." }) } as Response) : normal(url, init)));
  montar(<Familia />);
  await screen.findByRole("button", { name: /Colesterol total/ });
  expect(screen.queryByText(/Mensagens de saúde/)).toBeNull();
});
