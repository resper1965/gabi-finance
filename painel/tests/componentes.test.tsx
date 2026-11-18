import { render, screen, fireEvent, within } from "@testing-library/react";
import { Valor } from "../src/componentes/Valor";
import { Faixa } from "../src/componentes/Faixa";
import { Etiqueta, type TipoEtiqueta } from "../src/componentes/Etiqueta";
import { Shell } from "../src/componentes/Shell";
import { OcultarContext } from "../src/lib/ocultar";
import { GRUPOS } from "../src/navegacao";
import { Evidencia } from "../src/componentes/Evidencia";
import { ProvContext } from "../src/lib/proveniencia";

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

test("Etiqueta é um carimbo: sempre com texto e tipo, a cor nunca sozinha", () => {
  const tipos: TipoEtiqueta[] = ["erro", "conferir", "ok", "nota", "atencao", "parado", "regra", "banco", "paperless", "ajuste"];
  for (const t of tipos) {
    const { container, unmount } = render(<Etiqueta tipo={t} texto="texto" />);
    const carimbo = container.querySelector(".carimbo")!;
    expect(carimbo).toHaveAttribute("data-tipo", t);
    expect(carimbo).toHaveTextContent("texto");
    unmount();
  }
});

const prov = { dadosAte: "2026-10-08T17:00:00Z", desatualizado: false, proximaRodada: "2026-10-09T09:00:00Z",
  fontes: [{ nome: "open-finance", estado: "ok", ultima: "2026-10-08T17:00:00Z" }, { nome: "notas-nibo", estado: "parado", ultima: null }] };

test("Evidencia mostra a cadeia de proveniência ao focar e fecha com Esc", () => {
  render(<ProvContext.Provider value={prov}><Evidencia codigo="E-01" rotulo="Saldo do caixa único" fontes={[{ nome: "open-finance", papel: "saldos" }]} base="2 contas"><Valor valor="10.00" /></Evidencia></ProvContext.Provider>);
  const gatilho = screen.getByRole("button", { name: /R\$ 10,00.*E-01/ });
  expect(screen.queryByRole("tooltip")).toBeNull();
  fireEvent.focus(gatilho);
  const quadro = screen.getByRole("tooltip");
  expect(gatilho).toHaveAttribute("aria-describedby", quadro.id);
  expect(quadro).toHaveTextContent("Saldo do caixa único");
  expect(quadro).toHaveTextContent("open-finance");
  expect(quadro).toHaveTextContent("dados até 08/10 14:00");
  expect(quadro).toHaveTextContent("conferido");
  fireEvent.keyDown(gatilho, { key: "Escape" });
  expect(screen.queryByRole("tooltip")).toBeNull();
});

test("Evidencia abre no toque (foco + clique) e fecha no toque seguinte", () => {
  render(<ProvContext.Provider value={prov}><Evidencia codigo="E-06" rotulo="Menor saldo" fontes={[{ nome: "open-finance", papel: "saldos" }]} estado="projecao"><Valor valor="1.00" /></Evidencia></ProvContext.Provider>);
  const gatilho = screen.getByRole("button", { name: /E-06/ });
  fireEvent.pointerDown(gatilho); fireEvent.focus(gatilho); fireEvent.click(gatilho);
  expect(screen.getByRole("tooltip")).toHaveTextContent("projeção");
  fireEvent.pointerDown(gatilho); fireEvent.click(gatilho);
  expect(screen.queryByRole("tooltip")).toBeNull();
});

test("Evidencia de fonte parada fica a conferir", () => {
  render(<ProvContext.Provider value={prov}><Evidencia codigo="E-03" rotulo="A receber" fontes={[{ nome: "notas-nibo", papel: "notas" }]}><Valor valor="5.00" /></Evidencia></ProvContext.Provider>);
  const gatilho = screen.getByRole("button", { name: /E-03/ });
  expect(gatilho).toHaveAttribute("data-estado", "a_conferir");
  fireEvent.click(gatilho);
  expect(screen.getByRole("tooltip")).toHaveTextContent("a conferir");
  expect(screen.getByRole("tooltip")).toHaveTextContent("notas-nibo parou");
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

test("Shell abre área e aba do link (#cadastros/despesas), mesmo com outra aba salva", () => {
  localStorage.setItem("gabi.area", "caixa");
  localStorage.setItem("gabi.aba.cadastros", "cadastros");
  window.location.hash = "#cadastros/despesas";
  const tela = (_a: unknown, aba: string) => <p>aba:{aba}</p>;
  render(<Shell tela={tela} />);
  expect(screen.getByText("aba:despesas")).toBeInTheDocument();
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
  for (const r of ["Caixa", "Gastos", "Cobrar", "Regras", "Mais"]) expect(within(barra).getByText(r)).toBeInTheDocument();
});

test("textos da navegacao (só áreas financeiras)", () => {
  const nav = Object.fromEntries(GRUPOS.map((g) => [g.titulo, g.areas.map((a) => a.rotulo)]));
  expect(nav).toEqual({
    Dinheiro: ["Caixa", "Gastos", "Cobrar", "Regras"],
    Cadastros: ["Cadastros", "Gabi"],
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

test("Evidencia: rolar dentro do quadro não fecha; rolar a página fecha", () => {
  render(<ProvContext.Provider value={prov}><Evidencia codigo="PV-06" rotulo="Menor saldo" fontes={[{ nome: "open-finance", papel: "saldos" }, { nome: "notas-nibo", papel: "notas" }]} estado="projecao"><Valor valor="1.00" /></Evidencia></ProvContext.Provider>);
  const gatilho = screen.getByRole("button", { name: /PV-06/ });
  fireEvent.focus(gatilho);
  const quadro = screen.getByRole("tooltip");
  fireEvent.scroll(quadro);
  expect(screen.getByRole("tooltip")).toBeInTheDocument();
  fireEvent.blur(gatilho, { relatedTarget: quadro });
  expect(screen.getByRole("tooltip")).toBeInTheDocument();
  fireEvent.scroll(window);
  expect(screen.queryByRole("tooltip")).toBeNull();
});
