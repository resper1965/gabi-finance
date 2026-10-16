import { vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Qualidade } from "../src/telas/Gabi/Qualidade";
import { apiFalsa, amostra } from "./apiFalsa";

beforeEach(() => { window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

test("mostra aceite, custo por tarefa e latência", async () => {
  apiFalsa();
  render(<Qualidade />);
  expect(await screen.findByText("Aceite das sugestões")).toBeTruthy();
  expect(screen.getByText("80%")).toBeTruthy();                 // taxa geral 0,804
  expect(screen.getByText("84%")).toBeTruthy();                 // categoria
  expect(screen.getByText("classificar")).toBeTruthy();
  expect(screen.getByText("US$ 1,14")).toBeTruthy();
  expect(screen.getByText("agenda_financeira")).toBeTruthy();
  expect(screen.getByText("260 ms")).toBeTruthy();
});

test("sem dados no período mostra frases vazias e traço no aceite", async () => {
  const base = amostra("qualidade");
  apiFalsa({ qualidade: { ...base, dados: { aceite: { janela_dias: 90, sugestoes: [], taxa_aceite_geral: null, perguntas: { respondidas: 0, expiradas: 0, abertas: 0 } },
    custo: { janela_dias: 30, tarefas: [], total_usd: 0 }, latencia: { janela_dias: 7, ferramentas: [] } } } });
  render(<Qualidade />);
  expect(await screen.findByText("Nenhuma sugestão no período.")).toBeTruthy();
  expect(screen.getByText("Nenhuma chamada ao modelo no período.")).toBeTruthy();
  expect(screen.getByText("Nenhuma chamada no período.")).toBeTruthy();
  expect(screen.getAllByText("—").length).toBeGreaterThan(0);
});
