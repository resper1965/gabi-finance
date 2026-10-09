import { vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { Pedidos } from "../src/telas/Caixa/Pedidos";
import { Reembolsos } from "../src/telas/Cobrar/Reembolsos";
import { Comprovantes } from "../src/telas/Cobrar/Comprovantes";
import { EmailCobranca } from "../src/telas/Cobrar/EmailCobranca";
import { amostra, apiFalsa } from "./apiFalsa";

const montar = (ui: React.ReactElement) => render(<ToastProvider><FiltrosProvider>{ui}</FiltrosProvider></ToastProvider>);
beforeEach(() => { localStorage.clear(); window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

const env = (nome: string, dados: object) => ({ ...amostra(nome), dados });
const TEXTO_LOTE = "Lançar no Nibo da Bekaa: 1 despesas, R$ 70,00.";
const reembolsos = () => env("cobrar-reembolsos", {
  empresas: [{ empresa_id: "ness", nome: "Ness", em_aberto: "150.00", reembolsos: [],
    itens: [{ lancamento_id: 1, data: "2026-10-01", descricao: "HOTEL", valor: "100.00", em_aberto: "100.00", comprovante: "confirmado" },
            { lancamento_id: 2, data: "2026-10-02", descricao: "TAXI", valor: "50.00", em_aberto: "50.00", comprovante: "faltando" }] }],
  lote: { id: null, texto_confirmacao: TEXTO_LOTE, itens: [{ lancamento_id: 3, data: "2026-10-03", descricao: "LICENCA", valor: "70.00" }] },
});

test("Reembolsos: a Bekaa mostra o lote do Nibo e nao a cobranca", async () => {
  apiFalsa({ "cobrar-reembolsos": reembolsos() });
  montar(<Reembolsos />);
  await screen.findByRole("tab", { name: /Ness/ });
  fireEvent.click(screen.getByRole("tab", { name: /Bekaa/ }));
  expect(await screen.findByRole("button", { name: /Lote de hoje → Nibo/ })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Preparar e-mail/ })).toBeNull();
  expect(screen.getByText("LICENCA")).toBeInTheDocument();
});

test("Reembolsos: o lote envia a confirmacao IGUAL ao texto do servidor", async () => {
  const chamadas = apiFalsa({ "cobrar-reembolsos": reembolsos() }, [
    [/lote\/montar$/, env("cobrar-reembolsos", { id: 9, texto_confirmacao: TEXTO_LOTE, itens: [] })],
    [/lote\/9\/executar$/, env("cobrar-reembolsos", { ok: 1, erro: 0 })],
  ]);
  montar(<Reembolsos />);
  fireEvent.click(await screen.findByRole("tab", { name: /Bekaa/ }));
  fireEvent.click(await screen.findByRole("button", { name: /Lote de hoje → Nibo/ }));
  const dialogo = await screen.findByRole("dialog");
  expect(within(dialogo).getByText(TEXTO_LOTE)).toBeInTheDocument();
  fireEvent.click(within(dialogo).getByRole("button", { name: /Confirmar e gravar no Nibo/ }));
  await waitFor(() => expect(chamadas.some((c) => /lote\/9\/executar$/.test(c.url))).toBe(true));
  expect(chamadas.find((c) => /lote\/9\/executar$/.test(c.url))!.corpo).toEqual({ confirmacao: TEXTO_LOTE });
});

test("Reembolsos: preparar e-mail de uma empresa contratante chama a montagem do rascunho", async () => {
  const chamadas = apiFalsa({ "cobrar-reembolsos": reembolsos() });
  montar(<Reembolsos />);
  fireEvent.click(await screen.findByRole("button", { name: /Preparar e-mail com todos os itens/ }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /cobrar\/cobrancas$/.test(c.url))).toBe(true));
  expect(chamadas.find((c) => c.metodo === "POST")!.corpo).toEqual({ empresa_id: "ness" });
});

const pedidos = () => env("cobrar-pedidos", { itens: [{ id: 7, solicitante: "Ana", canal: "whatsapp", descricao: "Dentista", valor: "150.00", vencimento: "2026-10-20", pix_chave: "d@pix",
  anexo_paperless_id: null, estado: "pendente", mensagem_original: "paga o dentista?", criado_em: "2026-10-09T10:00:00", decidido_em: null }] });

test("Pedidos: aprovar pede a conta e o beneficiario antes de chamar a API", async () => {
  const chamadas = apiFalsa({ "cobrar-pedidos": pedidos() });
  montar(<Pedidos />);
  fireEvent.click(await screen.findByRole("button", { name: "Aprovar e pôr na fila" }));
  expect(chamadas.some((c) => c.metodo === "POST")).toBe(false);          // sem conta e beneficiário, nada vai
  expect(await screen.findByText(/Escolha a conta e o beneficiário/)).toBeInTheDocument();
});

test("Pedidos: aprovar com conta e beneficiario envia a decisao", async () => {
  const chamadas = apiFalsa({ "cobrar-pedidos": pedidos() });
  montar(<Pedidos />);
  fireEvent.change(await screen.findByRole("combobox", { name: /Sai de/ }), { target: { value: "1" } });
  fireEvent.change(screen.getByRole("combobox", { name: /Para quem/ }), { target: { value: "p-hel" } });
  fireEvent.click(screen.getByRole("button", { name: "Aprovar e pôr na fila" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /pedidos\/7\/decidir$/.test(c.url))).toBe(true));
  expect(chamadas.find((c) => c.metodo === "POST")!.corpo).toEqual({ acao: "aprovar", conta_id: 1, beneficiario_id: "p-hel" });
});

test("Pedidos: recusar e pedir mais informacao chamam a API sem exigir conta", async () => {
  const chamadas = apiFalsa({ "cobrar-pedidos": pedidos() });
  montar(<Pedidos />);
  fireEvent.click(await screen.findByRole("button", { name: "Recusar" }));
  await waitFor(() => expect(chamadas.find((c) => c.metodo === "POST")?.corpo).toEqual({ acao: "recusar" }));
});

const comprovantes = () => env("cobrar-comprovantes", {
  candidatos: [{ vinculo_id: 4, confianca: 0.8, motivo: "valor igual R$ 100,00, data exata",
    comprovante: { paperless_id: 77, tipo: "comprovante_pix", valor: "100.00", data: "2026-10-01" },
    lancamento: { id: 1, data: "2026-10-01", descricao: "HOTEL", valor: "100.00", empresa: "ness" } }],
  sem_comprovante: [{ id: 2, data: "2026-10-02", descricao: "TAXI", valor: "50.00", empresa_id: "ness" }],
});

test("Comprovantes: confirma o vinculo proposto e lista o que ainda esta sem comprovante", async () => {
  const chamadas = apiFalsa({ "cobrar-comprovantes": comprovantes() });
  montar(<Comprovantes />);
  expect(await screen.findByText(/Confirme o vínculo · 1/)).toBeInTheDocument();
  expect(screen.getByText("TAXI")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Confirmar vínculo" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /vinculos\/4\/confirmar$/.test(c.url))).toBe(true));
});

const cobrancas = () => env("cobrar-cobrancas", { itens: [{ id: 3, empresa_id: "ness", para: "fin@ness.com.br", assunto: "Reembolso de despesas — Ness — 10/2026", criado_em: "2026-10-09T10:00:00", itens: 2 }] });

test("EmailCobranca: o botao enviar fica desabilitado e diz o motivo", async () => {
  apiFalsa({ "cobrar-cobrancas": cobrancas() });
  montar(<EmailCobranca />);
  const enviar = await screen.findByRole("button", { name: /Enviar/ });
  expect(enviar).toBeDisabled();
  expect(screen.getByText(/O envio está desabilitado/)).toBeInTheDocument();
  expect(screen.getByText(/Reembolso de despesas — Ness — 10\/2026/)).toBeInTheDocument();
});

test("Reembolsos: marcar como cobrado abre a cobranca e a marca como cobrada", async () => {
  const chamadas = apiFalsa({ "cobrar-reembolsos": reembolsos() }, [[/cobrar\/reembolsos$/, env("cobrar-reembolsos", { id: 5 })]]);
  montar(<Reembolsos />);
  fireEvent.click(await screen.findByRole("button", { name: "Marcar como cobrado" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /reembolsos\/5\/cobrado$/.test(c.url))).toBe(true));
  expect(chamadas.find((c) => c.metodo === "POST" && /cobrar\/reembolsos$/.test(c.url))!.corpo).toEqual({ empresa_id: "ness" });
});

test("Reembolsos: marcar como cobrado cobra so os itens selecionados", async () => {
  const chamadas = apiFalsa({ "cobrar-reembolsos": reembolsos() }, [[/cobrar\/reembolsos$/, env("cobrar-reembolsos", { id: 6 })]]);
  montar(<Reembolsos />);
  fireEvent.click(await screen.findByRole("checkbox", { name: "Selecionar TAXI" }));
  fireEvent.click(screen.getByRole("button", { name: "Marcar como cobrado (1)" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /reembolsos\/6\/cobrado$/.test(c.url))).toBe(true));
  expect(chamadas.find((c) => c.metodo === "POST" && /cobrar\/reembolsos$/.test(c.url))!.corpo).toEqual({ empresa_id: "ness", itens: [2] });
});
