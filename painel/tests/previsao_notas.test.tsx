import { vi } from "vitest";
import { render, screen, within, fireEvent, waitFor } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { Projecao } from "../src/telas/Caixa/Projecao";
import { NotasAReceber } from "../src/telas/Cobrar/NotasAReceber";
import { amostra, apiFalsa } from "./apiFalsa";

const montar = (ui: React.ReactElement) => render(<ToastProvider><FiltrosProvider>{ui}</FiltrosProvider></ToastProvider>);
beforeEach(() => { localStorage.clear(); window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

const env = (dados: object) => ({ ...amostra("contagens"), dados });
const bloco = (qtd: number, liquido: string) => ({ qtd, liquido, bruto: liquido, notas: [] });

const projecao = () => env({
  saldo_inicial: "21499.47", aviso: "Entradas só de notas ainda não vencidas e contratos recorrentes; o Nibo é defasado.",
  menor_saldo: { dia: "2026-10-09", saldo: "16218.92" },
  dias: [{ dia: "2026-10-09", entradas: "0.00", saidas: "5280.55", saldo: "16218.92" }, { dia: "2026-10-10", entradas: "0.00", saidas: "0.00", saldo: "16218.92" },
         { dia: "2026-10-25", entradas: "29715.25", saidas: "1500.00", saldo: "44434.17" }] });
const previsao = () => env({ hoje: "2026-10-09", aviso: "Nibo defasado", meses: [],
  a_confirmar: bloco(9, "69230.61"), antigas: bloco(146, "1061216.49") });

test("Previsao mostra o saldo por dia (so os dias com movimento) e separa a fila de conferencia", async () => {
  apiFalsa({ "caixa-projecao": projecao(), "cobrar-previsao": previsao() });
  montar(<Projecao />);
  expect(await screen.findByText("Saldo hoje")).toBeInTheDocument();
  expect(screen.getByText("Menor saldo")).toBeInTheDocument();
  const tabela = screen.getByRole("table", { name: "Saldo projetado por dia" });
  const linhas = within(tabela).getAllByRole("row");
  expect(linhas.length).toBe(1 + 2)                      // cabeçalho + os 2 dias com movimento (10/10 não tem)
  expect(within(tabela).getByText("25/10")).toBeInTheDocument();
  const fila = await screen.findByRole("region", { name: "Fila de conferência com o extrato" });
  expect(within(fila).getByText(/9 notas vencidas/)).toBeInTheDocument();
  expect(within(fila).getByText(/146 notas antigas/)).toBeInTheDocument();
  expect(screen.getByText(/Nibo é defasado/)).toBeInTheDocument();
});

const nota = (n: string, tomador: string, venc: string, liquido: string, situacao: string) => ({ numero: n, tomador, emissao: "2026-10-01", vencimento: venc, bruto: liquido, liquido, situacao, nibo_pago: situacao === "nibo_diz_pago", pdf: true, xml: true });
const notas = () => env({ totais: { a_vencer: "22261.22", a_confirmar: "3660.15", antigas: "1000.00", nibo_diz_pago: "500.00", recebidas: "0.00" }, itens: [
  nota("201", "IONIC HEALTH", "2026-10-25", "22261.22", "a_vencer"), nota("150", "BARRA DO PARA", "2026-09-20", "3660.15", "a_confirmar"),
  nota("90", "ANTIGA LTDA", "2026-05-10", "1000.00", "antiga"), nota("205", "JA PAGA SA", "2026-10-30", "500.00", "nibo_diz_pago")] });

test("Notas a receber marca 'Nibo diz pago' sem trata-lo como recebido e agrupa pela situacao", async () => {
  apiFalsa({ "cobrar-notas": notas() });
  montar(<NotasAReceber />);
  expect(await screen.findByText("IONIC HEALTH")).toBeInTheDocument();
  const paga = screen.getByText("JA PAGA SA").closest("tr")!;
  expect(within(paga).getByText("Nibo diz pago")).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "A receber" })).toHaveTextContent("22.261,22");        // total a vencer não inclui a "paga"
  expect(screen.getByRole("region", { name: "A receber" })).not.toHaveTextContent("500,00");
  expect(screen.getByText(/confirmar pelo extrato/i)).toBeInTheDocument();
});


const proposta = () => env({ itens: [{ id: 5, confianca: 1, motivo: "valor igual ao líquido da nota, tomador no descritivo",
  nota: { numero: "150", tomador: "BARRA DO PARA", vencimento: "2026-10-15", liquido: "3660.15" },
  lancamento: { id: 9, data: "2026-10-16", descricao: "Pix recebido BARRA DO PARA", valor: "3660.15" } }] });

test("Notas a receber lista recebimentos propostos e confirma ou rejeita so por clique do Ricardo", async () => {
  const chamadas = apiFalsa({ "cobrar-notas": notas(), "cobrar-recebimentos": proposta() });
  montar(<NotasAReceber />);
  const caixa = await screen.findByRole("region", { name: "Recebimentos propostos" });
  expect(within(caixa).getByText(/Pix recebido BARRA DO PARA/)).toBeInTheDocument();
  expect(within(caixa).getByText(/valor igual ao líquido/)).toBeInTheDocument();
  fireEvent.click(within(caixa).getByRole("button", { name: "Confirmar recebimento da nota 150" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /recebimentos\/5\/confirmar$/.test(c.url))).toBe(true));
  fireEvent.click(within(caixa).getByRole("button", { name: "Rejeitar recebimento da nota 150" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /recebimentos\/5\/rejeitar$/.test(c.url))).toBe(true));
});
