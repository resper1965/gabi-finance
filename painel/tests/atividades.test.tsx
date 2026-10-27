import { vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { Atividades } from "../src/telas/Atividades";
import { GRUPOS } from "../src/navegacao";
import { TELAS } from "../src/App";
import { apiFalsa, type Chamada } from "./apiFalsa";

const item = (id: number, texto: string, prazo: string, vence_em: string | null = null, tem_hora = false) =>
  ({ id, texto, vence_em, tem_hora, status: "aberta", origem: "hermes", criada_em: "2026-10-20T12:00:00+00:00", concluida_em: null, prazo });
const LISTA = { dados_ate: null, desatualizado: false, fontes: [], dados: { itens: [
  item(1, "pagar o IPTU", "vencida", "2026-10-26"), item(2, "ligar pro contador", "hoje", "2026-10-27T10:00", true),
  item(3, "renovar o seguro", "proxima", "2026-11-05"), item(4, "ver a escola da Louise", "sem_data"),
] } };

const montar = () => render(<ToastProvider><Atividades /></ToastProvider>);
const achar = (c: Chamada[], metodo: string, fim: string) => c.find((x) => x.metodo === metodo && x.url.endsWith(fim));
beforeEach(() => { vi.useFakeTimers({ toFake: ["Date"] }); vi.setSystemTime(new Date("2026-10-27T15:00:00")); });  // só o relógio: waitFor segue com timers reais
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

test("lista agrupada em Vencidas, Hoje, Próximas e Sem data, e esconde o grupo vazio", async () => {
  apiFalsa({ atividades: { ...LISTA, dados: { itens: LISTA.dados.itens.filter((i) => i.prazo !== "proxima") } } });
  montar();
  const grupos = (await screen.findAllByRole("heading", { level: 4 })).map((h) => h.textContent);
  expect(grupos).toEqual(["Vencidas", "Hoje", "Sem data"]);
  expect(screen.getByText("ligar pro contador")).toBeInTheDocument();
  expect(screen.getByText(/10:00/)).toBeInTheDocument();
});

test("sem nenhuma atividade mostra 'Nada para fazer.'", async () => {
  apiFalsa();
  montar();
  expect(await screen.findByText("Nada para fazer.")).toBeInTheDocument();
});

test("criar com data e hora manda {texto, vence_em}", async () => {
  const chamadas = apiFalsa({ atividades: LISTA });
  montar();
  fireEvent.change(await screen.findByLabelText("Nova atividade"), { target: { value: "ligar pro dentista" } });
  fireEvent.change(screen.getByLabelText("Data (opcional)"), { target: { value: "2026-10-30" } });
  fireEvent.change(screen.getByLabelText("Hora (opcional)"), { target: { value: "10:00" } });
  fireEvent.click(screen.getByRole("button", { name: "Adicionar" }));
  await waitFor(() => expect(achar(chamadas, "POST", "/api/v1/atividades")).toBeTruthy());
  expect(achar(chamadas, "POST", "/api/v1/atividades")!.corpo).toEqual({ texto: "ligar pro dentista", vence_em: "2026-10-30T10:00" });
});

test("criar sem data manda só o texto", async () => {
  const chamadas = apiFalsa({ atividades: LISTA });
  montar();
  fireEvent.change(await screen.findByLabelText("Nova atividade"), { target: { value: "comprar pilhas" } });
  fireEvent.click(screen.getByRole("button", { name: "Adicionar" }));
  await waitFor(() => expect(achar(chamadas, "POST", "/api/v1/atividades")).toBeTruthy());
  expect(achar(chamadas, "POST", "/api/v1/atividades")!.corpo).toEqual({ texto: "comprar pilhas" });
});

test("Feita chama POST /atividades/{id}/concluir", async () => {
  const chamadas = apiFalsa({ atividades: LISTA });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Feita: ligar pro contador" }));
  await waitFor(() => expect(achar(chamadas, "POST", "/api/v1/atividades/2/concluir")).toBeTruthy());
});

test("Adiar para amanhã chama PATCH com o dia seguinte", async () => {
  const chamadas = apiFalsa({ atividades: LISTA });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Adiar: pagar o IPTU" }));
  fireEvent.click(screen.getByRole("button", { name: "Amanhã" }));
  await waitFor(() => expect(achar(chamadas, "PATCH", "/api/v1/atividades/1")).toBeTruthy());
  expect(achar(chamadas, "PATCH", "/api/v1/atividades/1")!.corpo).toEqual({ vence_em: "2026-10-28" });
});

test("Excluir só chama /cancelar depois de confirmar", async () => {
  const chamadas = apiFalsa({ atividades: LISTA });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Excluir: renovar o seguro" }));
  expect(achar(chamadas, "POST", "/cancelar")).toBeFalsy();
  fireEvent.click(screen.getByRole("button", { name: "Confirmar excluir renovar o seguro" }));
  await waitFor(() => expect(achar(chamadas, "POST", "/api/v1/atividades/3/cancelar")).toBeTruthy());
});

test("o menu Dia tem a área Atividades, com tela registrada", () => {
  const dia = GRUPOS.find((g) => g.titulo === "Dia")!;
  expect(dia.areas.map((a) => a.id)).toEqual(["hoje", "envios", "atividades", "projetos"]);
  expect(dia.areas[2].abas).toEqual([["atividades", "Atividades", "O que tenho para fazer?"]]);
  expect("atividades" in TELAS).toBe(true);
});
