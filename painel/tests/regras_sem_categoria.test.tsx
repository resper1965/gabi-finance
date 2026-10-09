import { vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { Regras } from "../src/telas/Regras";
import { amostra, apiFalsa } from "./apiFalsa";

const montar = (ui: React.ReactElement) => render(<ToastProvider><FiltrosProvider>{ui}</FiltrosProvider></ToastProvider>);
beforeEach(() => { localStorage.clear(); window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia; });
afterEach(() => { vi.unstubAllGlobals(); });

function sugestaoSemCategoria() {
  const base = amostra("sugestoes");
  const item = { ...base.dados.itens[0], id: 77, tipo: "regra", lancamento_id: null, motivo: "3 PIX para BEKAA sem categoria; escolha a categoria", impacto: { passado: 3, futuro_estimado: 0.5 },
                 payload: { padrao: "BEKAA", acao: { categoria_id: null } } };
  return { ...base, dados: { ...base.dados, itens: [item] } };
}

test("sugestao de regra sem categoria pede escolha e so aprova depois de escolher", async () => {
  const chamadas = apiFalsa({ sugestoes: sugestaoSemCategoria() });
  montar(<Regras />);
  const select = (await screen.findByLabelText("Categoria da sugestão BEKAA")) as HTMLSelectElement;
  expect(Array.from(select.options).map((o) => o.textContent)[0]).toBe("escolher…");
  const aprovar = screen.getByRole("button", { name: "Aprovar e ligar" }) as HTMLButtonElement;
  expect(aprovar.disabled).toBe(true);
  const primeira = Array.from(select.options).find((o) => o.value !== "0")!;
  fireEvent.change(select, { target: { value: primeira.value } });
  expect(aprovar.disabled).toBe(false);
  fireEvent.click(aprovar);
  await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST" && /sugestoes\/77\/aprovar$/.test(c.url))).toBe(true));
  expect(chamadas.find((c) => c.metodo === "POST" && /aprovar$/.test(c.url))!.corpo).toEqual({ edicao: { acao: { categoria_id: Number(primeira.value) } } });
});
