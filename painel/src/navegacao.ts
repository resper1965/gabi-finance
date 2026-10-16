/** Navegação (README do handoff). Rótulos copiados literalmente do protótipo. */
export interface Area { id: string; rotulo: string; pergunta: string; abas: [string, string, string?][] }
export interface Grupo { titulo: string | null; areas: Area[] }

export const GRUPOS: Grupo[] = [
  { titulo: "Dia", areas: [
    { id: "hoje", rotulo: "Hoje", pergunta: "O que precisa de mim hoje?", abas: [["hoje", "Hoje", "O que precisa de mim hoje?"]] },
    { id: "temas", rotulo: "Frentes", pergunta: "O que está andando em cada frente?", abas: [["temas", "Frentes", "O que está andando em cada frente?"]] },
  ] },
  { titulo: "Trabalho", areas: [
    { id: "agenda", rotulo: "Agenda", pergunta: "Onde preciso estar?", abas: [["agenda", "Agenda", "Onde preciso estar?"]] },
    { id: "msgs", rotulo: "Mensagens", pergunta: "O que pede resposta?", abas: [["prioridades", "Prioridades", "O que exige ação primeiro?"], ["emails", "E-mails", "O que pede resposta?"], ["contatos", "Contatos", "Com quem tenho algo em aberto?"]] },
    { id: "tarefas", rotulo: "Tarefas", pergunta: "O que eu prometi?", abas: [["tarefas", "Tarefas · Microsoft 365", "O que eu prometi?"], ["entregas", "Entregas · Linear", "O que vence nos projetos?"]] },
  ] },
  { titulo: "Dinheiro", areas: [
    { id: "caixa", rotulo: "Caixa", pergunta: "Tenho caixa? O que vence?", abas: [["visao", "Resumo", "Tenho caixa?"], ["projecao", "Previsão", "Quanto terei em caixa nos próximos dias?"], ["pedidos", "Pedidos", "O que me pediram para pagar?"], ["fluxo", "Semanas", "Como o caixa anda, semana a semana?"], ["contas", "A pagar", "O que vence, e quando?"]] },
    { id: "gastos", rotulo: "Gastos", pergunta: "Para onde vai o dinheiro?", abas: [["lanc", "Lançamentos", "De quem é cada gasto?"], ["destino", "Para onde vai", "Para onde vai o dinheiro?"], ["cartao", "Cartões", "Quanto já foi no cartão?"], ["parcelas", "Parcelas", "Quanto já está comprometido?"], ["assin", "Assinaturas", "O que é assinatura esquecida?"]] },
    { id: "cobrar", rotulo: "Cobrar", pergunta: "Quem me deve?", abas: [["notas", "Notas a receber", "O que os contratantes me devem pelas notas?"], ["reemb", "Reembolsos", "Quem me deve?"], ["docs", "Comprovantes", "O que o Paperless já tem?"], ["email", "E-mail de cobrança", "O que vou cobrar, e de quem?"]] },
    { id: "regras", rotulo: "Regras", pergunta: "O que a Gabi sugere classificar?", abas: [["regras", "Regras", "O que a Gabi sugere classificar?"]] },
  ] },
  { titulo: "Casa", areas: [
    { id: "familia", rotulo: "Família", pergunta: "Como está a saúde de cada um?", abas: [["familia", "Família"], ["reembolso", "Reembolso de saúde", "Quais reembolsos de saúde faltam pedir?"]] },
    { id: "cadastros", rotulo: "Cadastros", pergunta: "O que a Gabi sabe, e o que só você sabe?", abas: [["cadastros", "Cadastros", "O que a Gabi sabe, e o que só você sabe?"], ["escuta", "Escuta", "Quem a Gabi escuta no WhatsApp?"], ["agendas", "Agenda", "Quais agendas a Gabi lê?"], ["correio", "E-mail", "Quais caixas a Gabi lê?"], ["setup", "Configuração", "Está tudo conectado?"]] },
    { id: "gabi", rotulo: "Gabi", pergunta: "A Gabi está saudável e barata?", abas: [["saude", "Saúde e custo", "A Gabi está saudável e barata?"], ["ingestao", "Ingestão", "Os dados chegaram certos?"], ["conectores", "Integrações", "De onde a Gabi lê?"], ["seguranca", "Segurança", "Quem entra, por onde, e com quê?"], ["mcp", "Servidor MCP", "O que agentes externos podem fazer?"], ["receitas", "Receitas", "Como conecto meu agente?"], ["llm", "Modelos", "Quem classifica, e quanto custa?"], ["qualidade", "Qualidade", "A Gabi acerta e responde rápido?"]] },
  ] },
];
export const AREAS = GRUPOS.flatMap((g) => g.areas);
export const AREAS_DINHEIRO = ["caixa", "gastos", "cobrar", "regras"];

/** A API devolve "rota" nos itens de atenção (ex.: "/caixa/a-pagar"); isto traduz para [área, aba]. */
export function rotaParaTela(rota: string): [string, string?] {
  if (rota.startsWith("/caixa/a-pagar")) return ["caixa", "contas"];
  if (rota.startsWith("/regras")) return ["regras"];
  if (rota.startsWith("/cadastros")) return ["cadastros"];
  return ["hoje"];
}
