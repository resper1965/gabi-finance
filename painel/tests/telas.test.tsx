import { vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { Lancamentos } from "../src/telas/Gastos/Lancamentos";
import { Semanas } from "../src/telas/Caixa/Semanas";
import { Regras } from "../src/telas/Regras";
import { Cartoes } from "../src/telas/Gastos/Cartoes";
import { CustoGabi } from "../src/componentes/CustoGabi";
import { ParaOndeVai } from "../src/telas/Gastos/ParaOndeVai";
import { Resumo } from "../src/telas/Caixa/Resumo";
import { APagar } from "../src/telas/Caixa/APagar";
import { Assinaturas } from "../src/telas/Gastos/Assinaturas";
import { amostra, apiFalsa } from "./apiFalsa";

const montar = (ui: React.ReactElement) => render(<ToastProvider><FiltrosProvider>{ui}</FiltrosProvider></ToastProvider>);
function celular(ativo: boolean) {
  window.matchMedia = ((q: string) => ({ matches: ativo && q.includes("759"), media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia;
}
beforeEach(() => { localStorage.clear(); celular(false); });
afterEach(() => { vi.unstubAllGlobals(); });

test("Lancamentos chip muda para quem e chama PATCH", async () => {
  const chamadas = apiFalsa();
  montar(<Lancamentos />);
  const grupo = await screen.findByRole("group", { name: /Para quem: FARMACIA/ });
  fireEvent.click(within(grupo).getByRole("button", { name: "Helena" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "PATCH" && /\/lancamentos\/5$/.test(c.url))).toBe(true));
  const c = chamadas.find((x) => x.metodo === "PATCH")!;
  expect(c.corpo).toEqual({ beneficiario_id: "p-hel" });
});

test("Lancamentos sugestao tem borda tracejada e origem", async () => {
  apiFalsa({
    sugestoes: { ...amostra("sugestoes"), dados: { itens: [{ id: 9, tipo: "para_quem", lancamento_id: 5, payload: { para_quem_id: "p-lia" }, estado: "pendente", motivo: "você classificou assim os outros", criado_em: "x", decidida_em: null, impacto: null }] } },
  });
  montar(<Lancamentos />);
  const grupo = await screen.findByRole("group", { name: /Para quem: FARMACIA/ });
  const lia = within(grupo).getByRole("button", { name: "Lia" });
  expect(lia.style.border).toContain("dashed");
  expect(await screen.findByText(/Gabi sugere: Lia/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "confirmar" })).toBeInTheDocument();
});

test("Semanas futuras tem opacidade 04", async () => {
  apiFalsa();
  const { container } = montar(<Semanas />);
  await screen.findByText("Entradas e saídas por semana");
  const futura = container.querySelector('g[data-projecao="true"] rect') as SVGRectElement;
  const real = container.querySelector('g[data-projecao="false"] rect') as SVGRectElement;
  expect(futura.style.fillOpacity).toBe("0.4");
  expect(futura.style.strokeDasharray).toBe("3 2");
  expect(real.style.fillOpacity).toBe("1");
});

test("Regras chave liga desliga chama PATCH", async () => {
  const chamadas = apiFalsa();
  montar(<Regras />);
  const chave = await screen.findByRole("switch", { name: /Regra UBER ligada/ });
  expect(chave).toHaveAttribute("aria-checked", "true");
  fireEvent.click(chave);
  await waitFor(() => expect(chamadas.find((c) => c.metodo === "PATCH")?.corpo).toEqual({ ativa: false }));
  expect(chamadas.find((c) => c.metodo === "PATCH")!.url).toBe("/api/v1/regras/1");
});

test("ParaOndeVai celular abre em Fornecedores", async () => {
  celular(true);
  apiFalsa();
  montar(<ParaOndeVai />);
  const aba = await screen.findByRole("button", { name: "Fornecedores" });
  expect(aba).toHaveAttribute("aria-pressed", "true");
  expect(await screen.findByText("maiores fornecedores do período")).toBeInTheDocument();
});

test("ParaOndeVai desktop abre em Sankey", async () => {
  apiFalsa();
  montar(<ParaOndeVai />);
  expect(await screen.findByRole("button", { name: "Sankey" })).toHaveAttribute("aria-pressed", "true");
});

test("Resumo mostra os 5 instrumentos e a atencao leva a tela certa", async () => {
  apiFalsa();
  montar(<Resumo />);
  for (const r of ["Saldo do caixa único", "A pagar em 7 dias", "A receber das empresas", "Fatura aberta · cartões", "Assinaturas por mês"]) expect((await screen.findAllByText(r)).length).toBeGreaterThan(0);
  expect(screen.getByText("1 conta atrasada")).toBeInTheDocument(); // singular correto
});

test("APagar: ja paguei chama POST e mostra pagas conciliadas", async () => {
  const chamadas = apiFalsa();
  montar(<APagar />);
  fireEvent.click((await screen.findAllByRole("button", { name: "Já paguei" }))[0]);
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /\/contas-pagar\/aluguel%3A2026-10\/paga$/.test(c.url))).toBe(true));
  expect(screen.getByText(/conciliadas com o extrato/)).toBeInTheDocument();
});

test("Assinaturas troca status por PATCH", async () => {
  const chamadas = apiFalsa();
  montar(<Assinaturas />);
  fireEvent.change(await screen.findByRole("combobox", { name: "Status de NETFLIX" }), { target: { value: "cancelar" } });
  await waitFor(() => expect(chamadas.find((c) => c.metodo === "PATCH")?.corpo).toEqual({ status: "cancelar" }));
});

test("erro de API mostra o estado de erro com os ultimos dados bons guardados", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 500, json: async () => ({ erro: "erro", mensagem: "falhou" }) }) as Response));
  montar(<Regras />);
  expect(await screen.findByText(/continuam guardados/)).toBeInTheDocument();
});

const sugestaoDeRegra = () => {
  const base = amostra("sugestoes");
  return { ...base, dados: { itens: [{ id: 7, tipo: "regra", lancamento_id: null, estado: "pendente", motivo: "UBER aparece 6 vezes",
    payload: { padrao: "UBER", acao: { categoria_id: 1 } }, impacto: { passado: 6, futuro_estimado: 2 }, criado_em: "2026-10-08T12:00:00", decidida_em: null }] } };
};

test("Regras: trocar a categoria da sugestao envia a edicao ao aprovar", async () => {
  const chamadas = apiFalsa({ sugestoes: sugestaoDeRegra() });
  montar(<Regras />);
  const seletor = await screen.findByRole("combobox", { name: /Categoria da sugestão UBER/ });
  fireEvent.change(seletor, { target: { value: "2" } });
  fireEvent.click(screen.getByRole("button", { name: "Aprovar e ligar" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /\/sugestoes\/7\/aprovar$/.test(c.url))).toBe(true));
  expect(chamadas.find((c) => c.metodo === "POST")!.corpo).toEqual({ edicao: { acao: { categoria_id: 2 } } });
});

test("Regras: sem trocar a categoria aprova sem edicao", async () => {
  const chamadas = apiFalsa({ sugestoes: sugestaoDeRegra() });
  montar(<Regras />);
  await screen.findByRole("combobox", { name: /Categoria da sugestão UBER/ });
  fireEvent.click(screen.getByRole("button", { name: "Aprovar e ligar" }));
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST")).toBe(true));
  expect((chamadas.find((c) => c.metodo === "POST")!.corpo as { edicao?: unknown }).edicao).toBeUndefined();
});

test("Cartoes: filtro Tipo 'Só assinatura' mostra so lancamentos de assinaturas detectadas", async () => {
  apiFalsa();
  montar(<Cartoes />);
  await screen.findByRole("combobox", { name: "Tipo" });
  await waitFor(() => expect(document.querySelectorAll("tbody tr").length).toBeGreaterThan(0));
  const antes = document.querySelectorAll("tbody tr").length;
  fireEvent.change(screen.getByRole("combobox", { name: "Tipo" }), { target: { value: "assinatura" } });
  await waitFor(() => expect(document.querySelectorAll("tbody tr").length).toBeLessThan(antes));
  const linhas = [...document.querySelectorAll("tbody tr")].map((l) => l.textContent ?? "");
  expect(linhas.length).toBeGreaterThan(0);
  expect(linhas.every((t) => /NETFLIX/.test(t))).toBe(true); // a amostra tem NETFLIX como assinatura; TV e LOJA saem
});

test("CustoGabi mostra em reais quando ha cambio e em dolar quando nao ha", async () => {
  const base = amostra("custo");
  apiFalsa({ custo: { ...base, dados: { ...base.dados, dia_usd: 0.5, mes_usd: 4, teto_dia_usd: 1, teto_mes_usd: 10, cambio_usd_brl: "5.50" } } });
  const { unmount } = montar(<CustoGabi />);
  expect(await screen.findByText(/R\$ 2,75 \/ R\$ 5,50/)).toBeInTheDocument(); // hoje: 0,5 × 5,5 = 2,75 de 1 × 5,5 = 5,50
  unmount();
  vi.unstubAllGlobals();
  apiFalsa({ custo: { ...base, dados: { ...base.dados, dia_usd: 0.5, teto_dia_usd: 1, cambio_usd_brl: null } } });
  montar(<CustoGabi />);
  expect(await screen.findByText(/US\$ 0,50 \/ US\$ 1,00/)).toBeInTheDocument();
});

const rodadas = () => {
  const base = amostra("rodadas");
  const r = (id: number, fim: string, conferida: boolean, reprovadas: object[]) => ({ id, fonte: "open-finance", inicio: fim, fim, status: "ok", lidos: 2280, novos: 12, alterados: 0, erro: null, conferida, reprovadas });
  return { ...base, dados: { itens: [
    r(21, "2026-10-09T18:10:00Z", false, [{ conta: "Itaú PF", tipo: "saldo_final", detalhe: "diferença de -401663 centavos" }]),
    r(20, "2026-10-09T10:10:00Z", true, []),
    { ...r(19, "2026-10-09T12:05:00Z", true, []), fonte: "open-finance-saldos" },
  ] } };
};

test("APagar mostra as ultimas rodadas de extrato com estado e conferida", async () => {
  apiFalsa({ rodadas: rodadas() });
  montar(<APagar />);
  const bloco = await screen.findByRole("region", { name: "Rodadas" });
  expect(within(bloco).getAllByRole("listitem")).toHaveLength(2); // a rodada de saldos fica de fora
  expect(within(bloco).getByText(/conferida/, { selector: "[data-estado='conferida']" })).toBeInTheDocument();
});

test("APagar: rodada nao conferida mostra o motivo", async () => {
  apiFalsa({ rodadas: rodadas() });
  montar(<APagar />);
  const bloco = await screen.findByRole("region", { name: "Rodadas" });
  expect(within(bloco).getByText(/Itaú PF/)).toBeInTheDocument();
  expect(within(bloco).getByText(/diferença de -401663 centavos/)).toBeInTheDocument();
});

test("Assinaturas mostra 'parou de cobrar' nas inativas e conta so as ativas", async () => {
  const base = amostra("assinaturas");
  const ativa = { ...base.dados.itens[0], ativa: true };
  const parou = { ...base.dados.itens[0], id: 99, nome: "SAAS ANTIGO", ativa: false };
  apiFalsa({ assinaturas: { ...base, dados: { ...base.dados, itens: [ativa, parou] } } });
  montar(<Assinaturas />);
  expect(await screen.findByText("SAAS ANTIGO")).toBeTruthy();
  expect(screen.getAllByText("parou de cobrar")).toHaveLength(1);
  expect(screen.getByText("1 assinaturas ativas")).toBeTruthy();
});
