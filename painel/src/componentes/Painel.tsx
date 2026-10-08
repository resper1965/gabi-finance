import type { ReactNode } from "react";
import type { Leitura } from "../lib/useApi";
import { Faixa } from "./Faixa";
import { Carregando, Erro } from "./Estados";

/** Moldura de todo painel: faixa de dados + os quatro estados (carregando, erro com últimos dados bons, desatualizado, ok). */
export function Painel<T>({ leitura, arquivo, children }: { leitura: Leitura<T>; arquivo: string; children: (dados: T) => ReactNode }) {
  const { env, estado, erro } = leitura;
  if (!env) {
    return estado === "erro"
      ? <Erro arquivo={arquivo} motivo={erro?.message ?? "erro"} />
      : <Carregando arquivo={arquivo} />;
  }
  const parada = env.fontes.find((f) => f.estado !== "ok");
  return (
    <>
      <Faixa dadosAte={env.dados_ate} desatualizado={env.desatualizado} fonte={parada?.nome} />
      {estado === "erro" && <Erro arquivo={arquivo} motivo={erro?.message ?? "erro"} />}
      {children(env.dados)}
    </>
  );
}
