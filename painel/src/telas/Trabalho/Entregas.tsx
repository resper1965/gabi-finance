import { Painel } from "../../componentes/Painel";
import { dataCurta } from "../../lib/formato";
import { useApi } from "../../lib/useApi";

interface Entrega { id: number; identificador: string; titulo: string; projeto: string | null; responsavel: string | null; prazo: string | null; estado: string }

/** Entregas da Linear: só leitura (nada daqui escreve na Linear). */
export function Entregas() {
  const leitura = useApi<{ itens: Entrega[] }>("/api/v1/entregas");
  return (
    <Painel leitura={leitura} arquivo="entregas">
      {(d) => (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {d.itens.length === 0 && <p style={{ color: "var(--ink2)" }}>Nenhuma entrega aberta (ou a Linear ainda não está conectada).</p>}
          {d.itens.map((e) => (
            <div key={e.id} data-entrega style={{ display: "flex", gap: 10, alignItems: "baseline", border: "1px solid var(--color-divider)", padding: "8px 12px" }}>
              <code style={{ font: "600 12.5px var(--mono)" }}>{e.identificador}</code>
              <span>{e.titulo}</span>
              <small style={{ marginLeft: "auto", color: "var(--ink2)" }}>{[e.projeto, e.responsavel, e.estado].filter(Boolean).join(" · ")}{e.prazo ? ` · vence ${dataCurta(e.prazo.slice(0, 10))}` : ""}</small>
            </div>))}
        </div>
      )}
    </Painel>
  );
}
