import { render, screen, fireEvent, within } from "@testing-library/react";
import { Valor } from "../src/componentes/Valor";
import { Faixa } from "../src/componentes/Faixa";
import { Etiqueta, type TipoEtiqueta } from "../src/componentes/Etiqueta";
import { Shell } from "../src/componentes/Shell";
import { OcultarContext } from "../src/lib/ocultar";
import { GRUPOS } from "../src/navegacao";

function celular(ativo: boolean) {
  window.matchMedia = ((q: string) => ({
    matches: ativo && q.includes("759"), media: q,
    addEventListener: () => {}, removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia;
}
beforeEach(() => { localStorage.clear(); celular(false); });

test("Valor oculta quando ligado", () => {
  const { rerender } = render(<Valor valor="1234.56" />);
  expect(screen.getByText("R$ 1.234,56")).toBeInTheDocument();
  rerender(<OcultarContext.Provider value={true}><Valor valor="1234.56" /></OcultarContext.Provider>);
  expect(screen.getByText("R$ ••••••")).toBeInTheDocument();
  expect(screen.queryByText(/1\.234/)).toBeNull();
});

test("Faixa fica amarela com desatualizado e aponta a fonte", () => {
  render(<Faixa dadosAte="2026-10-05T10:00:00Z" desatualizado fonte="c6-extrato" />);
  const f = screen.getByRole("status");
  expect(f).toHaveAttribute("data-estado", "desatualizado");
  expect(f).toHaveTextContent("05/10 07:00"); // sempre horário de Brasília
  expect(f).toHaveTextContent("c6-extrato parou");
});

test("Faixa em dia nao e amarela", () => {
  render(<Faixa dadosAte="2026-10-08T10:00:00Z" />);
  expect(screen.getByRole("status")).toHaveAttribute("data-estado", "ok");
  expect(screen.getByRole("status")).toHaveTextContent("dados até 08/10 07:00");
});

test("Faixa mostra a próxima rodada no horário de Brasília", () => {
  render(<Faixa dadosAte="2026-10-08T10:00:00Z" proximaRodada="2026-10-08T18:00:00Z" />);
  expect(screen.getByRole("status")).toHaveTextContent("próxima rodada às 15h");
});

test("Etiqueta sempre tem simbolo e texto", () => {
  const tipos: TipoEtiqueta[] = ["erro", "conferir", "ok", "atencao", "parado", "regra", "banco", "paperless", "ajuste"];
  for (const t of tipos) {
    const { container, unmount } = render(<Etiqueta tipo={t} texto="texto" />);
    const glifo = container.querySelector("[aria-hidden]")!.textContent!;
    expect(glifo.length).toBeGreaterThan(0);
    expect(container).toHaveTextContent("texto");
    unmount();
  }
});

test("Shell lembra a ultima aba", () => {
  const tela = (_a: unknown, aba: string) => <p>aba:{aba}</p>;
  const { unmount } = render(<Shell tela={tela} />);
  fireEvent.click(screen.getByRole("button", { name: "Caixa" }));
  fireEvent.click(screen.getByRole("tab", { name: "A pagar" }));
  expect(screen.getByText("aba:contas")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Gastos" }));
  fireEvent.click(screen.getByRole("button", { name: "Caixa" }));
  expect(screen.getByText("aba:contas")).toBeInTheDocument();
  unmount();
  render(<Shell tela={tela} />); // recarregar a pagina
  expect(screen.getByText("aba:contas")).toBeInTheDocument();
});

test("Shell abre área e aba do link (#cadastros/documentos), mesmo com outra aba salva", () => {
  localStorage.setItem("gabi.area", "cadastros");
  localStorage.setItem("gabi.aba.cadastros", "agendas");
  window.location.hash = "#cadastros/documentos";
  const tela = (_a: unknown, aba: string) => <p>aba:{aba}</p>;
  render(<Shell tela={tela} />);
  expect(screen.getByText("aba:documentos")).toBeInTheDocument();
  window.location.hash = "";
});

test("Shell mostra a aba salva da área nova ao trocar de área", () => {
  localStorage.setItem("gabi.aba.gastos", "cartao");
  const tela = (_a: unknown, aba: string) => <p>aba:{aba}</p>;
  render(<Shell tela={tela} />);
  fireEvent.click(screen.getByRole("button", { name: "Gastos" }));
  expect(screen.getByText("aba:cartao")).toBeInTheDocument();
});

test("Shell vira barra inferior abaixo de 760px", () => {
  celular(true);
  render(<Shell tela={() => null} />);
  expect(screen.queryByRole("navigation", { name: "Painéis" })).toBeNull();
  const barra = screen.getByRole("navigation", { name: "Barra inferior" });
  for (const r of ["Hoje", "Agenda", "Mensagens", "Caixa", "Mais"]) expect(within(barra).getByText(r)).toBeInTheDocument();
});

test("textos da navegacao iguais ao prototipo", () => {
  const nav = Object.fromEntries(GRUPOS.map((g) => [g.titulo, g.areas.map((a) => a.rotulo)]));
  expect(nav).toEqual({
    Dia: ["Hoje", "Envios", "Atividades", "Projetos"],
    Trabalho: ["Agenda", "Mensagens"],
    Dinheiro: ["Caixa", "Gastos", "Cobrar", "Regras"],
    Casa: ["Cadastros", "Gabi"],
  });
});

test("Shell mostra selo de contagem no item do menu e total no sino", () => {
  render(<Shell tela={() => null} contagens={{ sino: 5, menu: { regras: 3, caixa: 2 } }} />);
  expect(within(screen.getByRole("button", { name: "Regras" })).getByText("3")).toHaveAttribute("data-selo");
  expect(within(screen.getByRole("button", { name: "Caixa" })).getByText("2")).toHaveAttribute("data-selo");
  expect(within(screen.getByRole("button", { name: "Alertas" })).getByText("5")).toHaveAttribute("data-selo");
});

test("Shell sem pendencia nao mostra selo", () => {
  render(<Shell tela={() => null} contagens={{ sino: 0, menu: { regras: 0 } }} />);
  expect(screen.queryByText("0")).toBeNull();
  expect(document.querySelectorAll("[data-selo]").length).toBe(0);
});
