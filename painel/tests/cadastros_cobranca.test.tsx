import { vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { CadastrosCobranca } from "../src/telas/CadastrosCobranca";
import { amostra, apiFalsa } from "./apiFalsa";

const montar = (ui: React.ReactElement) => render(<ToastProvider><FiltrosProvider>{ui}</FiltrosProvider></ToastProvider>);
beforeEach(() => { localStorage.clear(); window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

const env = (nome: string, dados: object) => ({ ...amostra(nome), dados });
const empresas = () => env("cadastros-empresas", { itens: [{ id: "ness", nome: "Ness", cnpj: null, dados: { relacao: "contratante", obs: "x" }, origem: "manual", excluido_em: null }] });
const pessoas = () => env("cadastros-pessoas", { itens: [{ id: "ana", nome: "Ana", papel: null, telefone: null, dados: { canais: ["whatsapp:+5511911110000"], pode_pedir: false }, origem: "manual", excluido_em: null }] });
const categorias = () => env("cadastros-categorias", { itens: [{ id: 1, nome: "Software", pai_id: null, nibo_category_id: null, excluido_em: null }] });

test("Cadastros da cobranca: salvar a empresa envia relacao e e-mail sem perder os outros dados", async () => {
  const chamadas = apiFalsa({ "cadastros-empresas": empresas(), "cadastros-pessoas": pessoas(), "cadastros-categorias": categorias() });
  montar(<CadastrosCobranca />);
  const bloco = await screen.findByRole("region", { name: "Empresas" });
  fireEvent.change(within(bloco).getByLabelText("Relação de Ness"), { target: { value: "contratante" } });
  fireEvent.change(within(bloco).getByLabelText("E-mail de cobrança de Ness"), { target: { value: "fin@ness.com.br" } });
  fireEvent.click(within(bloco).getByRole("button", { name: "Salvar Ness" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "PATCH" && /cadastros\/empresas\/ness$/.test(c.url))).toBe(true));
  expect(chamadas.find((c) => c.metodo === "PATCH")!.corpo).toEqual({ dados: { relacao: "contratante", obs: "x", email_cobranca: "fin@ness.com.br" } });
});

test("Cadastros da cobranca: salvar os canais de uma pessoa", async () => {
  const chamadas = apiFalsa({ "cadastros-empresas": empresas(), "cadastros-pessoas": pessoas(), "cadastros-categorias": categorias() });
  montar(<CadastrosCobranca />);
  const bloco = await screen.findByRole("region", { name: "Canais de cada pessoa" });
  fireEvent.change(within(bloco).getByLabelText("Canais de Ana"), { target: { value: "whatsapp:+5511911110000, telegram:@ana" } });
  fireEvent.click(within(bloco).getByRole("button", { name: "Salvar Ana" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "PATCH" && /cadastros\/pessoas\/ana$/.test(c.url))).toBe(true));
  expect((chamadas.find((c) => c.metodo === "PATCH")!.corpo as { dados: { canais: string[] } }).dados.canais).toEqual(["whatsapp:+5511911110000", "telegram:@ana"]);
});

test("Cadastros da cobranca: categoria recebe o id equivalente no Nibo", async () => {
  const chamadas = apiFalsa({ "cadastros-empresas": empresas(), "cadastros-pessoas": pessoas(), "cadastros-categorias": categorias() });
  montar(<CadastrosCobranca />);
  const bloco = await screen.findByRole("region", { name: "Categorias no Nibo" });
  fireEvent.change(within(bloco).getByLabelText("Id no Nibo de Software"), { target: { value: "cat-sw" } });
  fireEvent.click(within(bloco).getByRole("button", { name: "Salvar Software" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "PATCH" && /cadastros\/categorias\/1$/.test(c.url))).toBe(true));
  expect(chamadas.find((c) => c.metodo === "PATCH")!.corpo).toEqual({ nibo_category_id: "cat-sw" });
});

test("Cadastros da cobranca: define o socio do Nibo", async () => {
  const chamadas = apiFalsa({ "cadastros-empresas": empresas(), "cadastros-pessoas": pessoas(), "cadastros-categorias": categorias(),
    "cadastros-nibo": env("cadastros-nibo", { socio_id: null }) });
  montar(<CadastrosCobranca />);
  const nibo = await screen.findByRole("region", { name: "Nibo" });
  fireEvent.change(within(nibo).getByLabelText("Id do sócio no Nibo"), { target: { value: "socio-1" } });
  fireEvent.click(within(nibo).getByRole("button", { name: "Salvar sócio" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "PUT" || (c.metodo === "POST" && /cadastros\/nibo$/.test(c.url)))).toBe(true));
});
