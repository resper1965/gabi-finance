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
import { Hoje } from "./telas/Trabalho/Hoje";
import { Frentes } from "./telas/Trabalho/Frentes";
import { Agenda } from "./telas/Trabalho/Agenda";
import { Mensagens } from "./telas/Trabalho/Mensagens";
import { Tarefas } from "./telas/Trabalho/Tarefas";

const TELAS: Record<string, () => ReactNode> = {
  visao: Resumo, fluxo: Semanas, contas: APagar, pedidos: Pedidos, reemb: Reembolsos, docs: Comprovantes, email: EmailCobranca,
  lanc: Lancamentos, destino: ParaOndeVai, cartao: Cartoes, parcelas: Parcelas, assin: Assinaturas,
  regras: Regras, cadastros: Cadastros,
  hoje: Hoje, temas: Frentes, agenda: Agenda, emails: Mensagens, tarefas: Tarefas,
};

function tela(area: Area, aba: string) {
  const T = TELAS[aba];
  return T ? <Limite key={aba} arquivo={`${area.rotulo} / ${aba}`}><T /></Limite> : <Vazio frase={`${area.rotulo} ainda não foi construída nesta fase.`} />;
}

export function App() {
  const contagens = useApi<Contagens>("/api/v1/contagens").env?.dados;
  return (
    <ToastProvider>
      <FiltrosProvider>
        <Shell tela={tela} contagens={contagens} seletores={(a, celular) => (AREAS_DINHEIRO.includes(a.id) && a.id !== "regras" ? <Seletores celular={celular} /> : null)} />
      </FiltrosProvider>
    </ToastProvider>
  );
}
