import { vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { Escuta } from "../src/telas/Escuta";

const env = (dados: unknown) => ({ dados_ate: null, desatualizado: false, fontes: [], dados });
interface Chamada { metodo: string; url: string; corpo: unknown }

function fake(o: { fila?: unknown[]; aprovados?: unknown[]; grupos?: unknown[]; parametros?: Record<string, unknown>; falha?: RegExp } = {}) {
  const chamadas: Chamada[] = [];
  const parametros = { modo: "registro", palavras_risco: ["urgente", "multa"], horas_sem_receber: 12, anexo_max_mb: 25, ...o.parametros };
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const metodo = init?.method ?? "GET";
    chamadas.push({ metodo, url, corpo: init?.body ? JSON.parse(String(init.body)) : undefined });
    const ok = (j: unknown) => ({ ok: true, status: 200, json: async () => j }) as Response;
    if (metodo !== "GET" && o.falha?.test(url)) return { ok: false, status: 400, json: async () => ({ erro: "requisicao_invalida", mensagem: "papel inválido" }) } as Response;
    if (metodo !== "GET") return ok(env({}));
    if (/remetentes/.test(url)) return ok(env({ fila: o.fila ?? [], aprovados: o.aprovados ?? [] }));
    if (/grupos/.test(url)) return ok(env({ grupos: o.grupos ?? [] }));
    return ok(env(parametros));
  }));
  return chamadas;
}
const montar = () => render(<ToastProvider><FiltrosProvider><Escuta /></FiltrosProvider></ToastProvider>);
const posts = (c: Chamada[]) => c.filter((x) => x.metodo !== "GET");
beforeEach(() => { localStorage.clear(); window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

const FILA = [{ numero: "+5511911110000", nome: "Ana", qtd: 3 }, { numero: "+5511922220000", nome: null, qtd: 1 }];

test("fila vazia mostra o estado vazio", async () => {
  fake();
  montar();
  expect(await screen.findByText(/Nenhum remetente novo/)).toBeTruthy();
});

test("numero aparece junto do nome quando ha nome, e sozinho quando nao ha", async () => {
  fake({ fila: FILA });
  montar();
  const ana = (await screen.findByText("Ana")).closest("li")!;
  expect(ana.textContent).toContain("+5511911110000");
  expect(ana.textContent).toContain("3");
  expect(screen.getByText("+5511922220000")).toBeTruthy();
});

test("aprovar exige escolher o papel antes de enviar", async () => {
  const c = fake({ fila: FILA });
  montar();
  const linha = (await screen.findByText("Ana")).closest("li")!;
  fireEvent.click(within(linha).getByRole("button", { name: "Aprovar" }));
  expect(posts(c)).toHaveLength(0);
  fireEvent.click(within(linha).getByRole("button", { name: "Prestador" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0].url).toBe("/api/v1/escuta/remetentes/%2B5511911110000/aprovar");
  expect(posts(c)[0].corpo).toEqual({ papel: "prestador" });
  await waitFor(() => expect(c.filter((x) => x.metodo === "GET" && /remetentes/.test(x.url)).length).toBeGreaterThan(1));
});

test("ignorar e bloquear chamam a rota certa", async () => {
  const c = fake({ fila: FILA });
  montar();
  const linha = (await screen.findByText("Ana")).closest("li")!;
  fireEvent.click(within(linha).getByRole("button", { name: "Ignorar" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0].url).toBe("/api/v1/escuta/remetentes/%2B5511911110000/ignorar");
  fireEvent.click(within(linha).getByRole("button", { name: "Bloquear" }));
  await waitFor(() => expect(posts(c)).toHaveLength(2));
  expect(posts(c)[1].url).toBe("/api/v1/escuta/remetentes/%2B5511911110000/bloquear");
});

test("erro da API aparece e a linha nao some", async () => {
  fake({ fila: FILA, falha: /ignorar/ });
  montar();
  const linha = (await screen.findByText("Ana")).closest("li")!;
  fireEvent.click(within(linha).getByRole("button", { name: "Ignorar" }));
  expect(await screen.findAllByText(/papel inválido/)).not.toHaveLength(0);
  expect(screen.getByText("Ana")).toBeTruthy();
});

test("lista aprovados e aprova grupo", async () => {
  const c = fake({ aprovados: [{ pessoa_id: "p1", nome: "Bia", numero: "+5511933330000", papel: "familia" }], grupos: [{ id_grupo: "g1@g.us", nome: "Condomínio", aprovado: false }] });
  montar();
  expect(await screen.findByText("Bia")).toBeTruthy();
  fireEvent.click(await screen.findByRole("button", { name: "Aprovar grupo Condomínio" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0].url).toBe("/api/v1/escuta/grupos/g1%40g.us/aprovar");
});

test("trocar para ativo mostra o aviso e exige confirmacao", async () => {
  const c = fake();
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Ativo" }));
  expect(screen.getByText(/em registro a escuta só registra; em ativo ela cria pedidos e avisa/i)).toBeTruthy();
  expect(posts(c)).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "Confirmar modo ativo" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0]).toMatchObject({ metodo: "PUT", url: "/api/v1/escuta/parametros", corpo: { modo: "ativo" } });
});

test("palavras de risco: adicionar e remover enviam a lista inteira", async () => {
  const c = fake();
  montar();
  fireEvent.change(await screen.findByLabelText("Nova palavra de risco"), { target: { value: "processo" } });
  fireEvent.click(screen.getByRole("button", { name: "Adicionar palavra" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0].corpo).toEqual({ palavras_risco: ["urgente", "multa", "processo"] });
  fireEvent.click(await screen.findByRole("button", { name: "Remover urgente" }));
  await waitFor(() => expect(posts(c)).toHaveLength(2));
  expect(posts(c)[1].corpo).toEqual({ palavras_risco: ["multa"] });
});

test("horas e anexo gravam com chaves curtas", async () => {
  const c = fake();
  montar();
  fireEvent.change(await screen.findByLabelText("Horas sem receber"), { target: { value: "24" } });
  fireEvent.change(screen.getByLabelText("Tamanho máximo de anexo (MB)"), { target: { value: "10" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar limites" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0].corpo).toEqual({ horas_sem_receber: 24, anexo_max_mb: 10 });
});
