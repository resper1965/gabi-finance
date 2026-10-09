import { useState } from "react";
import { api } from "../lib/api";
import { useToast } from "../lib/toast";
import { useApi } from "../lib/useApi";

interface Caixa { id: number; endereco: string; provedor: string; papel: string | null; empresa_id: string | null; le: number; rascunho: number; ler_a_partir_de: string | null; estado: string; itens: number }
const ESTADOS: [string, string][] = [["a_decidir", "a decidir (não lê)"], ["sim", "sim (lê)"], ["nao", "não"]];
const campo = { height: 32, border: "1px solid var(--color-divider)", background: "var(--color-surface)", color: "inherit", font: "500 14px var(--font-body)", padding: "0 8px" } as const;

/** Cadastros › Caixas de e-mail (T3.3): as caixas que a Gabi pode ler. Nascem “a decidir”; só “sim” é lida. Senhas e tokens nunca passam por aqui (R5). */
export function CadastrosCaixas() {
  const leitura = useApi<{ itens: Caixa[] }>("/api/v1/caixas-email");
  const avisar = useToast();
  const [novo, setNovo] = useState({ endereco: "", provedor: "google" });
  const agir = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); avisar(ok); leitura.recarregar(); } catch (e) { avisar((e as Error).message); }
  };
  const itens = leitura.env?.dados.itens ?? [];
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <h3 style={{ margin: 0 }}>Caixas de e-mail</h3>
      {itens.length === 0 && <p style={{ color: "var(--ink2)" }}>Nenhuma caixa cadastrada.</p>}
      {itens.map((c) => (
        <div key={c.id} data-caixa style={{ border: "1px solid var(--color-divider)", padding: "8px 12px", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <strong>{c.endereco}</strong><small>{c.provedor} · {c.itens} itens</small>
          <label style={{ marginLeft: "auto" }}>Lê
            <select aria-label={`Estado de ${c.endereco}`} value={c.estado} style={campo}
              onChange={(e) => agir(() => api.patch(`/api/v1/caixas-email/${c.id}`, { estado: e.target.value }), "Caixa atualizada.")}>
              {ESTADOS.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
            </select>
          </label>
        </div>))}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input aria-label="Endereço da nova caixa" style={campo} value={novo.endereco} placeholder="endereço@dominio" onChange={(e) => setNovo({ ...novo, endereco: e.target.value })} />
        <select aria-label="Provedor da nova caixa" style={campo} value={novo.provedor} onChange={(e) => setNovo({ ...novo, provedor: e.target.value })}><option value="google">Google</option><option value="graph">Microsoft 365</option></select>
        <button onClick={() => agir(async () => { await api.post("/api/v1/caixas-email", novo); setNovo({ ...novo, endereco: "" }); }, "Caixa cadastrada (a decidir).")}>+ Cadastrar</button>
      </div>
    </section>
  );
}
