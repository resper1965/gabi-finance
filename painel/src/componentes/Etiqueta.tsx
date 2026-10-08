export type TipoEtiqueta =
  | "erro" | "conferir" | "ok" | "atencao" | "parado" | "regra" | "banco" | "paperless" | "ajuste";

const GLIFO: Record<TipoEtiqueta, string> = {
  erro: "!", conferir: "?", ok: "✓", atencao: "▲", parado: "◷",
  regra: "⚙", banco: "◇", paperless: "▣", ajuste: "⇄",
};
const COR: Record<TipoEtiqueta, [string, string]> = {
  erro: ["var(--danger)", "var(--danger-bg)"],
  conferir: ["var(--warn)", "var(--warn-bg)"],
  ok: ["var(--ok)", "var(--ok-bg)"],
  atencao: ["var(--warn)", "var(--warn-bg)"],
  parado: ["var(--ink2)", "var(--color-neutral-100)"],
  regra: ["var(--ink2)", "var(--color-neutral-100)"],
  banco: ["var(--ink2)", "var(--color-neutral-100)"],
  paperless: ["var(--ink2)", "var(--color-neutral-100)"],
  ajuste: ["var(--ink2)", "var(--color-neutral-100)"],
};

/** Etiqueta: cor nunca é a única informação, então sempre glifo + texto. Raio 0. */
export function Etiqueta({ tipo, texto }: { tipo: TipoEtiqueta; texto: string }) {
  const [cor, fundo] = COR[tipo];
  return (
    <span
      data-tipo={tipo}
      style={{ display: "inline-flex", gap: 5, alignItems: "center", padding: "1px 7px", border: `1px solid ${cor}`, background: fundo, color: cor, font: "600 11px/1.5 var(--font-body)" }}
    >
      <span aria-hidden="true">{GLIFO[tipo]}</span>
      {texto}
    </span>
  );
}
