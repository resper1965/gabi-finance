import type { ReactNode } from "react";
import { Etiqueta } from "./Etiqueta";

const caixa = { padding: 20, border: "1px solid var(--color-divider)", background: "var(--color-surface)" } as const;

/** Carregando: blocos listrados e o arquivo sendo lido. */
export function Carregando({ arquivo }: { arquivo?: string }) {
  return (
    <div role="progressbar" aria-busy="true" aria-label="Carregando" style={caixa}>
      <div style={{ height: 14, marginBottom: 8, background: "repeating-linear-gradient(45deg,var(--stripe) 0 6px,transparent 6px 12px)" }} />
      <div style={{ height: 14, width: "60%", background: "repeating-linear-gradient(45deg,var(--stripe) 0 6px,transparent 6px 12px)" }} />
      {arquivo && <div style={{ marginTop: 10, font: "500 11.5px var(--mono)", color: "var(--ink2)" }}>lendo {arquivo}</div>}
    </div>
  );
}

/** Vazio: frase da Gabi dizendo o que fazer. */
export function Vazio({ frase }: { frase: string }) {
  return <div style={caixa}><span style={{ color: "var(--ink2)" }}>Gabi: </span>{frase}</div>;
}

/** Erro: arquivo, motivo e a garantia de que os últimos dados bons continuam guardados. */
export function Erro({ arquivo, motivo }: { arquivo: string; motivo: string }) {
  return (
    <div role="alert" style={{ ...caixa, borderColor: "var(--danger)", background: "var(--danger-bg)" }}>
      <Etiqueta tipo="erro" texto="Erro" />
      <div style={{ marginTop: 8, font: "500 12px var(--mono)" }}>{arquivo}</div>
      <div>{motivo}</div>
      <div style={{ color: "var(--ink2)", marginTop: 6 }}>Os últimos dados bons continuam guardados.</div>
    </div>
  );
}

/** Desatualizado: o painel continua, com aviso de qual fonte parou. */
export function Desatualizado({ fonte, children }: { fonte: string; children?: ReactNode }) {
  return (
    <div style={{ ...caixa, borderColor: "var(--warn)", background: "var(--warn-bg)" }}>
      <Etiqueta tipo="parado" texto={`${fonte} parou`} />
      {children}
    </div>
  );
}
