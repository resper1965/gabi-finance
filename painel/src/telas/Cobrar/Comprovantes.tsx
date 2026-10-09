import { Etiqueta } from "../../componentes/Etiqueta";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { api } from "../../lib/api";
import { dataCurta } from "../../lib/formato";
import { useToast } from "../../lib/toast";
import { useApi } from "../../lib/useApi";

interface Candidato {
  vinculo_id: number; confianca: number; motivo: string;
  comprovante: { paperless_id: number; tipo: string; valor: string; data: string };
  lancamento: { id: number; data: string; descricao: string | null; valor: string; empresa: string | null };
}
interface Sem { id: number; data: string; descricao: string | null; valor: string; empresa_id: string | null }

/** Cobrar › Comprovantes: o que o Paperless já tem. A Gabi propõe o vínculo com a confiança e o motivo; só o Ricardo confirma. */
export function Comprovantes() {
  const leitura = useApi<{ candidatos: Candidato[]; sem_comprovante: Sem[] }>("/api/v1/cobrar/comprovantes");
  const avisar = useToast();
  const decidir = async (id: number, acao: "confirmar" | "rejeitar") => {
    try { await api.post(acao === "confirmar" ? `/api/v1/cobrar/vinculos/${id}/confirmar` : `/api/v1/cobrar/vinculos/${id}/rejeitar`); avisar(acao === "confirmar" ? "Vínculo confirmado por você." : "Vínculo rejeitado."); leitura.recarregar(); }
    catch (e) { avisar((e as Error).message); }
  };
  return (
    <Painel leitura={leitura} arquivo="comprovantes">
      {(d) => (
        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          <span style={{ fontSize: 12.5, color: "var(--ink2)" }}>A Gabi só lê o Paperless e grava etiquetas (empresa, "reembolso", "para quem"). Não apaga nem move documentos.</span>
          <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <h3 style={{ margin: 0, fontSize: 20 }}>Confirme o vínculo · {d.candidatos.length}</h3>
            {d.candidatos.length === 0 && <div style={{ border: "1px dashed var(--line3)", padding: 16, color: "var(--ink2)" }}>Tudo vinculado. Os comprovantes já vão anexados nos e-mails de cobrança.</div>}
            {d.candidatos.map((c) => (
              <div key={c.vinculo_id} data-vinculo style={{ border: "1px solid var(--color-divider)", display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,260px),1fr))" }}>
                <div style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: 6, borderRight: "1px solid var(--line2)" }}>
                  <span style={{ font: "600 10.5px var(--font-body)", letterSpacing: ".08em", textTransform: "uppercase", color: "var(--ink2)" }}>No Paperless · #{c.comprovante.paperless_id}</span>
                  <span style={{ fontWeight: 600 }}>{c.comprovante.tipo === "comprovante_pix" ? "Comprovante Pix" : c.comprovante.tipo}</span>
                  <span style={{ fontSize: 13 }}><strong style={{ fontVariantNumeric: "tabular-nums" }}><Valor valor={c.comprovante.valor} /></strong> · {dataCurta(c.comprovante.data)}</span>
                </div>
                <div style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: 6 }}>
                  <span style={{ font: "600 10.5px var(--font-body)", letterSpacing: ".08em", textTransform: "uppercase", color: "var(--ink2)" }}>Lançamento{c.lancamento.empresa ? ` · reembolso ${c.lancamento.empresa}` : ""}</span>
                  <span style={{ fontWeight: 600 }}>{c.lancamento.descricao}</span>
                  <span style={{ fontSize: 13 }}><strong style={{ fontVariantNumeric: "tabular-nums" }}><Valor valor={c.lancamento.valor} /></strong> · {dataCurta(c.lancamento.data)}</span>
                  <span style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--ink2)" }}>
                    <span style={{ width: 60, height: 4, background: "var(--line2)" }}><span style={{ display: "block", height: "100%", width: `${Math.round(c.confianca * 100)}%`, background: c.confianca >= 0.8 ? "var(--ok)" : "var(--warn)" }} /></span>
                    <strong style={{ color: "var(--color-text)" }}>{Math.round(c.confianca * 100)}%</strong> · {c.motivo}
                  </span>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <button className="btn btn-primary" onClick={() => decidir(c.vinculo_id, "confirmar")}>Confirmar vínculo</button>
                    <button className="btn btn-secondary" onClick={() => decidir(c.vinculo_id, "rejeitar")}>Não é esse</button>
                  </div>
                </div>
              </div>
            ))}
          </section>
          <section style={{ display: "flex", flexDirection: "column" }}>
            <h3 style={{ margin: "0 0 6px", fontSize: 20 }}>Sem comprovante · {d.sem_comprovante.length}</h3>
            {d.sem_comprovante.map((x) => (
              <div key={x.id} style={{ display: "grid", gridTemplateColumns: "70px minmax(0,1fr) auto auto", gap: 10, padding: "9px 0", borderTop: "1px solid var(--line2)", alignItems: "center" }}>
                <span style={{ font: "500 12.5px var(--mono)" }}>{dataCurta(x.data)}</span><span>{x.descricao}</span>
                <Etiqueta tipo="atencao" texto="sem comprovante" /><span style={{ fontVariantNumeric: "tabular-nums" }}><Valor valor={x.valor} /></span>
              </div>
            ))}
          </section>
        </div>
      )}
    </Painel>
  );
}
