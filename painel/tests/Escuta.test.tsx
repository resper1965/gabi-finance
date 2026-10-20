import { vi } from "vitest";
import { act, render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { ToastProvider } from "../src/lib/toast";
import { FiltrosProvider } from "../src/lib/filtros";
import { Escuta } from "../src/telas/Escuta";

const env = (dados: unknown) => ({ dados_ate: null, desatualizado: false, fontes: [], dados });
interface Chamada { metodo: string; url: string; corpo: unknown }
interface Opcoes { fila?: unknown[]; aprovados?: unknown[]; grupos?: unknown[]; parametros?: Record<string, unknown>; falha?: RegExp; segurar?: Promise<void>; negar?: boolean; contatos?: unknown[]; contasFalhas?: Record<string, unknown>; total?: number; aposPut?: Record<string, unknown> }

function fake(o: Opcoes = {}) {
  const chamadas: Chamada[] = [];
  let parametros: Record<string, unknown> = { modo: "registro", palavras_risco: ["urgente", "multa"], horas_sem_receber: 12, anexo_max_mb: 25, ...o.parametros };
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const metodo = init?.method ?? "GET";
    chamadas.push({ metodo, url, corpo: init?.body ? JSON.parse(String(init.body)) : undefined });
    const ok = (j: unknown) => ({ ok: true, status: 200, json: async () => j }) as Response;
    if (o.negar) return { ok: false, status: 403, json: async () => ({ erro: "sem_escopo", mensagem: "Você não tem acesso a isto." }) } as Response;
    if (metodo !== "GET") {
      if (o.segurar) await o.segurar;
      if (o.falha?.test(url)) return { ok: false, status: 400, json: async () => ({ erro: "requisicao_invalida", mensagem: "papel inválido" }) } as Response;
      if (metodo === "PUT") { parametros = { ...parametros, ...JSON.parse(String(init!.body)) }; const resposta = parametros; if (o.aposPut) parametros = { ...parametros, ...o.aposPut }; return ok(env(resposta)); }
      if (/contatos\/trazer/.test(url)) return ok(env({ criadas: 2, ignoradas: 1 }));
      if (/contatos\/sincronizar/.test(url)) return ok(env({ contas: { "a@x.com": { lidos: 7 }, ...(o.contasFalhas ?? {}) }, total: 7, invalidos: 1 }));
      return ok(env({}));
    }
    if (/contatos\/propostas/.test(url)) return ok(env({ itens: [], escrita: "ligado" }));
    if (/contatos/.test(url)) return ok(env({ itens: o.contatos ?? [], total: o.total ?? (o.contatos ?? []).length, limite: 50, offset: 0 }));
    if (/remetentes/.test(url)) return ok(env({ fila: o.fila ?? [], aprovados: o.aprovados ?? [] }));
    if (/grupos/.test(url)) return ok(env({ grupos: o.grupos ?? [] }));
    return ok(env(parametros));
  }));
  return chamadas;
}
const montar = () => render(<ToastProvider><FiltrosProvider><Escuta /></FiltrosProvider></ToastProvider>);
const posts = (c: Chamada[]) => c.filter((x) => x.metodo !== "GET");
const assentar = async () => { for (let i = 0; i < 3; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); }); };
const linhaDe = async (nome: string) => (await screen.findByText(nome)).closest("li")!;
let erros: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  localStorage.clear();
  window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia;
  erros = vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(async () => { await assentar(); const chamadas = erros.mock.calls.length; erros.mockRestore(); vi.unstubAllGlobals(); expect(chamadas).toBe(0); });

const FILA = [{ numero: "+5511911110000", nome: "Ana", qtd: 3 }, { numero: "+5511922220000", nome: null, qtd: 1 }];

test("fila vazia mostra o estado vazio", async () => {
  fake();
  montar();
  expect(await screen.findByText(/Nenhum remetente novo/)).toBeTruthy();
});

test("numero aparece junto do nome quando ha nome, e sozinho quando nao ha", async () => {
  fake({ fila: FILA });
  montar();
  const ana = await linhaDe("Ana");
  expect(ana.textContent).toContain("+5511911110000");
  expect(ana.textContent).toContain("3");
  expect(screen.getByText("+5511922220000")).toBeTruthy();
});

test("botoes da linha tem nome acessivel com a pessoa e distinguem as linhas", async () => {
  fake({ fila: FILA });
  montar();
  for (const a of ["Aprovar", "Ignorar", "Bloquear"]) {
    expect(await screen.findByRole("button", { name: `${a} Ana` })).toBeTruthy();
    expect(screen.getByRole("button", { name: `${a} +5511922220000` })).toBeTruthy();
  }
  fireEvent.click(screen.getByRole("button", { name: "Aprovar Ana" }));
  expect(screen.getByRole("button", { name: "Aprovar como Família: Ana" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Aprovar como Cobrança: Ana" })).toBeTruthy();
});

test("aprovar exige escolher o papel antes de enviar e foca o primeiro papel", async () => {
  const c = fake({ fila: FILA });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Aprovar Ana" }));
  expect(posts(c)).toHaveLength(0);
  const primeiro = screen.getByRole("button", { name: "Aprovar como Família: Ana" });
  await waitFor(() => expect(document.activeElement).toBe(primeiro));
  fireEvent.click(screen.getByRole("button", { name: "Aprovar como Prestador: Ana" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0].url).toBe("/api/v1/escuta/remetentes/%2B5511911110000/aprovar");
  expect(posts(c)[0].corpo).toEqual({ papel: "prestador" });
  await waitFor(() => expect(c.filter((x) => x.metodo === "GET" && /remetentes/.test(x.url)).length).toBeGreaterThan(1));
});

test("cancelar a escolha de papel nao envia nada e devolve o foco ao Aprovar da linha", async () => {
  const c = fake({ fila: FILA });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Aprovar Ana" }));
  fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
  expect(posts(c)).toHaveLength(0);
  const volta = screen.getByRole("button", { name: "Aprovar Ana" });
  await waitFor(() => expect(document.activeElement).toBe(volta));
});

test("a escolha de papel de uma linha nao vaza para outra", async () => {
  const c = fake({ fila: FILA });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Aprovar Ana" }));
  fireEvent.click(screen.getByRole("button", { name: "Aprovar +5511922220000" }));
  expect(screen.queryByRole("button", { name: "Aprovar como Família: Ana" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Aprovar como Cobrança: +5511922220000" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0].url).toBe("/api/v1/escuta/remetentes/%2B5511922220000/aprovar");
  expect(posts(c)[0].corpo).toEqual({ papel: "cobranca" });
});

test("ignorar e bloquear chamam a rota certa", async () => {
  const c = fake({ fila: FILA });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Ignorar Ana" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0].url).toBe("/api/v1/escuta/remetentes/%2B5511911110000/ignorar");
  await waitFor(() => expect((screen.getByRole("button", { name: "Bloquear Ana" }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "Bloquear Ana" }));
  await waitFor(() => expect(posts(c)).toHaveLength(2));
  expect(posts(c)[1].url).toBe("/api/v1/escuta/remetentes/%2B5511911110000/bloquear");
});

test("duplo clique em Ignorar envia uma unica requisicao e desabilita os botoes enquanto isso", async () => {
  let soltar!: () => void;
  const c = fake({ fila: FILA, segurar: new Promise<void>((r) => { soltar = r; }) });
  montar();
  const botao = await screen.findByRole("button", { name: "Ignorar Ana" });
  fireEvent.click(botao);
  fireEvent.click(botao);
  await waitFor(() => expect((screen.getByRole("button", { name: "Bloquear Ana" }) as HTMLButtonElement).disabled).toBe(true));
  expect((screen.getByRole("button", { name: "Aprovar +5511922220000" }) as HTMLButtonElement).disabled).toBe(true);
  soltar();
  await assentar();
  expect(posts(c)).toHaveLength(1);
});

test("erro da API: a linha continua durante e depois, e a mensagem aparece dentro da linha", async () => {
  let soltar!: () => void;
  fake({ fila: FILA, falha: /ignorar/, segurar: new Promise<void>((r) => { soltar = r; }) });
  montar();
  const linha = await linhaDe("Ana");
  fireEvent.click(within(linha).getByRole("button", { name: "Ignorar Ana" }));
  await waitFor(() => expect((within(linha).getByRole("button", { name: "Ignorar Ana" }) as HTMLButtonElement).disabled).toBe(true));
  expect(screen.getByText("Ana").closest("li")).toBe(linha);
  expect(document.body.contains(linha)).toBe(true);
  soltar();
  const alerta = await within(linha).findByRole("alert");
  expect(alerta.textContent).toContain("papel inválido");
  expect(document.body.contains(linha)).toBe(true);
  expect(within(screen.getByText("+5511922220000").closest("li")!).queryByRole("alert")).toBeNull();
  await waitFor(() => expect((within(linha).getByRole("button", { name: "Ignorar Ana" }) as HTMLButtonElement).disabled).toBe(false));
});

test("lista aprovados e aprova grupo", async () => {
  const c = fake({ aprovados: [{ pessoa_id: "p1", nome: "Bia", numero: "+5511933330000", papel: "familia" }], grupos: [{ id_grupo: "g1@g.us", nome: "Condomínio", aprovado: false }] });
  montar();
  expect(await screen.findByText("Bia")).toBeTruthy();
  fireEvent.click(await screen.findByRole("button", { name: "Aprovar grupo Condomínio" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0].url).toBe("/api/v1/escuta/grupos/g1%40g.us/aprovar");
});

test("trocar para ativo mostra o aviso, foca o Confirmar e exige confirmacao", async () => {
  const c = fake();
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Ativo" }));
  expect(screen.getByText(/em registro a escuta só registra; em ativo ela cria pedidos e avisa/i)).toBeTruthy();
  expect(posts(c)).toHaveLength(0);
  const confirmar = screen.getByRole("button", { name: "Confirmar modo ativo" });
  await waitFor(() => expect(document.activeElement).toBe(confirmar));
  fireEvent.click(confirmar);
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0]).toMatchObject({ metodo: "PUT", url: "/api/v1/escuta/parametros", corpo: { modo: "ativo" } });
});

test("cancelar a confirmacao do modo nao envia nada, mantem registro e devolve o foco ao Ativo", async () => {
  const c = fake();
  montar();
  const ativo = await screen.findByRole("button", { name: "Ativo" });
  fireEvent.click(ativo);
  fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
  expect(posts(c)).toHaveLength(0);
  expect(screen.queryByText(/em registro a escuta só registra/i)).toBeNull();
  expect(screen.getByRole("button", { name: "Registro" }).getAttribute("aria-pressed")).toBe("true");
  await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Ativo" })));
});

test("voltar para registro nao pede confirmacao (e o modo seguro: so registra)", async () => {
  const c = fake({ parametros: { modo: "ativo" } });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Registro" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0].corpo).toEqual({ modo: "registro" });
  expect(screen.queryByRole("button", { name: "Confirmar modo ativo" })).toBeNull();
});

test("palavras de risco: adicionar e remover enviam a lista mais recente inteira", async () => {
  const c = fake();
  montar();
  fireEvent.change(await screen.findByLabelText("Nova palavra de risco"), { target: { value: "  processo  " } });
  fireEvent.click(screen.getByRole("button", { name: "Adicionar palavra" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0].corpo).toEqual({ palavras_risco: ["urgente", "multa", "processo"] });
  await waitFor(() => expect((screen.getByRole("button", { name: "Remover urgente" }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "Remover urgente" }));
  await waitFor(() => expect(posts(c)).toHaveLength(2));
  expect(posts(c)[1].corpo).toEqual({ palavras_risco: ["multa", "processo"] });
});

test("duas remocoes rapidas nao se sobrescrevem: so uma sai enquanto a outra espera", async () => {
  let soltar!: () => void;
  const c = fake({ segurar: new Promise<void>((r) => { soltar = r; }) });
  montar();
  const a = await screen.findByRole("button", { name: "Remover urgente" });
  const b = screen.getByRole("button", { name: "Remover multa" });
  fireEvent.click(a);
  fireEvent.click(b);
  soltar();
  await assentar();
  expect(posts(c)).toHaveLength(1);
  expect(posts(c)[0].corpo).toEqual({ palavras_risco: ["multa"] });
});

test.each([
  ["   ", /vazia/i],
  ["URGENTE", /já existe/i],
  ["x".repeat(61), /60/],
])("palavra %j e recusada com mensagem e nada e enviado", async (texto, msg) => {
  const c = fake();
  montar();
  fireEvent.change(await screen.findByLabelText("Nova palavra de risco"), { target: { value: texto } });
  fireEvent.click(screen.getByRole("button", { name: "Adicionar palavra" }));
  expect((await screen.findByRole("alert")).textContent).toMatch(msg);
  expect(posts(c)).toHaveLength(0);
});

test("a 201a palavra e recusada com mensagem", async () => {
  const c = fake({ parametros: { palavras_risco: Array.from({ length: 200 }, (_, i) => `p${i}`) } });
  montar();
  fireEvent.change(await screen.findByLabelText("Nova palavra de risco"), { target: { value: "nova" } });
  fireEvent.click(screen.getByRole("button", { name: "Adicionar palavra" }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/limite de 200/i);
  expect(posts(c)).toHaveLength(0);
});

test("400 no PUT mostra a mensagem do servidor e a UI fica com a lista salva", async () => {
  const c = fake({ falha: /parametros/ });
  montar();
  fireEvent.change(await screen.findByLabelText("Nova palavra de risco"), { target: { value: "nova" } });
  fireEvent.click(screen.getByRole("button", { name: "Adicionar palavra" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  const alertas = await screen.findAllByRole("alert");
  expect(alertas.filter((a) => /papel inválido/.test(a.textContent ?? ""))).toHaveLength(1);
  expect(alertas).toHaveLength(1);
  expect(screen.queryByText("nova", { selector: "span" })).toBeNull();
  expect(screen.getByRole("button", { name: "Remover urgente" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Remover nova" })).toBeNull();
});

test("horas e anexo gravam com chaves curtas", async () => {
  const c = fake();
  montar();
  fireEvent.change(await screen.findByLabelText("Horas sem receber"), { target: { value: "24" } });
  fireEvent.change(screen.getByLabelText("Tamanho máximo de anexo (MB)"), { target: { value: "10" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar limites" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0].corpo).toEqual({ horas_sem_receber: 24, anexo_max_mb: 10 });
});

test.each([["", "Horas sem receber"], ["0", "Horas sem receber"], ["169", "Horas sem receber"], ["2,5", "Horas sem receber"], ["101", "Tamanho máximo de anexo (MB)"], ["", "Tamanho máximo de anexo (MB)"]])(
  "valor invalido %j em %s nao e enviado e mostra mensagem", async (valor, campo) => {
    const c = fake();
    montar();
    fireEvent.change(await screen.findByLabelText(campo), { target: { value: valor } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar limites" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/inteiro/i);
    expect(posts(c)).toHaveLength(0);
  });

test("sem ser o dono (403) mostra uma unica mensagem", async () => {
  fake({ negar: true });
  montar();
  expect(await screen.findByText("Só o dono acessa a escuta.")).toBeTruthy();
  expect(screen.queryAllByRole("alert")).toHaveLength(0);
  expect(screen.queryByText(/Novos remetentes/)).toBeNull();
});

test("o servidor prevalece sobre o ultimo PUT: depois da releitura a tela mostra a lista do servidor", async () => {
  fake({ aposPut: { palavras_risco: ["externo"] } });
  montar();
  fireEvent.change(await screen.findByLabelText("Nova palavra de risco"), { target: { value: "processo" } });
  fireEvent.click(screen.getByRole("button", { name: "Adicionar palavra" }));
  expect(await screen.findByRole("button", { name: "Remover externo" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Remover processo" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Remover urgente" })).toBeNull();
});


const CONTATOS = [
  { nome: "Zé", telefone: "+5511988887777", contas: ["resper@ness.com.br"], ja_e_pessoa: false },
  { nome: "Ana", telefone: "+5511912345678", contas: ["resper@gmail.com"], ja_e_pessoa: false },
  { nome: null, telefone: "+5511900000000", contas: ["resper@gmail.com"], ja_e_pessoa: true },
];

test('botao "Trazer dos contatos" so envia os selecionados e fica desabilitado sem selecao', async () => {
  const c = fake({ contatos: CONTATOS });
  montar();
  const trazer = await screen.findByRole("button", { name: "Trazer dos contatos" });
  expect((trazer as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("checkbox", { name: "Selecionar Ana +5511912345678" }));
  expect((trazer as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(trazer);
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0]).toMatchObject({ metodo: "POST", url: "/api/v1/escuta/contatos/trazer", corpo: { telefones: ["+5511912345678"] } });
  expect(await screen.findByText(/Criadas 2 pessoas, 1 ignoradas/)).toBeTruthy();
  expect((screen.getByRole("checkbox", { name: "Selecionar Ana +5511912345678" }) as HTMLInputElement).checked).toBe(false);
});

test("quem ja e pessoa nao pode ser selecionado e o link do CSV aponta para a exportacao", async () => {
  fake({ contatos: CONTATOS });
  montar();
  expect((await screen.findByRole("checkbox", { name: "Selecionar +5511900000000" }) as HTMLInputElement).disabled).toBe(true);
  const a = screen.getByRole("link", { name: "Baixar contatos só na ness (CSV)" });
  expect(a.getAttribute("href")).toBe("/api/v1/escuta/contatos/so-na-ness.csv");
});

test("Sincronizar agora chama a rota e mostra so contagens", async () => {
  const c = fake({ contatos: CONTATOS });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Sincronizar agora" }));
  await waitFor(() => expect(posts(c).map((x) => x.url)).toEqual(["/api/v1/escuta/contatos/sincronizar"]));
  expect(await screen.findByText(/Sincronizado: 7 contatos, 1 números inválidos/)).toBeTruthy();
});

test("buscar envia o termo na leitura", async () => {
  const c = fake({ contatos: CONTATOS });
  montar();
  fireEvent.change(await screen.findByLabelText("Buscar contato"), { target: { value: "ana" } });
  fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
  await waitFor(() => expect(c.some((x) => /contatos\?busca=ana/.test(x.url))).toBe(true));
});

test("Apagar contatos pede confirmacao, foca o Confirmar e cancelar nao envia nada", async () => {
  const c = fake({ contatos: CONTATOS });
  montar();
  const apagar = await screen.findByRole("button", { name: "Apagar contatos" });
  fireEvent.click(apagar);
  expect(posts(c)).toHaveLength(0);
  const confirmar = screen.getByRole("button", { name: "Confirmar apagar contatos" });
  await waitFor(() => expect(document.activeElement).toBe(confirmar));
  const cancelar = within(confirmar.parentElement!).getByRole("button", { name: "Cancelar" });
  fireEvent.click(cancelar);
  await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Apagar contatos" })));
  expect(posts(c)).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "Apagar contatos" }));
  fireEvent.click(await screen.findByRole("button", { name: "Confirmar apagar contatos" }));
  await waitFor(() => expect(posts(c)).toHaveLength(1));
  expect(posts(c)[0]).toMatchObject({ metodo: "DELETE", url: "/api/v1/escuta/contatos" });
});

test("erro ao sincronizar aparece na secao e a lista continua", async () => {
  fake({ contatos: CONTATOS, falha: /sincronizar/ });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Sincronizar agora" }));
  expect((await screen.findAllByText(/Erro: papel inválido/)).length).toBeGreaterThan(0);
  expect(screen.getByRole("checkbox", { name: "Selecionar Ana +5511912345678" })).toBeTruthy();
});

test("contatos com o mesmo nome se distinguem pelo telefone no rotulo da caixa", async () => {
  fake({ contatos: [{ nome: "Ana", telefone: "+5511911111111", contas: [], ja_e_pessoa: false }, { nome: "Ana", telefone: "+5511922222222", contas: [], ja_e_pessoa: false }] });
  montar();
  expect(await screen.findByRole("checkbox", { name: "Selecionar Ana +5511911111111" })).toBeTruthy();
  expect(screen.getByRole("checkbox", { name: "Selecionar Ana +5511922222222" })).toBeTruthy();
});

test("sincronizar mostra as contas que falharam e limpa a selecao", async () => {
  fake({ contatos: CONTATOS, contasFalhas: { "ness@x.com": { erro: "conta não autorizada: ness@x.com" } } });
  montar();
  fireEvent.click(await screen.findByRole("checkbox", { name: "Selecionar Ana +5511912345678" }));
  fireEvent.click(screen.getByRole("button", { name: "Sincronizar agora" }));
  expect(await screen.findByText(/Falharam: ness@x.com \(conta não autorizada: ness@x.com\)/)).toBeTruthy();
  await waitFor(() => expect((screen.getByRole("checkbox", { name: "Selecionar Ana +5511912345678" }) as HTMLInputElement).checked).toBe(false));
});

test.each([["Sincronizar agora", null], ["Apagar contatos", "Confirmar apagar contatos"]])("%s volta para a primeira pagina", async (botao, confirmar) => {
  const c = fake({ contatos: CONTATOS, total: 120 });
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Próxima" }));
  await waitFor(() => expect(c.some((x) => /offset=50/.test(x.url))).toBe(true));
  const antes = c.length;
  fireEvent.click(screen.getByRole("button", { name: botao }));
  if (confirmar) fireEvent.click(await screen.findByRole("button", { name: confirmar }));
  await waitFor(() => expect(c.slice(antes).some((x) => /offset=0/.test(x.url))).toBe(true));
});

test("aprovar um numero que ainda nao escreveu manda telefone, papel e nome para a API", async () => {
  const c = fake();
  montar();
  await assentar();
  fireEvent.change(screen.getByLabelText("Nome do remetente"), { target: { value: "Ana Souza" } });
  fireEvent.change(screen.getByLabelText("Telefone do remetente"), { target: { value: "11 91234-5678" } });
  fireEvent.change(screen.getByLabelText("Papel do remetente"), { target: { value: "prestador" } });
  fireEvent.click(screen.getByRole("button", { name: "Aprovar número" }));
  await assentar();
  const [p] = posts(c);
  expect(p.metodo).toBe("POST");
  expect(decodeURIComponent(p.url)).toContain("/api/v1/escuta/remetentes/11 91234-5678/aprovar");
  expect(p.corpo).toEqual({ papel: "prestador", nome: "Ana Souza" });
});

test("o botao de aprovar numero fica desligado sem telefone", async () => {
  fake();
  montar();
  await assentar();
  expect((screen.getByRole("button", { name: "Aprovar número" }) as HTMLButtonElement).disabled).toBe(true);
});
