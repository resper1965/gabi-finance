import { useState } from "react";
import { Etiqueta } from "../../componentes/Etiqueta";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { api } from "../../lib/api";
import { dataCurta } from "../../lib/formato";
import { useToast } from "../../lib/toast";
import { useApi } from "../../lib/useApi";

interface Pedido {
  id: number; solicitante: string; canal: string; descricao: string; valor: string | null; vencimento: string | null; pix_chave: string | null;
  anexo_paperless_id: number | null; estado: string; mensagem_original: string; criado_em: string; decidido_em: string | null;
}
interface Item { id: number | string; nome?: string; apelido?: string; estado?: string | null }

/** Caixa › Pedidos: o que me pediram para pagar. A Gabi só registra; aprovar, pedir informação e recusar são do Ricardo. */
export function Pedidos() {
  const pendentes = useApi<{ itens: Pedido[] }>("/api/v1/cobrar/pedidos");
  const decididos = useApi<{ itens: Pedido[] }>("/api/v1/cobrar/pedidos?estado=decididos");
  const contas = (useApi<{ itens: Item[] }>("/api/v1/cadastros/contas").env?.dados.itens ?? []).filter((c) => c.estado === "sim");
  const pessoas = useApi<{ itens: Item[] }>("/api/v1/cadastros/pessoas").env?.dados.itens ?? [];
  const avisar = useToast();
  const [conta, setConta] = useState<Record<number, string>>({});
  const [ben, setBen] = useState<Record<number, string>>({});
  const recarregar = () => { pendentes.recarregar(); decididos.recarregar(); };
  const decidir = async (p: Pedido, acao: "aprovar" | "recusar" | "pedir_info") => {
    if (acao === "aprovar" && (!conta[p.id] || !ben[p.id])) { avisar("Escolha a conta e o beneficiário antes de aprovar."); return; }
    try {
      await api.post(`/api/v1/cobrar/pedidos/${p.id}/decidir`, acao === "aprovar" ? { acao, conta_id: Number(conta[p.id]), beneficiario_id: ben[p.id] } : { acao });
      avisar(acao === "aprovar" ? "Aprovado: entrou na fila de contas a pagar." : acao === "recusar" ? "Pedido recusado." : "Pedi mais informação ao solicitante.");
      recarregar();
    } catch (e) { avisar((e as Error).message); }
  };
  const seletor = { height: 30, border: "1px solid var(--line3)", background: "var(--raised)", color: "var(--color-text)", font: "600 12.5px var(--font-body)", padding: "0 4px" } as const;
  return (
    <Painel leitura={pendentes} arquivo="pedidos">
      {(d) => (
        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <h3 style={{ margin: 0, fontSize: 20 }}>Pedidos · {d.itens.length} pendentes</h3>
            {d.itens.length === 0 && <div style={{ border: "1px dashed var(--line3)", padding: 18, color: "var(--ink2)" }}>Gabi: nenhum pedido esperando. Quando alguém pedir um pagamento pelo canal, ele aparece aqui.</div>}
            {d.itens.map((p) => (
              <div key={p.id} data-pedido style={{ border: "1px solid var(--color-divider)", padding: "12px 14px", display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
                  <strong style={{ font: "600 20px/1.15 var(--font-heading)" }}>{p.descricao}</strong>
                  {p.valor && <span style={{ font: "600 22px var(--font-heading)", fontVariantNumeric: "tabular-nums" }}><Valor valor={p.valor} /></span>}
                </div>
                <span style={{ fontSize: 13, color: "var(--ink2)" }}>{p.solicitante} · via {p.canal}{p.vencimento ? ` · vence ${dataCurta(p.vencimento)}` : ""}{p.pix_chave ? ` · Pix ${p.pix_chave}` : ""}</span>
                <span style={{ fontSize: 13, textWrap: "pretty" }}>“{p.mensagem_original}”</span>
                {p.estado === "info_pedida" && <span style={{ fontSize: 12.5, color: "var(--sel-ink)" }}>? Pedi mais informação. O pedido continua aqui até você decidir.</span>}
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", fontSize: 12.5 }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 6 }}>Sai de
                    <select aria-label={`Sai de (pedido ${p.id})`} value={conta[p.id] ?? ""} onChange={(e) => setConta({ ...conta, [p.id]: e.target.value })} style={seletor}>
                      <option value="">escolha</option>{contas.map((c) => <option key={c.id} value={c.id}>{c.apelido}</option>)}
                    </select>
                  </label>
                  <label style={{ display: "flex", alignItems: "center", gap: 6 }}>Para quem
                    <select aria-label={`Para quem (pedido ${p.id})`} value={ben[p.id] ?? ""} onChange={(e) => setBen({ ...ben, [p.id]: e.target.value })} style={seletor}>
                      <option value="">escolha</option>{pessoas.map((x) => <option key={x.id} value={x.id}>{x.nome}</option>)}
                    </select>
                  </label>
                </div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", paddingTop: 4 }}>
                  <button className="btn btn-primary" onClick={() => decidir(p, "aprovar")}>Aprovar e pôr na fila</button>
                  <button className="btn btn-secondary" onClick={() => decidir(p, "pedir_info")}>Pedir mais informação</button>
                  <button className="btn btn-ghost" onClick={() => decidir(p, "recusar")}>Recusar</button>
                </div>
              </div>
            ))}
          </section>
          <Decididos leitura={decididos.env?.dados.itens ?? []} />
        </div>
      )}
    </Painel>
  );
}

function Decididos({ leitura }: { leitura: Pedido[] }) {
  if (leitura.length === 0) return null;
  return (
    <section style={{ display: "flex", flexDirection: "column" }}>
      <h3 style={{ margin: "0 0 6px", fontSize: 19 }}>Decididos</h3>
      {leitura.map((p) => (
        <div key={p.id} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: "4px 12px", padding: "9px 0", borderTop: "1px solid var(--line2)", alignItems: "center" }}>
          <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <strong style={{ fontSize: 13.5 }}>{p.descricao}{p.valor ? ` · R$ ${p.valor.replace(".", ",")}` : ""}</strong>
            <span style={{ fontSize: 12, color: "var(--ink2)" }}>{p.solicitante} · via {p.canal}</span>
          </span>
          <Etiqueta tipo={p.estado === "aprovado" ? "ok" : "parado"} texto={p.estado === "aprovado" ? "aprovado" : "recusado"} />
        </div>
      ))}
    </section>
  );
}
