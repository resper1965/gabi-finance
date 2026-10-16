import { vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Qualidade } from "../src/telas/Gabi/Qualidade";
import { apiFalsa, amostra } from "./apiFalsa";

// dados de exemplo escritos aqui: a amostra do gerador vem do banco demo, que quase não tem histórico
const CHEIO = { ...amostra("qualidade"), dados: {"aceite": {"janela_dias": 90, "sugestoes": [{"tipo": "categoria", "aprovadas": 42, "rejeitadas": 8, "pendentes": 5, "taxa_aceite": 0.84}, {"tipo": "regra", "aprovadas": 3, "rejeitadas": 3, "pendentes": 0, "taxa_aceite": 0.5}], "taxa_aceite_geral": 0.804, "perguntas": {"respondidas": 4, "expiradas": 1, "abertas": 2}}, "custo": {"janela_dias": 30, "tarefas": [{"tarefa": "classificar", "chamadas": 120, "total_usd": 0.84, "medio_usd": 0.007}, {"tarefa": "escuta", "chamadas": 30, "total_usd": 0.3, "medio_usd": 0.01}], "total_usd": 1.14}, "latencia": {"janela_dias": 7, "ferramentas": [{"ferramenta": "agenda_financeira", "chamadas": 12, "erros": 0, "mediana_ms": 110, "p95_ms": 260}, {"ferramenta": "financeiro_saldo", "chamadas": 8, "erros": 1, "mediana_ms": 50, "p95_ms": 90}]}} };

beforeEach(() => { window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

test("mostra aceite, custo por tarefa e latência", async () => {
  apiFalsa({ qualidade: CHEIO });
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
