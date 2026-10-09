import { Painel } from "../../componentes/Painel";
import { useApi } from "../../lib/useApi";

interface Rascunho { id: number; empresa_id: string; para: string; assunto: string; criado_em: string; itens: number }

const MOTIVO = "O envio está desabilitado: o app só guarda o rascunho (ADR-006). Copie para o seu e-mail e envie de lá.";

/** Cobrar › E-mail de cobrança: os rascunhos guardados. Nada é enviado por aqui; o botão fica desabilitado e diz o motivo. */
export function EmailCobranca() {
  const leitura = useApi<{ itens: Rascunho[] }>("/api/v1/cobrar/cobrancas");
  return (
    <Painel leitura={leitura} arquivo="rascunhos de cobrança">
      {(d) => (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {d.itens.length === 0 && <div style={{ border: "1px dashed var(--line3)", padding: 18, color: "var(--ink2)" }}>Gabi: nenhum rascunho. Em Reembolsos, escolha os itens e toque em “Preparar e-mail”.</div>}
          {d.itens.map((r) => (
            <div key={r.id} data-rascunho style={{ border: "1px solid var(--color-divider)", padding: "12px 14px", display: "flex", flexDirection: "column", gap: 6 }}>
              <span style={{ font: "600 10.5px var(--font-body)", letterSpacing: ".08em", textTransform: "uppercase", color: "var(--ink2)" }}>Rascunho · {r.itens} itens</span>
              <strong>{r.assunto}</strong>
              <span style={{ fontSize: 13, color: "var(--ink2)" }}>Para {r.para}</span>
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <button className="btn btn-primary" disabled aria-describedby={`motivo-${r.id}`}>Enviar</button>
                <span id={`motivo-${r.id}`} style={{ fontSize: 12.5, color: "var(--ink2)" }}>{MOTIVO}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </Painel>
  );
}
