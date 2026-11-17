import { vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { Lancamentos } from "../src/telas/Gastos/Lancamentos";
import { Assinaturas } from "../src/telas/Gastos/Assinaturas";
import { amostra, apiFalsa } from "./apiFalsa";

const montar = (ui: React.ReactElement) => render(<ToastProvider><FiltrosProvider>{ui}</FiltrosProvider></ToastProvider>);
beforeEach(() => { localStorage.clear(); window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

const comLanc = (gasto: object) => {
  const base = amostra("lancamentos-pendentes");
  return { ...base, dados: { ...base.dados, itens: [{ ...base.dados.itens[0], valor: "-1863.62", estabelecimento: "PAGAMENTO DE BOLETO ITAU", gasto }] } };
};

test("boleto de fatura mostra por que nao e gasto e deixa marcar como gasto", async () => {
  const chamadas = apiFalsa({ "lancamentos-pendentes": comLanc({ valor: false, origem: "fatura" }) });
  montar(<Lancamentos />);
  expect(await screen.findByText("não é gasto (paga fatura de cartão)")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "é gasto" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "PATCH" && JSON.stringify(c.corpo) === JSON.stringify({ gasto: true }))).toBe(true));
});

test("marcacao sua pode voltar para a Gabi decidir", async () => {
  const chamadas = apiFalsa({ "lancamentos-pendentes": comLanc({ valor: true, origem: "voce" }) });
  montar(<Lancamentos />);
  fireEvent.click(await screen.findByRole("button", { name: "deixar a Gabi decidir" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "PATCH" && JSON.stringify(c.corpo) === JSON.stringify({ gasto: null }))).toBe(true));
});

test("assinatura marcada como nao e assinatura some do rol e aparece no filtro do status", async () => {
  const base = amostra("assinaturas");
  const item = base.dados.itens[0];
  apiFalsa({ assinaturas: { ...base, dados: { ...base.dados, total_mensal: "0.00", itens: [{ ...item, status: "nao_assinatura", no_rol: false }] } } });
  montar(<Assinaturas />);
  expect(await screen.findByText("0 assinaturas ativas")).toBeTruthy();
  expect(screen.queryAllByText(item.nome).length).toBe(0);
  fireEvent.click(screen.getByRole("button", { name: "não é assinatura" }));
  expect((await screen.findAllByText(item.nome)).length).toBeGreaterThan(0);
});
