export interface FaixaProps {
  dadosAte: string | null; // ISO; vem do envelope (última rodada CONFERIDA)
  desatualizado?: boolean;
  fonte?: string; // qual fonte parou
}

const dois = (n: number) => String(n).padStart(2, "0");
export function formatarDadosAte(iso: string): string {
  const d = new Date(iso);
  return `${dois(d.getDate())}/${dois(d.getMonth() + 1)} ${dois(d.getHours())}:${dois(d.getMinutes())}`;
}

/** Faixa "dados até DD/MM hh:mm" no topo de todo painel; amarela e com a fonte quando desatualizado. */
export function Faixa({ dadosAte, desatualizado, fonte }: FaixaProps) {
  return (
    <div
      role="status"
      data-estado={desatualizado ? "desatualizado" : "ok"}
      style={{
        padding: "6px 14px", font: "500 12px/1.4 var(--mono)",
        background: desatualizado ? "var(--warn-bg)" : "transparent",
        color: desatualizado ? "var(--warn)" : "var(--ink2)",
        borderBottom: "1px solid var(--color-divider)",
      }}
    >
      {dadosAte ? `dados até ${formatarDadosAte(dadosAte)}` : "sem dados conferidos ainda"}
      {desatualizado && fonte ? ` · ${fonte} parou` : ""}
    </div>
  );
}
