import type { ReactNode } from "react";
import { ArrowRight } from "lucide-react";
import { Etiqueta, type TipoEtiqueta } from "./Etiqueta";
import { useEvidencia, type InfoEvidencia } from "./Evidencia";

export interface Achado extends InfoEvidencia {
  valor: ReactNode;
  prova?: ReactNode;                              // o que sustenta o número (contas, contagens, datas)
  estado?: InfoEvidencia["estado"];
  carimbo?: { tipo: TipoEtiqueta; texto: string }; // fato do achado (vencida, negativa…); vai na linha da prova
  acao?: { rotulo: string; fazer: () => void };
}

/** o carimbo de conferência sai do mesmo estado que pinta o código: um vocabulário só */
const CONFERENCIA = { conferido: ["ok", "conferido"], a_conferir: ["conferir", "a conferir"], projecao: ["nota", "projeção"] } as const;

function Linha({ a }: { a: Achado }) {
  const ev = useEvidencia(a);
  return (
    <tr {...ev.zona} data-item={a.codigo}>
      <td><button {...ev.gatilho} aria-label={`Proveniência do item ${a.codigo}`}><span className="ev-cod">{a.codigo}</span></button>{ev.quadro}</td>
      <td className="achado-texto"><span className="achado-rotulo">{a.rotulo}</span>
        {(a.prova || a.carimbo) && <span className="achado-prova fila" style={{ gap: "2px 8px" }}>{a.prova && <span>{a.prova}</span>}{a.carimbo && <Etiqueta tipo={a.carimbo.tipo} texto={a.carimbo.texto} />}</span>}</td>
      <td className="achado-valor num">{a.valor}</td>
      <td className="achado-estado"><Etiqueta tipo={CONFERENCIA[ev.estado][0]} texto={CONFERENCIA[ev.estado][1]} /></td>
      <td className="achado-acao">{a.acao && <button className="btn btn-ghost btn-sm" onClick={a.acao.fazer}>{a.acao.rotulo}<ArrowRight size={14} strokeWidth={1.8} aria-hidden="true" /></button>}</td>
    </tr>
  );
}

/** Quadro de achados numerados: cada valor-chave da tela com seu código de item (E-01…), o que o sustenta, o carimbo de estado
 *  e, quando houver, a ação. O código abre a cadeia de proveniência (fonte → rodada → conferência). */
export function Achados({ itens, titulo = "Achados", nota, compacto = false }: { itens: Achado[]; titulo?: string; nota?: ReactNode; compacto?: boolean }) {
  const comAcao = itens.some((a) => a.acao);
  return (
    <section className="secao" aria-label={titulo} style={{ maxWidth: 940 }}>
      <table className={`achados${compacto ? " achados-compacto" : ""}`}>
        <caption className="sr-only">{titulo}</caption>
        <thead>
          <tr><th scope="col">Item</th><th scope="col">{titulo}{nota && <span className="secao-nota" style={{ fontWeight: 400, marginLeft: 10 }}>{nota}</span>}</th><th scope="col" className="direita">Valor</th><th scope="col">Conferência</th><th scope="col">{comAcao ? <span className="sr-only">Ação</span> : null}</th></tr>
        </thead>
        <tbody>{itens.map((a) => <Linha key={a.codigo} a={a} />)}</tbody>
      </table>
    </section>
  );
}
