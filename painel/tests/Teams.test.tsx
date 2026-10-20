import { vi } from "vitest";
import { act, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { CadastrosTeams } from "../src/telas/CadastrosTeams";

const env = (dados: unknown) => ({ dados_ate: null, desatualizado: false, fontes: [], dados });
interface Chamada { metodo: string; url: string; corpo: unknown }
const FONTE = { id: 1, conta: "a@x.com", estado: "a_decidir", coletada_em: null, ultimo_erro: null };

function fake(o: { fontes?: unknown[]; falha?: boolean; negar?: boolean } = {}) {
  const chamadas: Chamada[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const metodo = init?.method ?? "GET";
    chamadas.push({ metodo, url, corpo: init?.body ? JSON.parse(String(init.body)) : undefined });
    const ok = (j: unknown) => ({ ok: true, status: 200, json: async () => j }) as Response;
    if (o.negar) return { ok: false, status: 403, json: async () => ({ erro: "sem_escopo", mensagem: "Você não tem acesso a isto." }) } as Response;
    if (metodo !== "GET") {
      if (o.falha) return { ok: false, status: 409, json: async () => ({ erro: "conflito", mensagem: "essa conta já está cadastrada" }) } as Response;
      return ok(env({}));
    }
    return ok(env({ fontes: o.fontes ?? [] }));
  }));
  return chamadas;
}
const montar = () => render(<ToastProvider><FiltrosProvider><CadastrosTeams /></FiltrosProvider></ToastProvider>);
const mudancas = (c: Chamada[]) => c.filter((x) => x.metodo !== "GET");
const assentar = async () => { for (let i = 0; i < 3; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); }); };
let erros: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  localStorage.clear();
  window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia;
  erros = vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(async () => { await assentar(); const n = erros.mock.calls.length; erros.mockRestore(); vi.unstubAllGlobals(); expect(n).toBe(0); });

test("lista vazia e aviso de que só metadados são lidos", async () => {
  fake();
  montar();
  expect(await screen.findByText(/Nenhuma conta do Teams cadastrada/)).toBeTruthy();
  expect(screen.getByText(/só quem escreveu e quando; o texto não é guardado/)).toBeTruthy();
});

test("lista a conta com estado e libera com PUT sim", async () => {
  const c = fake({ fontes: [FONTE] });
  montar();
  expect(await screen.findByText(/a@x.com/)).toBeTruthy();
  expect(screen.getByText(/A decidir/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Liberar a@x.com" }));
  await waitFor(() => expect(mudancas(c)).toEqual([{ metodo: "PUT", url: "/api/v1/teams/fontes/1/estado", corpo: { estado: "sim" } }]));
});

test("conta liberada oferece pausar, não liberar", async () => {
  const c = fake({ fontes: [{ ...FONTE, estado: "sim", coletada_em: "2026-10-12T09:00:00+00:00" }] });
  montar();
  expect((await screen.findByText(/última coleta/)).textContent).toContain("12/10, 06:00");
  expect(screen.queryByRole("button", { name: /Liberar/ })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Pausar a@x.com" }));
  await waitFor(() => expect(mudancas(c)[0].corpo).toEqual({ estado: "nao" }));
});

test("ultimo_erro é aviso quando já coletou, erro quando não", async () => {
  fake({ fontes: [
    { ...FONTE, id: 1, conta: "ok@x.com", estado: "sim", coletada_em: "2026-10-12T09:00:00+00:00", ultimo_erro: "2 chat(s) pulado(s) por erro" },
    { ...FONTE, id: 2, conta: "mau@x.com", estado: "sim", ultimo_erro: "token expirado" },
  ] });
  montar();
  expect((await screen.findByText(/Aviso: 2 chat\(s\) pulado\(s\) por erro/)).textContent).toBeTruthy();
  expect(screen.getByText(/Último erro: token expirado/)).toBeTruthy();
});

test("cadastra conta nova com POST", async () => {
  const c = fake();
  montar();
  fireEvent.change(await screen.findByLabelText("Conta do Teams"), { target: { value: " n@x.com " } });
  fireEvent.click(screen.getByRole("button", { name: "Cadastrar conta" }));
  await waitFor(() => expect(mudancas(c)).toEqual([{ metodo: "POST", url: "/api/v1/teams/fontes", corpo: { conta: "n@x.com" } }]));
});

test("erro da API aparece no cadastro", async () => {
  fake({ falha: true });
  montar();
  fireEvent.change(await screen.findByLabelText("Conta do Teams"), { target: { value: "n@x.com" } });
  fireEvent.click(screen.getByRole("button", { name: "Cadastrar conta" }));
  expect((await screen.findByRole("alert")).textContent).toContain("essa conta já está cadastrada");
});

test("sem acesso mostra a frase do dono", async () => {
  fake({ negar: true });
  montar();
  expect(await screen.findByText(/Só o dono configura o Teams/)).toBeTruthy();
});
