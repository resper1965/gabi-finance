/** Navegação (README do handoff). Rótulos copiados literalmente do protótipo. */
export interface Area { id: string; rotulo: string; pergunta: string; abas: [string, string][] }
export interface Grupo { titulo: string | null; areas: Area[] }

export const GRUPOS: Grupo[] = [
  { titulo: "Dia", areas: [
    { id: "hoje", rotulo: "Hoje", pergunta: "O que precisa de mim hoje?", abas: [["hoje", "Hoje"]] },
    { id: "temas", rotulo: "Frentes", pergunta: "O que está andando em cada frente?", abas: [["temas", "Frentes"]] },
  ] },
  { titulo: "Trabalho", areas: [
    { id: "agenda", rotulo: "Agenda", pergunta: "Onde preciso estar?", abas: [["agenda", "Agenda"]] },
    { id: "msgs", rotulo: "Mensagens", pergunta: "O que pede resposta?", abas: [["emails", "E-mails"], ["contatos", "Contatos"]] },
    { id: "tarefas", rotulo: "Tarefas", pergunta: "O que eu prometi?", abas: [["tarefas", "Tarefas · Microsoft 365"], ["entregas", "Entregas · Linear"]] },
  ] },
  { titulo: "Dinheiro", areas: [
    { id: "caixa", rotulo: "Caixa", pergunta: "Tenho caixa? O que vence?", abas: [["visao", "Resumo"], ["pedidos", "Pedidos"], ["fluxo", "Semanas"], ["contas", "A pagar"]] },
    { id: "gastos", rotulo: "Gastos", pergunta: "Para onde vai o dinheiro?", abas: [["lanc", "Lançamentos"], ["destino", "Para onde vai"], ["cartao", "Cartões"], ["parcelas", "Parcelas"], ["assin", "Assinaturas"]] },
    { id: "cobrar", rotulo: "Cobrar", pergunta: "Quem me deve?", abas: [["notas", "Notas a receber"], ["reemb", "Reembolsos"], ["docs", "Comprovantes"], ["email", "E-mail de cobrança"]] },
    { id: "regras", rotulo: "Regras", pergunta: "O que a Gabi sugere classificar?", abas: [["regras", "Regras"]] },
  ] },
  { titulo: "Casa", areas: [
    { id: "familia", rotulo: "Família", pergunta: "Como está a saúde de cada um?", abas: [["familia", "Família"]] },
    { id: "cadastros", rotulo: "Cadastros", pergunta: "O que a Gabi sabe, e o que só você sabe?", abas: [["cadastros", "Cadastros"]] },
    { id: "gabi", rotulo: "Gabi", pergunta: "A Gabi está saudável e barata?", abas: [["saude", "Saúde e custo"], ["ingestao", "Ingestão"], ["conectores", "Integrações"], ["seguranca", "Segurança"], ["mcp", "Servidor MCP"], ["receitas", "Receitas"], ["llm", "Modelos"]] },
  ] },
];
export const AREAS = GRUPOS.flatMap((g) => g.areas);
export const AREAS_DINHEIRO = ["caixa", "gastos", "cobrar", "regras"];
