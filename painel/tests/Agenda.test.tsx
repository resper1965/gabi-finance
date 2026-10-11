import { vi } from "vitest";
import { act, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { CadastrosAgenda } from "../src/telas/CadastrosAgenda";
import { Agenda, diaLocal } from "../src/telas/Trabalho/Agenda";

const env = (dados: unknown) => ({ dados_ate: null, desatualizado: false, fontes: [], dados });
interface Chamada { metodo: string; url: string; corpo: unknown }
interface Opcoes { fontes?: unknown[]; parametros?: Record<string, unknown>; falha?: RegExp; negar?: boolean; calendarios?: unknown[]; agenda?: unknown }

const FONTE = { id: 1, conta: "a@x.com", provedor: "google", calendario_id: "primary", nome: "Ricardo", estado: "a_decidir", sincronizada_em: null, ultimo_erro: null, eventos: 0 };

function fake(o: Opcoes = {}) {
  const chamadas: Chamada[] = [];
  const parametros = { privados: "mostrar", fuso: "America/Sao_Paulo", janela_passado_dias: 7, janela_futuro_dias: 90, ...o.parametros };
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const metodo = init?.method ?? "GET";
    chamadas.push({ metodo, url, corpo: init?.body ? JSON.parse(String(init.body)) : undefined });
    const ok = (j: unknown) => ({ ok: true, status: 200, json: async () => j }) as Response;
    if (o.negar) return { ok: false, status: 403, json: async () => ({ erro: "sem_escopo", mensagem: "Você não tem acesso a isto." }) } as Response;
    if (metodo !== "GET") {
      if (o.falha?.test(url)) return { ok: false, status: 503, json: async () => ({ erro: "fonte_indisponivel", mensagem: "a agenda do Google não está configurada" }) } as Response;
      if (/descobrir/.test(url)) return ok(env({ calendarios: o.calendarios ?? [] }));
      return ok(env({}));
    }
    if (/agenda\/fontes/.test(url)) return ok(env({ fontes: o.fontes ?? [] }));
    if (/agenda\/parametros/.test(url)) return ok(env(parametros));
    return ok(env(o.agenda ?? { eventos: [], conflitos: [] }));
  }));
  return chamadas;
}
const montar = (tela = <CadastrosAgenda />) => render(<ToastProvider><FiltrosProvider>{tela}</FiltrosProvider></ToastProvider>);
const mudancas = (c: Chamada[]) => c.filter((x) => x.metodo !== "GET");
const assentar = async () => { for (let i = 0; i < 3; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); }); };
let erros: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  localStorage.clear();
  window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia;
  erros = vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(async () => { await assentar(); const n = erros.mock.calls.length; erros.mockRestore(); vi.unstubAllGlobals(); expect(n).toBe(0); }); // sem act() warnings nem erros

test("lista vazia mostra o estado vazio", async () => {
  fake();
  montar();
  expect(await screen.findByText(/Nenhuma agenda cadastrada/)).toBeTruthy();
});

test("liberar envia PATCH com o estado sim", async () => {
  const c = fake({ fontes: [FONTE] });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Liberar a@x.com (Ricardo)" }));
  await waitFor(() => expect(mudancas(c)).toEqual([{ metodo: "PATCH", url: "/api/v1/agenda/fontes/1", corpo: { estado: "sim" } }]));
});

test("fonte liberada oferece desligar, não liberar", async () => {
  const c = fake({ fontes: [{ ...FONTE, estado: "sim", eventos: 12, sincronizada_em: "2026-10-12T09:00:00+00:00" }] });
  montar();
  expect(await screen.findByText(/Lendo/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: /Liberar/ })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Desligar a@x.com (Ricardo)" }));
  await waitFor(() => expect(mudancas(c)[0].corpo).toEqual({ estado: "nao" }));
});

test("descobrir calendários chama a rota e mostra o resumo", async () => {
  const c = fake({ fontes: [FONTE], calendarios: [{ nova: false }, { nova: true }] });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Descobrir calendários de a@x.com" }));
  expect(await screen.findByText(/2 calendário\(s\) encontrado\(s\), 1 novo/)).toBeTruthy();
  expect(mudancas(c)[0]).toMatchObject({ metodo: "POST", url: "/api/v1/agenda/fontes/1/calendarios/descobrir" });
});

test("erro na linha aparece na linha e mantém a tela", async () => {
  fake({ fontes: [FONTE], falha: /descobrir/ });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Descobrir calendários de a@x.com" }));
  const alerta = await screen.findByRole("alert");
  expect(alerta.textContent).toContain("a agenda do Google não está configurada");
  expect(alerta.closest("li")?.textContent).toContain("a@x.com");
  expect(screen.getByRole("button", { name: "Liberar a@x.com (Ricardo)" })).toBeTruthy();
});

test("cadastrar conta envia POST e limpa o campo", async () => {
  const c = fake();
  montar();
  fireEvent.change(await screen.findByLabelText("Conta da agenda"), { target: { value: " nova@x.com " } });
  fireEvent.click(screen.getByRole("button", { name: "Cadastrar conta" }));
  await waitFor(() => expect(mudancas(c)).toEqual([{ metodo: "POST", url: "/api/v1/agenda/fontes", corpo: { conta: "nova@x.com", provedor: "google" } }]));
  await waitFor(() => expect((screen.getByLabelText("Conta da agenda") as HTMLInputElement).value).toBe(""));
});

test("ajustes validam a faixa antes de enviar e salvam só o que mudou", async () => {
  const c = fake();
  montar();
  const futuro = await screen.findByLabelText("Dias para frente");
  fireEvent.change(futuro, { target: { value: "3" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar ajustes" }));
  expect((await screen.findByRole("alert")).textContent).toContain("de 7 a 365");
  expect(mudancas(c)).toEqual([]);
  fireEvent.change(futuro, { target: { value: "120" } });
  fireEvent.change(screen.getByLabelText("Compromissos privados"), { target: { value: "ocultar" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar ajustes" }));
  await waitFor(() => expect(mudancas(c)).toEqual([{ metodo: "PUT", url: "/api/v1/agenda/parametros", corpo: { privados: "ocultar", janela_futuro_dias: 120 } }]));
});

test("quem não é o dono vê uma mensagem só", async () => {
  fake({ negar: true });
  montar();
  expect(await screen.findByText("Só o dono configura a agenda.")).toBeTruthy();
  expect(screen.queryByRole("button")).toBeNull();
});

test("a tela Agenda mostra dia inteiro, horário local, fonte e privado", async () => {
  fake({ agenda: { conflitos: [], eventos: [
    { id: 1, titulo: "Viagem", inicio_local: null, fim_local: null, dia_local: diaLocal(0), dia_fim_local: diaLocal(0), dia_inteiro: true, link_reuniao: null, fonte: "a@x.com", privado: false },
    { id: 2, titulo: "Reunião IONIC", inicio_local: "2026-10-12T14:00:00-03:00", fim_local: "2026-10-12T15:00:00-03:00", dia_local: diaLocal(0), dia_fim_local: diaLocal(0), dia_inteiro: false, link_reuniao: null, fonte: "b@x.com", privado: false },
    { id: 3, titulo: "Médico", inicio_local: "2026-10-12T22:30:00-03:00", fim_local: "2026-10-12T23:30:00-03:00", dia_local: diaLocal(0), dia_fim_local: diaLocal(0), dia_inteiro: false, link_reuniao: null, fonte: "a@x.com", privado: true }] } });
  montar(<Agenda />);
  const viagem = (await screen.findByText(/Viagem/)).closest("li")!;
  expect(viagem.textContent).toContain("dia inteiro");
  expect(viagem.textContent).toContain("a@x.com");
  expect(screen.getByText(/Reunião IONIC/).closest("li")!.textContent).toContain("14:00–15:00");
  const medico = screen.getByText(/Médico/).closest("li")!;
  expect(medico.textContent).toContain("22:30–23:30");
  expect(medico.textContent).toContain("privado");
});


const ev = (id: number, titulo: string, dia: string, fim = dia, extra: Record<string, unknown> = {}) => ({ id, titulo, inicio_local: `${dia}T10:00:00-03:00`, fim_local: `${fim}T11:00:00-03:00`, dia_local: dia, dia_fim_local: fim, dia_inteiro: false, link_reuniao: null, fonte: "a@x.com", privado: false, ...extra });

test("a tela Agenda pede os próximos 7 dias por padrão e agrupa por dia", async () => {
  const c = fake({ agenda: { conflitos: [], eventos: [ev(1, "Reunião A", diaLocal(0)), ev(2, "Plantão", diaLocal(0), diaLocal(1)), ev(3, "Almoço", diaLocal(3))] } });
  montar(<Agenda />);
  expect(await screen.findByText(/Reunião A/)).toBeTruthy();
  const url = c.find((x) => /\/api\/v1\/agenda\?/.test(x.url))!.url;
  expect(url).toBe(`/api/v1/agenda?de=${diaLocal(0)}&ate=${diaLocal(6)}`);
  expect(screen.getAllByRole("heading", { level: 4 }).length).toBe(7);          // um bloco por dia, mesmo sem compromisso
  expect(screen.getAllByText(/Plantão/).length).toBe(2);                         // cruza a meia-noite: aparece nos dois dias
  expect(screen.getAllByText(/Sem compromissos/).length).toBe(4);                // dias 2, 4, 5 e 6... (0, 1 e 3 têm evento)
});

test("escolher Amanhã pede só o dia de amanhã", async () => {
  const c = fake({ agenda: { conflitos: [], eventos: [] } });
  montar(<Agenda />);
  fireEvent.click(await screen.findByRole("button", { name: "Amanhã" }));
  await waitFor(() => expect(c.some((x) => x.url === `/api/v1/agenda?de=${diaLocal(1)}&ate=${diaLocal(1)}`)).toBe(true));
  expect(screen.getByRole("button", { name: "Amanhã" }).getAttribute("aria-pressed")).toBe("true");
});
