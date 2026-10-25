import { useState, type ReactNode } from "react";
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
import { CadastrosDocumentos } from "./telas/CadastrosDocumentos";
import { CadastrosContatos } from "./telas/CadastrosContatos";
import { CadastrosAgenda } from "./telas/CadastrosAgenda";
import { CadastrosTeams } from "./telas/CadastrosTeams";
import { CadastrosCorreio } from "./telas/CadastrosCorreio";
import { Prioridades } from "./telas/Trabalho/Prioridades";
import { Hoje } from "./telas/Trabalho/Hoje";
import { Agenda } from "./telas/Trabalho/Agenda";
import { Envios } from "./telas/Envios";
import { Avisos } from "./componentes/Avisos";
import { Projecao } from "./telas/Caixa/Projecao";
import { Qualidade } from "./telas/Gabi/Qualidade";
import { NotasAReceber } from "./telas/Cobrar/NotasAReceber";
import { AReceber } from "./telas/Cobrar/AReceber";

export const TELAS: Record<string, () => ReactNode> = {
  visao: Resumo, projecao: Projecao, areceber: AReceber, notas: NotasAReceber, fluxo: Semanas, contas: APagar,
  lanc: Lancamentos, destino: ParaOndeVai, cartao: Cartoes, parcelas: Parcelas, assin: Assinaturas,
  regras: Regras, cadastros: Cadastros, documentos: CadastrosDocumentos, listacontatos: CadastrosContatos, agendas: CadastrosAgenda, teams: CadastrosTeams, correio: CadastrosCorreio, prioridades: Prioridades,
  qualidade: Qualidade, hoje: Hoje, agenda: Agenda, envios: Envios,
};

function tela(area: Area, aba: string) {
  const T = TELAS[aba];
  return T ? <Limite key={aba} arquivo={`${area.rotulo} / ${aba}`}><T /></Limite> : <Vazio frase={`${area.rotulo} ainda não foi construída nesta fase.`} />;
}

/** Links antigos (o brain mandava #cadastros/familia antes da aba Documentos) abrem a aba nova; roda antes do Shell ler a URL. */
const LINKS_ANTIGOS: Record<string, string> = { "#cadastros/familia": "#cadastros/documentos" };
function redirecionarLinkAntigo(): null {
  const novo = LINKS_ANTIGOS[window.location.hash];
  if (novo) window.history.replaceState(null, "", novo);
  return null;
}

export function App() {
  useState(redirecionarLinkAntigo);
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
