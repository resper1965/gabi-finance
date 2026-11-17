import type { ReactNode } from "react";
import { Inbox } from "lucide-react";
import { Etiqueta } from "./Etiqueta";

/** Carregando: esqueleto pautado no lugar do conteúdo e qual arquivo está sendo lido. */
export function Carregando({ arquivo }: { arquivo?: string }) {
  return (
    <div role="progressbar" aria-busy="true" aria-label="Carregando" className="esqueleto">
      <span className="esqueleto-linha" data-forte style={{ width: "46%" }} />
      <span className="esqueleto-linha" />
      <span className="esqueleto-linha" style={{ width: "88%" }} />
      <span className="esqueleto-linha" style={{ width: "72%" }} />
      <span className="esqueleto-linha" style={{ width: "80%" }} />
      {arquivo && <span className="esqueleto-rotulo">lendo {arquivo}</span>}
    </div>
  );
}

/** Vazio: o que a tela mostraria e o que fazer para aparecer algo. */
export function Vazio({ frase, children }: { frase: string; children?: ReactNode }) {
  return <div className="vazio"><Inbox size={18} strokeWidth={1.6} aria-hidden="true" /><span>{frase}{children}</span></div>;
}

/** Erro: arquivo, motivo e a garantia de que os últimos dados bons continuam guardados. */
export function Erro({ arquivo, motivo }: { arquivo: string; motivo: string }) {
  return (
    <div role="alert" className="erro-caixa">
      <span className="fila"><Etiqueta tipo="erro" texto="Erro" /><span className="mono">{arquivo}</span></span>
      <span>{motivo}</span>
      <span className="miudo">Os últimos dados bons continuam guardados.</span>
    </div>
  );
}
