import type { CSSProperties, ReactNode } from "react";

/** Seção do laudo: título com régua de tinta embaixo, nota à direita e o conteúdo solto no papel (sem cartão). */
export function Bloco({ titulo, nota, acao, children, style, rotulo }: {
  titulo?: string; nota?: ReactNode; acao?: ReactNode; children: ReactNode; style?: CSSProperties; rotulo?: string;
}) {
  return (
    <section className="secao" style={style} aria-label={rotulo}>
      {(titulo || nota || acao) && (
        <div className="secao-cab">
          {titulo && <h2>{titulo}</h2>}
          {(nota || acao) && <span className="fila">{nota && <span className="secao-nota">{nota}</span>}{acao}</span>}
        </div>
      )}
      {children}
    </section>
  );
}
