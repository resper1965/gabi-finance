import { vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { APagar } from "../src/telas/Caixa/APagar";
import { amostra, apiFalsa, type Chamada } from "./apiFalsa";

const montar = () => render(<ToastProvider><APagar /></ToastProvider>);
afterEach(() => { vi.unstubAllGlobals(); });

const acoes = async (nome: string) => fireEvent.click(await screen.findByRole("button", { name: `Ações de ${nome}` }));
/** Botão "Desfazer" do toast (a tela tem outros role=status). */
const desfazer = async () => { await waitFor(() => expect(document.querySelector("[data-toast]")).not.toBeNull()); return within(document.querySelector("[data-toast]") as HTMLElement).getByRole("button", { name: "Desfazer" }); };
const achar = (chamadas: Chamada[], metodo: string, url: string) => chamadas.find((c) => c.metodo === metodo && c.url.endsWith(url));

test("dispensar chama POST /despesas/{linha}/mes/{mes}/dispensar e o Desfazer chama DELETE", async () => {
  const chamadas = apiFalsa();
  montar();
  await acoes("Escola");
  fireEvent.click(screen.getByRole("menuitem", { name: "Dispensar este mês" }));
  await waitFor(() => expect(achar(chamadas, "POST", "/api/v1/despesas/escola/mes/2026-10/dispensar")).toBeTruthy());
  fireEvent.click(await desfazer());
  await waitFor(() => expect(achar(chamadas, "DELETE", "/api/v1/despesas/escola/mes/2026-10/dispensar")).toBeTruthy());
});

test("encerrar chama POST /despesas/{linha}/encerrar depois de confirmar; o Desfazer só aponta Cadastros › Despesas", async () => {
  const chamadas = apiFalsa();
  montar();
  await acoes("Aluguel");
  fireEvent.click(screen.getByRole("menuitem", { name: "Encerrar" }));
  expect(achar(chamadas, "POST", "/encerrar")).toBeFalsy();
  fireEvent.click(screen.getByRole("button", { name: "Confirmar encerrar Aluguel" }));
  await waitFor(() => expect(achar(chamadas, "POST", "/api/v1/despesas/aluguel/encerrar")).toBeTruthy());
  fireEvent.click(await desfazer());
  expect(await screen.findByText(/Cadastros › Despesas/)).toBeInTheDocument();
  expect(chamadas.filter((c) => c.metodo !== "GET")).toHaveLength(1);
});

test("mudar daqui em diante manda valor_padrao e a_partir", async () => {
  const chamadas = apiFalsa();
  montar();
  await acoes("Escola");
  fireEvent.click(screen.getByRole("menuitem", { name: "Mudar daqui em diante" }));
  fireEvent.change(screen.getByLabelText("Valor"), { target: { value: "2.350,50" } });
  fireEvent.change(screen.getByLabelText("A partir de (opcional)"), { target: { value: "2026-11" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(achar(chamadas, "PATCH", "/api/v1/despesas/escola")).toBeTruthy());
  expect(achar(chamadas, "PATCH", "/api/v1/despesas/escola")!.corpo).toEqual({ valor_padrao: "2350.50", a_partir: "2026-11" });
});

test("+ despesa avulsa manda tipo e data", async () => {
  const chamadas = apiFalsa();
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "+ despesa" }));
  fireEvent.click(screen.getByRole("radio", { name: "Avulsa" }));
  fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Conserto do portão" } });
  fireEvent.change(screen.getByLabelText("Valor"), { target: { value: "800" } });
  fireEvent.change(screen.getByLabelText("Data"), { target: { value: "2026-11-15" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(achar(chamadas, "POST", "/api/v1/despesas")).toBeTruthy());
  expect(achar(chamadas, "POST", "/api/v1/despesas")!.corpo).toEqual({ tipo: "avulsa", nome: "Conserto do portão", valor_padrao: "800.00", data: "2026-11-15", forma: "pix" });
});

test("fatura não tem menu de ações", async () => {
  const base = amostra("contas-pagar");
  const fatura = { ...base.dados.proximas[0], id: "fatura:nubank:2026-10", nome: "Fatura Nubank", forma: "fatura", linha_id: null, mes: null, tipo: null };
  apiFalsa({ "contas-pagar": { ...base, dados: { ...base.dados, proximas: [...base.dados.proximas, fatura] } } });
  montar();
  await screen.findByText("Fatura Nubank");
  expect(screen.getByRole("button", { name: "Ações de Escola" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Ações de Fatura Nubank" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Ações de Luz" })).toBeNull();
});
