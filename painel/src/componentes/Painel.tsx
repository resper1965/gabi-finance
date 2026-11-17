import type { ReactNode } from "react";
import type { Leitura } from "../lib/useApi";
import { ProvContext } from "../lib/proveniencia";
import { Faixa } from "./Faixa";
import { Carregando, Erro } from "./Estados";

/** Moldura de todo painel: faixa de proveniência + os quatro estados (carregando, erro com últimos dados bons, desatualizado, ok).
 *  O envelope vira contexto: toda etiqueta de evidência da tela lê dele a fonte, a rodada e a conferência. */
export function Painel<T>({ leitura, arquivo, children }: { leitura: Leitura<T>; arquivo: string; children: (dados: T) => ReactNode }) {
  const { env, estado, erro } = leitura;
  if (!env) {
    return estado === "erro"
      ? <Erro arquivo={arquivo} motivo={erro?.message ?? "erro"} />
      : <Carregando arquivo={arquivo} />;
  }
  const parada = env.fontes.find((f) => f.estado !== "ok");
  return (
    <ProvContext.Provider value={{ dadosAte: env.dados_ate, desatualizado: env.desatualizado, fontes: env.fontes, proximaRodada: env.proxima_rodada }}>
      <Faixa dadosAte={env.dados_ate} desatualizado={env.desatualizado} fonte={parada?.nome} proximaRodada={env.proxima_rodada} fontes={env.fontes} />
      {estado === "erro" && <Erro arquivo={arquivo} motivo={erro?.message ?? "erro"} />}
      {children(env.dados)}
    </ProvContext.Provider>
  );
}
