import { vi } from "vitest";
import { render, screen, within, fireEvent, waitFor } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { AReceber } from "../src/telas/Cobrar/AReceber";
import { amostra, apiFalsa } from "./apiFalsa";

const montar = (ui: React.ReactElement) => render(<ToastProvider><FiltrosProvider>{ui}</FiltrosProvider></ToastProvider>);
beforeEach(() => { localStorage.clear(); window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

const tot = { esperado: "0.00", recebido: "0.00", falta: "0.00", atrasado: "0.00" };
const manual = (o: object) => ({ id: 1, pagador: "X", situacao: "a_receber", esperado: "100.00", vencimento: null, conta: null, observacao: null, recebido_em: null, recebido: null, extrato: null, proposta: null, ...o });
const dados = () => ({ ...amostra("contagens"), dados: { mes: "2026-10", recorrentes: [], notas: [], totais: { recorrentes: tot, notas: tot, manuais: { esperado: "1200.00", recebido: "0.00", falta: "1200.00", atrasado: "0.00" } },
  manuais: [
    manual({ id: 7, pagador: "ORM Reis", situacao: "credito_provavel", esperado: "1500.00", vencimento: "2026-10-20", recebido: "1500.00", recebido_em: "2026-10-05",
             proposta: { id: 3, confianca: 1, motivo: "valor igual", data: "2026-10-05", descricao: "Pix ORM REIS LTDA", valor: "1500.00" } }),
    manual({ id: 8, pagador: "NESS", situacao: "a_receber", esperado: "-300.00", observacao: "adiantamento" })] } });

test("A receber lista os lancados pelo Ricardo e so confirma, rejeita ou cancela no clique", async () => {
  const chamadas = apiFalsa({ "cobrar-a-receber": dados() });
  montar(<AReceber />);
  const caixa = await screen.findByRole("region", { name: "Lançados por você" });
  expect(within(caixa).getByText("ORM Reis")).toBeInTheDocument();
  expect(within(caixa).getByText(/Crédito provável: confirme aqui/)).toBeInTheDocument();
  expect(within(caixa).getAllByText(/Pix ORM REIS LTDA/).length).toBeGreaterThan(0);
  expect(screen.getByText(/negativo nos lançados por você é desconto ou adiantamento/)).toBeInTheDocument();
  expect(chamadas.some((c) => c.metodo === "POST")).toBe(false);
  fireEvent.click(within(caixa).getByRole("button", { name: "Confirmar crédito de ORM Reis" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /a-receber-manual\/propostas\/3\/confirmar$/.test(c.url))).toBe(true));
  fireEvent.click(within(caixa).getByRole("button", { name: "Rejeitar crédito de ORM Reis" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /a-receber-manual\/propostas\/3\/rejeitar$/.test(c.url))).toBe(true));
  fireEvent.click(within(caixa).getByRole("button", { name: "Cancelar a receber de NESS" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /a-receber-manual\/8\/cancelar$/.test(c.url))).toBe(true));
  expect(within(caixa).queryByRole("button", { name: "Cancelar a receber de ORM Reis" })).toBeInTheDocument();
});
