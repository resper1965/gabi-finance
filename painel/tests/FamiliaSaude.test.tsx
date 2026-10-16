import { vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { Familia } from "../src/telas/Familia";
import { posicao } from "../src/telas/FamiliaSaude";

const montar = (ui: React.ReactElement) => render(<ToastProvider><FiltrosProvider>{ui}</FiltrosProvider></ToastProvider>);
const env = (dados: unknown) => ({ dados_ate: "2026-10-16T12:00:00Z", desatualizado: false, fontes: [], dados });
const med = (marcador: string, em: string, valor: string, extra: object = {}) =>
  ({ marcador, em, valor, unidade: "mg/dL", ref_min: "70", ref_max: "99", fora_da_faixa: false, qualitativo: false, ...extra });

const HIST = [med("Glicose", "2026-01-10", "92"), med("Glicose", "2026-07-10", "120", { fora_da_faixa: true }), med("Ferro", "2026-07-10", "40", { ref_min: "60", ref_max: "150", fora_da_faixa: true }),
  med("HIV", "2026-07-10", "Não reagente", { qualitativo: true, unidade: null, ref_min: null, ref_max: null })];
const MARC = [{ marcador: "Glicose", valor: "120", unidade: "mg/dL", em: "2026-07-10", fora_da_faixa: true }, { marcador: "Ferro", valor: "40", unidade: "mg/dL", em: "2026-07-10", fora_da_faixa: true },
  { marcador: "HIV", valor: "Não reagente", unidade: null, em: "2026-07-10", fora_da_faixa: false, qualitativo: true }];

interface Opcoes { laudos?: object | 403; chamadas?: { metodo: string; url: string; corpo: unknown }[] }
function servidor({ laudos, chamadas = [] }: Opcoes = {}) {
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const metodo = init?.method ?? "GET";
    chamadas.push({ metodo, url, corpo: init?.body ? JSON.parse(String(init.body)) : undefined });
    const ok = (j: unknown) => ({ ok: true, status: 200, json: async () => j }) as Response;
    if (metodo !== "GET") return ok(env({}));
    if (/familia\/pessoas/.test(url)) return ok(env({ itens: [{ id: "p1", nome: "Lia" }, { id: "p2", nome: "Bia" }] }));
    if (/\/serie/.test(url)) return ok(env({ pontos: [{ em: "2026-01-10", valor: "92", unidade: "mg/dL", fora_da_faixa: false }, { em: "2026-07-10", valor: "120", unidade: "mg/dL", fora_da_faixa: true }] }));
    if (/familia\/exames\/p[12]$/.test(url)) return ok(env({ marcadores: MARC, historico: HIST }));
    if (/laudos\/\d+\/versoes/.test(url)) return ok(env({ versoes: [{ versao: 1 }, { versao: 2 }], diferencas: [{ marcador: "Glicose", em: "2026-07-10", antes: "92", depois: "120" }] }));
    if (/marcadores\/apelidos/.test(url)) return ok(env({ itens: [], sugestoes: [] }));
    if (/familia\/laudos/.test(url)) {
      if (laudos === 403) return { ok: false, status: 403, json: async () => ({ erro: "sem_escopo", mensagem: "Você não tem acesso a isto." }) } as Response;
      return ok(env(laudos ?? { itens: [], falhos: [] }));
    }
    return { ok: false, status: 404, json: async () => ({ erro: "nao_encontrado", mensagem: url }) } as Response;
  }));
  return chamadas;
}
const LAUDO = (id: number, sugerida: string | null, versao = 1) => ({ paperless_id: id, pessoa_sugerida: sugerida, versao, marcadores: [{ marcador: "TSH", valor: "2,5", unidade: "uUI/mL", em: "2026-05-03" }] });

beforeEach(() => { localStorage.clear(); window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

test("tabela mostra acima e abaixo em texto, nao so em cor", async () => {
  servidor();
  montar(<Familia />);
  const tabela = await screen.findByRole("table", { name: "Exames por data de coleta" });
  expect(within(tabela).getByText("120 mg/dL (acima)")).toBeTruthy();
  expect(within(tabela).getByText("40 mg/dL (abaixo)")).toBeTruthy();
  expect(within(tabela).getByText("92 mg/dL")).toBeTruthy();
  expect(posicao({ valor: "50", ref_min: "70", ref_max: "99", qualitativo: false })).toBe("abaixo");
});

test("qualitativo fica fora do grafico e da tabela numerica", async () => {
  servidor();
  montar(<Familia />);
  const lista = await screen.findByRole("region", { name: "Resultados qualitativos" });
  expect(lista.textContent).toContain("HIV: Não reagente");
  expect(screen.queryByRole("button", { name: /HIV/ })).toBeNull();  // sem botão de série
  expect(within(screen.getByRole("table")).queryByText(/HIV/)).toBeNull();
  fireEvent.click(await screen.findByRole("button", { name: /Glicose/ }));
  expect(await screen.findByRole("img", { name: "Série do marcador" })).toBeTruthy();
  expect(screen.getByTestId("faixa")).toBeTruthy();  // faixa de referência sombreada
});

test("fila em lote confirma so os selecionados", async () => {
  const chamadas = servidor({ laudos: { itens: [LAUDO(1, "p1"), LAUDO(2, null), LAUDO(3, "p2")], falhos: [] } });
  montar(<Familia />);
  const confirmar = await screen.findByRole("button", { name: "Confirmar selecionados" });
  fireEvent.click(screen.getByLabelText("Selecionar documento 1"));
  fireEvent.click(screen.getByLabelText("Selecionar documento 2"));
  expect((confirmar as HTMLButtonElement).disabled).toBe(true);  // o 2 ainda não tem dono
  fireEvent.change(screen.getByLabelText("De quem é o laudo 2"), { target: { value: "p2" } });
  expect((confirmar as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(confirmar);
  await waitFor(() => expect(chamadas.some((c) => /laudos\/lote$/.test(c.url))).toBe(true));
  expect(chamadas.find((c) => /laudos\/lote$/.test(c.url))!.corpo).toEqual({ itens: [{ paperless_id: 1, pessoa_id: "p1" }, { paperless_id: 2, pessoa_id: "p2" }] });
});

test("documento que falhou mostra o motivo e pode ser reprocessado", async () => {
  const chamadas = servidor({ laudos: { itens: [], falhos: [{ paperless_id: 9, motivo: "sem texto legível" }] } });
  vi.spyOn(window, "confirm").mockReturnValue(true);
  montar(<Familia />);
  const falhas = await screen.findByRole("region", { name: "Documentos que falharam" });
  expect(falhas.textContent).toContain("Documento 9: sem texto legível");
  fireEvent.click(within(falhas).getByRole("button", { name: "Reprocessar" }));
  await waitFor(() => expect(chamadas.find((c) => /exames\/reprocessar$/.test(c.url))?.corpo).toEqual({ paperless_id: 9 }));
});

test("reprocessar todos pede confirmacao e nao dispara se o dono recusar", async () => {
  const chamadas = servidor();
  vi.spyOn(window, "confirm").mockReturnValue(false);
  montar(<Familia />);
  fireEvent.click(await screen.findByRole("button", { name: "Reprocessar todos" }));
  expect(window.confirm).toHaveBeenCalled();
  expect(chamadas.some((c) => /reprocessar$/.test(c.url))).toBe(false);
});

test("acesso parcial (403 na fila) nao ve fila, reprocessar nem apelidos", async () => {
  servidor({ laudos: 403 });
  montar(<Familia />);
  await screen.findByRole("table", { name: "Exames por data de coleta" });
  expect(screen.queryByText(/Laudos para confirmar/)).toBeNull();
  expect(screen.queryByRole("button", { name: "Reprocessar todos" })).toBeNull();
  expect(screen.queryByText(/Apelidos de marcador/)).toBeNull();
});

test("comparar versoes mostra a diferenca", async () => {
  servidor({ laudos: { itens: [LAUDO(7, "p1", 2)], falhos: [] } });
  montar(<Familia />);
  fireEvent.click(await screen.findByRole("button", { name: "Comparar versões" }));
  const bloco = await screen.findByRole("region", { name: "Versões do documento 7" });
  expect(bloco.textContent).toContain("Glicose");
  expect(bloco.textContent).toContain("92 → 120");
});
