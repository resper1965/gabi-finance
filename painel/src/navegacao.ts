/** Navegação (README do handoff). Rótulos copiados literalmente do protótipo. */
export interface Area { id: string; rotulo: string; pergunta: string; abas: [string, string, string?][] }
export interface Grupo { titulo: string | null; areas: Area[] }

export const GRUPOS: Grupo[] = [
  { titulo: "Dia", areas: [
    { id: "hoje", rotulo: "Hoje", pergunta: "O que precisa de mim hoje?", abas: [["hoje", "Hoje", "O que precisa de mim hoje?"]] },
    { id: "envios", rotulo: "Envios", pergunta: "O que espera meu OK para sair?", abas: [["envios", "Envios", "O que espera meu OK para sair?"]] },
  ] },
  { titulo: "Trabalho", areas: [
    { id: "agenda", rotulo: "Agenda", pergunta: "Onde preciso estar?", abas: [["agenda", "Agenda", "Onde preciso estar?"]] },
    { id: "msgs", rotulo: "Mensagens", pergunta: "O que pede resposta?", abas: [["prioridades", "Prioridades", "O que exige ação primeiro?"]] },
  ] },
  { titulo: "Dinheiro", areas: [
    { id: "caixa", rotulo: "Caixa", pergunta: "Tenho caixa? O que vence?", abas: [["visao", "Resumo", "Tenho caixa?"], ["projecao", "Previsão", "Quanto terei em caixa nos próximos dias?"], ["fluxo", "Semanas", "Como o caixa anda, semana a semana?"], ["contas", "A pagar", "O que vence, e quando?"]] },
    { id: "gastos", rotulo: "Gastos", pergunta: "Para onde vai o dinheiro?", abas: [["lanc", "Lançamentos", "De quem é cada gasto?"], ["destino", "Para onde vai", "Para onde vai o dinheiro?"], ["cartao", "Cartões", "Quanto já foi no cartão?"], ["parcelas", "Parcelas", "Quanto já está comprometido?"], ["assin", "Assinaturas", "O que é assinatura esquecida?"]] },
    { id: "cobrar", rotulo: "Cobrar", pergunta: "Quem me deve?", abas: [["areceber", "A receber", "O que vou receber este mês, e o que já entrou?"], ["notas", "Notas a receber", "O que os contratantes me devem pelas notas?"]] },
    { id: "regras", rotulo: "Regras", pergunta: "O que a Gabi sugere classificar?", abas: [["regras", "Regras", "O que a Gabi sugere classificar?"]] },
  ] },
  { titulo: "Casa", areas: [
    { id: "cadastros", rotulo: "Cadastros", pergunta: "O que a Gabi sabe, e o que só você sabe?", abas: [["cadastros", "Cadastros", "O que a Gabi sabe, e o que só você sabe?"], ["documentos", "Documentos", "Que documentos temos e quando vencem?"], ["listacontatos", "Contatos", "Quem está nos meus contatos?"], ["agendas", "Agenda", "Quais agendas a Gabi lê?"], ["correio", "E-mail", "Quais caixas a Gabi lê?"], ["teams", "Teams", "Quais conversas do Teams a Gabi lê?"]] },
    { id: "gabi", rotulo: "Gabi", pergunta: "A Gabi acerta e responde rápido?", abas: [["qualidade", "Qualidade", "A Gabi acerta e responde rápido?"]] },
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
