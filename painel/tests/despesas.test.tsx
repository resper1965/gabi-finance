import { vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { APagar } from "../src/telas/Caixa/APagar";
import { CadastrosDespesas } from "../src/telas/CadastrosDespesas";
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

test("encerrar chama POST /despesas/{linha}/encerrar depois de confirmar; o toast só avisa, sem Desfazer", async () => {
  const chamadas = apiFalsa();
  montar();
  await acoes("Aluguel");
  fireEvent.click(screen.getByRole("menuitem", { name: "Encerrar" }));
  expect(achar(chamadas, "POST", "/encerrar")).toBeFalsy();
  fireEvent.click(screen.getByRole("button", { name: "Confirmar encerrar Aluguel" }));
  await waitFor(() => expect(achar(chamadas, "POST", "/api/v1/despesas/aluguel/encerrar")).toBeTruthy());
  const toast = await waitFor(() => { const t = document.querySelector("[data-toast]") as HTMLElement; expect(t).not.toBeNull(); return t; });
  expect(toast).toHaveTextContent("Aluguel encerrada");
  expect(within(toast).queryByRole("button")).toBeNull();
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

// Cadastros › Despesas
const montarCadastro = () => render(<ToastProvider><CadastrosDespesas /></ToastProvider>);
const toastCom = async (texto: string) => waitFor(() => expect(document.querySelector("[data-toast]")).toHaveTextContent(texto));

test("Cadastros › Despesas: as abas Fixas, Avulsas e Encerradas filtram a lista", async () => {
  apiFalsa();
  montarCadastro();
  expect(await screen.findByText("Aluguel")).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: /Fixas/, selected: true })).toBeInTheDocument();
  expect(screen.queryByText("Dentista")).toBeNull();
  expect(screen.queryByText("Academia")).toBeNull();
  fireEvent.click(screen.getByRole("tab", { name: /Avulsas/ }));
  expect(screen.getByText("Dentista")).toBeInTheDocument();
  expect(screen.queryByText("Aluguel")).toBeNull();
  fireEvent.click(screen.getByRole("tab", { name: /Encerradas/ }));
  expect(screen.getByText("Academia")).toBeInTheDocument();
  expect(screen.queryByText("Aluguel")).toBeNull();
  expect(screen.queryByRole("button", { name: /Encerrar Academia|Excluir Academia|Editar Academia/ })).toBeNull();
});

test("Cadastros › Despesas: excluir pede confirmação; se já teve pagamento avisa que foi encerrada", async () => {
  const resp = { dados_ate: null, desatualizado: false, fontes: [], dados: { id: "aluguel", excluida: false, encerrada: true, ultimo_mes: "2026-09" } };
  const chamadas = apiFalsa({}, [[/\/despesas\/aluguel$/, resp]]);
  montarCadastro();
  fireEvent.click(await screen.findByRole("button", { name: "Excluir Aluguel" }));
  expect(achar(chamadas, "DELETE", "/api/v1/despesas/aluguel")).toBeFalsy();
  fireEvent.click(screen.getByRole("button", { name: "Confirmar excluir Aluguel" }));
  await waitFor(() => expect(achar(chamadas, "DELETE", "/api/v1/despesas/aluguel")).toBeTruthy());
  await toastCom("Já teve pagamento: foi encerrada, não excluída");
});

test("Cadastros › Despesas: excluir sem pagamento avisa que excluiu", async () => {
  const resp = { dados_ate: null, desatualizado: false, fontes: [], dados: { id: "luz", excluida: true, encerrada: false } };
  const chamadas = apiFalsa({}, [[/\/despesas\/luz$/, resp]]);
  montarCadastro();
  fireEvent.click(await screen.findByRole("button", { name: "Excluir Luz" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirmar excluir Luz" }));
  await waitFor(() => expect(achar(chamadas, "DELETE", "/api/v1/despesas/luz")).toBeTruthy());
  await toastCom("Luz excluída");
});

test("Cadastros › Despesas: encerrar confirma e chama POST /encerrar; editar manda PATCH", async () => {
  const chamadas = apiFalsa();
  montarCadastro();
  fireEvent.click(await screen.findByRole("button", { name: "Encerrar Internet" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirmar encerrar Internet" }));
  await waitFor(() => expect(achar(chamadas, "POST", "/api/v1/despesas/internet/encerrar")).toBeTruthy());
  fireEvent.click(screen.getByRole("button", { name: "Editar Escola" }));
  fireEvent.change(screen.getByLabelText("Dia do vencimento"), { target: { value: "12" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(achar(chamadas, "PATCH", "/api/v1/despesas/escola")).toBeTruthy());
  expect(achar(chamadas, "PATCH", "/api/v1/despesas/escola")!.corpo).toEqual({ vencimento: "dia:12" });
});

test("atrasada de mês passado não oferece Editar/Dispensar este mês (só Mudar daqui em diante e Encerrar)", async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-26T12:00:00-03:00"));
  try {
    const env = amostra("contas-pagar");
    const velha = { ...env.dados.atrasadas[0], id: "aluguel:2026-09", mes: "2026-09", vencimento: "2026-09-05", vencimento_util: "2026-09-05" };
    apiFalsa({ "contas-pagar": { ...env, dados: { ...env.dados, atrasadas: [velha] } } });
    montar();
    await acoes("Aluguel");
    const itens = screen.getAllByRole("menuitem").map((b) => b.textContent);
    expect(itens).toEqual(["Mudar daqui em diante", "Encerrar"]);
    fireEvent.click(await screen.findByRole("button", { name: "Ações de Escola" }));
    expect(screen.getAllByRole("menuitem", { name: "Dispensar este mês" }).length).toBeGreaterThan(0);  // mês em curso continua com tudo
  } finally {
    vi.useRealTimers();
  }
});
