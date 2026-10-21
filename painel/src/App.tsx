import type { ReactNode } from "react";
import { Shell, type Contagens } from "./componentes/Shell";
import { Seletores } from "./componentes/Seletores";
import { Vazio } from "./componentes/Estados";
import { Limite } from "./componentes/Limite";
import { FiltrosProvider } from "./lib/filtros";
import { ToastProvider } from "./lib/toast";
import { useApi } from "./lib/useApi";
import { AREAS_DINHEIRO, type Area } from "./navegacao";
import { Resumo } from "./telas/Caixa/Resumo";
import { Semanas } from "./telas/Caixa/Semanas";
import { APagar } from "./telas/Caixa/APagar";
import { Pedidos } from "./telas/Caixa/Pedidos";
import { Reembolsos } from "./telas/Cobrar/Reembolsos";
import { Comprovantes } from "./telas/Cobrar/Comprovantes";
import { EmailCobranca } from "./telas/Cobrar/EmailCobranca";
import { Lancamentos } from "./telas/Gastos/Lancamentos";
import { ParaOndeVai } from "./telas/Gastos/ParaOndeVai";
import { Cartoes } from "./telas/Gastos/Cartoes";
import { Parcelas } from "./telas/Gastos/Parcelas";
import { Assinaturas } from "./telas/Gastos/Assinaturas";
import { Regras } from "./telas/Regras";
import { Cadastros } from "./telas/Cadastros";
import { CadastrosContatos } from "./telas/CadastrosContatos";
import { CadastrosAgenda } from "./telas/CadastrosAgenda";
import { CadastrosTeams } from "./telas/CadastrosTeams";
import { CadastrosCorreio } from "./telas/CadastrosCorreio";
import { Prioridades } from "./telas/Trabalho/Prioridades";
import { Hoje } from "./telas/Trabalho/Hoje";
import { Frentes } from "./telas/Trabalho/Frentes";
import { Agenda } from "./telas/Trabalho/Agenda";
import { Mensagens } from "./telas/Trabalho/Mensagens";
import { Tarefas } from "./telas/Trabalho/Tarefas";
import { Entregas } from "./telas/Trabalho/Entregas";
import { Configuracao } from "./telas/Configuracao";
import { Familia } from "./telas/Familia";
import { Reembolso } from "./telas/Reembolso";
import { Avisos } from "./componentes/Avisos";
import { Projecao } from "./telas/Caixa/Projecao";
import { Qualidade } from "./telas/Gabi/Qualidade";
import { NotasAReceber } from "./telas/Cobrar/NotasAReceber";
import { AReceber } from "./telas/Cobrar/AReceber";

const TELAS: Record<string, () => ReactNode> = {
  visao: Resumo, projecao: Projecao, areceber: AReceber, notas: NotasAReceber, fluxo: Semanas, contas: APagar, pedidos: Pedidos, reemb: Reembolsos, docs: Comprovantes, email: EmailCobranca,
  lanc: Lancamentos, destino: ParaOndeVai, cartao: Cartoes, parcelas: Parcelas, assin: Assinaturas,
  regras: Regras, cadastros: Cadastros, listacontatos: CadastrosContatos, agendas: CadastrosAgenda, teams: CadastrosTeams, correio: CadastrosCorreio, prioridades: Prioridades, setup: Configuracao,
  qualidade: Qualidade, hoje: Hoje, temas: Frentes, familia: Familia, reembolso: Reembolso, agenda: Agenda, emails: Mensagens, tarefas: Tarefas, entregas: Entregas,
};

function tela(area: Area, aba: string) {
  const T = TELAS[aba];
  return T ? <Limite key={aba} arquivo={`${area.rotulo} / ${aba}`}><T /></Limite> : <Vazio frase={`${area.rotulo} ainda não foi construída nesta fase.`} />;
}

export function App() {
  const leituraContagens = useApi<Contagens>("/api/v1/contagens");
  const contagens = leituraContagens.env?.dados;
  return (
    <ToastProvider>
      <FiltrosProvider>
        <Shell tela={tela} contagens={contagens} avisos={<Avisos aoMudar={leituraContagens.recarregar} />} seletores={(a, celular) => (AREAS_DINHEIRO.includes(a.id) && a.id !== "regras" ? <Seletores celular={celular} /> : null)} />
      </FiltrosProvider>
    </ToastProvider>
  );
}
