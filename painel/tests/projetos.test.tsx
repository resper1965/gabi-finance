import { vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { Projetos } from "../src/telas/Projetos";
import { GRUPOS } from "../src/navegacao";
import { TELAS } from "../src/App";
import { apiFalsa, type Chamada } from "./apiFalsa";

const env = (dados: unknown) => ({ dados_ate: null, desatualizado: false, fontes: [], dados });
const proj = (id: number, nome: string, status = "ativo", feitas = 2, total = 5, prazo: string | null = "2026-11-20") => ({ id, nome, status, prazo, objetivo: "trocar o motor", progresso: { feitas, total }, orcamento_centavos: null });
const ativ = (id: number, texto: string, extra = {}) => ({ id, texto, vence_em: null, tem_hora: false, status: "aberta", prazo: "sem_data", projeto_id: 1, depende_de_id: null, marco: false, bloqueada: false, ...extra });
const DADOS = {
  id: 1, nome: "Carro na oficina", objetivo: "trocar o motor", status: "ativo", prazo: "2026-11-20", progresso: { feitas: 2, total: 5 },
  proximas: [ativ(2, "pedir orçamento", { vence_em: "2026-10-30", prazo: "proxima" })], bloqueadas: [ativ(3, "aprovar o serviço", { depende_de_id: 2, bloqueada: true, espera: "pedir orçamento" })],
  atrasadas: [ativ(4, "ligar pro seguro", { vence_em: "2026-10-20", prazo: "vencida" })],
  pessoas: [{ id: 1, nome: "Seu Jorge", papel: "mecânico", pessoa_id: null, contato: "11 99999-0000" }],
  orcamento: "5000.00", gasto: "1200.50", saldo: "3799.50",
  fatos_recentes: [{ id: 1, texto: "O mecânico disse que o prazo é dia 20", data: "2026-10-26", pessoa_nome: "Seu Jorge", anexo_id: 7, atividade_id: null, origem: "hermes" }],
  anexos: 2,
  anexos_itens: [{ id: 7, tipo: "imagem", recebido_em: "2026-10-26T12:00:00+00:00", transcricao: null, paperless_id: null },
                 { id: 8, tipo: "audio", recebido_em: "2026-10-25T12:00:00+00:00", transcricao: "oi, o carro fica pronto dia 20", paperless_id: null }],
};
const DETALHE = env(DADOS);
const ATIVOS = env({ itens: [proj(1, "Carro na oficina"), proj(2, "Reforma da cozinha", "ativo", 0, 3, null)] });
const VAZIO = env({ itens: [] });
const CAIXA = env({ itens: [{ id: 9, tipo: "imagem", recebido_em: "2026-10-27T10:00:00+00:00", transcricao: null }, { id: 10, tipo: "audio", recebido_em: "2026-10-27T11:00:00+00:00", transcricao: "pagar o guincho amanhã" }] });
const SOBRE = (extra: Record<string, unknown> = {}) => ({ projetos: ATIVOS, "projeto-detalhe": DETALHE, "anexos-recentes": VAZIO, ...extra });

const montar = () => render(<ToastProvider><Projetos /></ToastProvider>);
const achar = (c: Chamada[], metodo: string, fim: string) => c.find((x) => x.metodo === metodo && x.url.endsWith(fim));
const abrir = async () => { fireEvent.click(await screen.findByRole("button", { name: /Carro na oficina/ })); await screen.findByRole("heading", { name: "Carro na oficina" }); };
beforeEach(() => { vi.useFakeTimers({ toFake: ["Date"] }); vi.setSystemTime(new Date("2026-10-27T15:00:00")); });
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

test("lista os projetos ativos com prazo e progresso em texto, e tem as abas", async () => {
  apiFalsa(SOBRE());
  montar();
  expect(await screen.findByText("2/5")).toBeInTheDocument();
  expect(screen.getByText("0/3")).toBeInTheDocument();
  expect(screen.getByText(/20\/11/)).toBeInTheDocument();
  expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Ativos", "Pausados", "Encerrados"]);
});

test("aba Pausados lê status=pausado e Encerrados lê concluído e cancelado", async () => {
  const chamadas = apiFalsa(SOBRE());
  montar();
  await screen.findByText("2/5");
  fireEvent.click(screen.getByRole("tab", { name: "Pausados" }));
  await waitFor(() => expect(chamadas.some((c) => c.url.endsWith("/api/v1/projetos?status=pausado"))).toBe(true));
  fireEvent.click(screen.getByRole("tab", { name: "Encerrados" }));
  await waitFor(() => expect(chamadas.some((c) => c.url.endsWith("?status=concluido"))).toBe(true));
  expect(chamadas.some((c) => c.url.endsWith("?status=cancelado"))).toBe(true);
});

test("sem projeto mostra a frase de vazio", async () => {
  apiFalsa(SOBRE({ projetos: VAZIO }));
  montar();
  expect(await screen.findByText(/Nenhum projeto ativo/)).toBeInTheDocument();
});

test("abrir o detalhe mostra os blocos: resumo, atividades, pessoas, fatos e anexos", async () => {
  const chamadas = apiFalsa(SOBRE());
  montar();
  await abrir();
  expect(achar(chamadas, "GET", "/api/v1/projetos/1")).toBeTruthy();
  expect(screen.getByText("trocar o motor")).toBeInTheDocument();
  expect(screen.getByText(/5\.000,00/)).toBeInTheDocument();
  expect(screen.getByText(/1\.200,50/)).toBeInTheDocument();
  expect(screen.getByText(/3\.799,50/)).toBeInTheDocument();
  expect(screen.getByText("pedir orçamento")).toBeInTheDocument();
  expect(screen.getByText("aprovar o serviço")).toBeInTheDocument();
  expect(screen.getByText("espera: pedir orçamento")).toBeInTheDocument();
  expect(screen.getByText("ligar pro seguro")).toBeInTheDocument();
  expect(screen.getByText(/Seu Jorge — mecânico/)).toBeInTheDocument();
  expect(screen.getByText("O mecânico disse que o prazo é dia 20")).toBeInTheDocument();
  expect(screen.getByText("oi, o carro fica pronto dia 20")).toBeInTheDocument();
});

test("anexos: imagem em miniatura e áudio com player apontam para o arquivo original", async () => {
  apiFalsa(SOBRE());
  montar();
  await abrir();
  const img = document.querySelector("img[src='/api/v1/anexos/7/arquivo']");
  expect(img).toBeTruthy();
  expect(document.querySelector("audio[controls][src='/api/v1/anexos/8/arquivo']")).toBeTruthy();
  expect(screen.getByRole("link", { name: /Abrir anexo 7/ })).toHaveAttribute("href", "/api/v1/anexos/7/arquivo");
});

test("projeto sem orçamento não mostra dinheiro nem 'null'", async () => {
  apiFalsa(SOBRE({ "projeto-detalhe": env({ ...DADOS, orcamento: null, saldo: null, gasto: "0.00" }) }));
  montar();
  await abrir();
  expect(screen.getByText(/Sem orçamento/)).toBeInTheDocument();
  expect(document.body.textContent).not.toMatch(/null|None/);
});

test("criar projeto manda {nome, objetivo}", async () => {
  const chamadas = apiFalsa(SOBRE());
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Novo projeto" }));
  fireEvent.change(screen.getByLabelText("Nome do projeto"), { target: { value: "Reforma" } });
  fireEvent.change(screen.getByLabelText("Objetivo"), { target: { value: "trocar o piso" } });
  fireEvent.click(screen.getByRole("button", { name: "Criar projeto" }));
  await waitFor(() => expect(achar(chamadas, "POST", "/api/v1/projetos")).toBeTruthy());
  expect(achar(chamadas, "POST", "/api/v1/projetos")!.corpo).toEqual({ nome: "Reforma", objetivo: "trocar o piso" });
});

test("anotar fato manda {texto, data}", async () => {
  const chamadas = apiFalsa(SOBRE());
  montar();
  await abrir();
  fireEvent.click(screen.getByRole("button", { name: "Anotar fato" }));
  fireEvent.change(screen.getByLabelText("Fato"), { target: { value: "Ficou combinado pagar em duas vezes" } });
  fireEvent.change(screen.getByLabelText("Data do fato"), { target: { value: "2026-10-27" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar fato" }));
  await waitFor(() => expect(achar(chamadas, "POST", "/api/v1/projetos/1/fatos")).toBeTruthy());
  expect(achar(chamadas, "POST", "/api/v1/projetos/1/fatos")!.corpo).toEqual({ texto: "Ficou combinado pagar em duas vezes", data: "2026-10-27" });
});

test("registrar gasto manda o valor em reais como string", async () => {
  const chamadas = apiFalsa(SOBRE());
  montar();
  await abrir();
  fireEvent.click(screen.getByRole("button", { name: "Registrar gasto" }));
  fireEvent.change(screen.getByLabelText("Valor do gasto"), { target: { value: "300,00" } });
  fireEvent.change(screen.getByLabelText("Descrição do gasto"), { target: { value: "peça" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar gasto" }));
  await waitFor(() => expect(achar(chamadas, "POST", "/api/v1/projetos/1/gastos")).toBeTruthy());
  expect(achar(chamadas, "POST", "/api/v1/projetos/1/gastos")!.corpo).toEqual({ valor: "300,00", descricao: "peça" });
});

test("adicionar pessoa manda {nome, papel}", async () => {
  const chamadas = apiFalsa(SOBRE());
  montar();
  await abrir();
  fireEvent.click(screen.getByRole("button", { name: "Adicionar pessoa" }));
  fireEvent.change(screen.getByLabelText("Nome da pessoa"), { target: { value: "Dra. Ana" } });
  fireEvent.change(screen.getByLabelText("Papel"), { target: { value: "advogada" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar pessoa" }));
  await waitFor(() => expect(achar(chamadas, "POST", "/api/v1/projetos/1/pessoas")).toBeTruthy());
  expect(achar(chamadas, "POST", "/api/v1/projetos/1/pessoas")!.corpo).toEqual({ nome: "Dra. Ana", papel: "advogada" });
});

test("Pausar muda o status direto; Concluir e Cancelar só chamam PATCH depois de confirmar", async () => {
  const chamadas = apiFalsa(SOBRE());
  montar();
  await abrir();
  fireEvent.click(screen.getByRole("button", { name: "Concluir projeto" }));
  expect(achar(chamadas, "PATCH", "/api/v1/projetos/1")).toBeUndefined();
  expect(screen.getByRole("alert")).toHaveTextContent(/não há como reabrir/i);
  fireEvent.click(screen.getByRole("button", { name: "Confirmar concluir" }));
  await waitFor(() => expect(achar(chamadas, "PATCH", "/api/v1/projetos/1")).toBeTruthy());
  expect(achar(chamadas, "PATCH", "/api/v1/projetos/1")!.corpo).toEqual({ status: "concluido" });
});

test("Pausar não pede confirmação", async () => {
  const chamadas = apiFalsa(SOBRE());
  montar();
  await abrir();
  fireEvent.click(screen.getByRole("button", { name: "Pausar projeto" }));
  await waitFor(() => expect(achar(chamadas, "PATCH", "/api/v1/projetos/1")).toBeTruthy());
  expect(achar(chamadas, "PATCH", "/api/v1/projetos/1")!.corpo).toEqual({ status: "pausado" });
});

test("editar prazo manda PATCH {prazo}", async () => {
  const chamadas = apiFalsa(SOBRE());
  montar();
  await abrir();
  fireEvent.change(screen.getByLabelText("Prazo do projeto"), { target: { value: "2026-12-15" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar prazo" }));
  await waitFor(() => expect(achar(chamadas, "PATCH", "/api/v1/projetos/1")).toBeTruthy());
  expect(achar(chamadas, "PATCH", "/api/v1/projetos/1")!.corpo).toEqual({ prazo: "2026-12-15" });
});

test("projeto encerrado não oferece ações de status nem de atividade nova", async () => {
  apiFalsa(SOBRE({ "projeto-detalhe": env({ ...DADOS, status: "concluido" }) }));
  montar();
  await abrir();
  expect(screen.queryByRole("button", { name: "Pausar projeto" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Concluir projeto" })).toBeNull();
  expect(screen.getByText(/não reabre/i)).toBeInTheDocument();
});

test("caixa de entrada lista anexos, mostra a transcrição e 'Ligar a…' chama POST /projetos/{id}/anexos", async () => {
  const chamadas = apiFalsa(SOBRE({ "anexos-recentes": CAIXA }));
  montar();
  expect(await screen.findByText("pagar o guincho amanhã")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Ligar anexo 9 a"), { target: { value: "1" } });
  fireEvent.click(screen.getByRole("button", { name: "Ligar anexo 9" }));
  await waitFor(() => expect(achar(chamadas, "POST", "/api/v1/projetos/1/anexos")).toBeTruthy());
  expect(achar(chamadas, "POST", "/api/v1/projetos/1/anexos")!.corpo).toEqual({ anexo_id: 9 });
});

test("sem anexo novo a caixa de entrada não aparece", async () => {
  apiFalsa(SOBRE());
  montar();
  await screen.findByText("2/5");
  expect(screen.queryByText("Caixa de entrada")).toBeNull();
});

test("o menu Dia tem Projetos depois de Atividades e a tela está registrada", () => {
  const dia = GRUPOS.find((g) => g.titulo === "Dia")!.areas.map((a) => a.rotulo);
  expect(dia).toEqual(["Hoje", "Envios", "Atividades", "Projetos"]);
  expect(GRUPOS.find((g) => g.titulo === "Dia")!.areas[3].pergunta).toBe("Como andam meus projetos?");
  expect(TELAS.projetos).toBeTypeOf("function");
});
