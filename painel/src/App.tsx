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
import { Lancamentos } from "./telas/Gastos/Lancamentos";
import { ParaOndeVai } from "./telas/Gastos/ParaOndeVai";
import { Cartoes } from "./telas/Gastos/Cartoes";
import { Parcelas } from "./telas/Gastos/Parcelas";
import { Assinaturas } from "./telas/Gastos/Assinaturas";
import { Regras } from "./telas/Regras";
import { Cadastros } from "./telas/Cadastros";
import { CadastrosDespesas } from "./telas/CadastrosDespesas";
import { Avisos } from "./componentes/Avisos";
import { Projecao } from "./telas/Caixa/Projecao";
import { Agentes } from "./telas/Gabi/Agentes";
import { NotasAReceber } from "./telas/Cobrar/NotasAReceber";
import { AReceber } from "./telas/Cobrar/AReceber";

export const TELAS: Record<string, () => ReactNode> = {
  contas: APagar, projecao: Projecao, fluxo: Semanas, visao: Resumo,
  lanc: Lancamentos, destino: ParaOndeVai, cartao: Cartoes, parcelas: Parcelas, assin: Assinaturas,
  areceber: AReceber, notas: NotasAReceber,
  regras: Regras, cadastros: Cadastros, despesas: CadastrosDespesas,
  agentes: Agentes,
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
