import { PERIODOS, useFiltros } from "../lib/filtros";
import { useApi } from "../lib/useApi";

/** Período (Semana, Mês, 12 meses) e conta. Só nas telas de dinheiro. Estrutura do protótipo: grupo .seg + rótulo "Conta". */
export function Seletores({ celular = false }: { celular?: boolean }) {
  const f = useFiltros();
  const contas = (useApi<{ itens: { apelido: string; estado: string }[] }>("/api/v1/cadastros/contas").env?.dados.itens ?? []).filter((c) => c.estado === "sim").map((c) => c.apelido);
  const opcoes = (<><option value="">{celular ? "Todas as contas" : "Todas"}</option>{contas.map((c) => <option key={c} value={c}>{c}</option>)}</>);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: celular ? undefined : "wrap" }}>
      <div role="group" aria-label="Período" className="seg" style={celular ? { flex: 1 } : undefined}>
        {PERIODOS.map(([id, rotulo]) => (
          <button key={id} className="seg-opt" aria-pressed={f.periodo === id} onClick={() => f.setPeriodo(id)}
            style={{ flex: celular ? 1 : undefined, justifyContent: celular ? "center" : undefined, border: 0, borderLeft: "1px solid var(--color-divider)", marginLeft: -1, background: f.periodo === id ? "var(--color-accent)" : "transparent", color: f.periodo === id ? "var(--color-bg)" : "var(--color-text)" }}>{rotulo}</button>
        ))}
      </div>
      {celular
        ? <select aria-label="Conta" value={f.conta} onChange={(e) => f.setConta(e.target.value)} style={{ height: 33, border: "1px solid var(--color-divider)", background: "var(--raised)", color: "inherit", font: "600 13px var(--font-body)", padding: "0 6px" }}>{opcoes}</select>
        : <label style={{ display: "flex", alignItems: "center", gap: 6, height: 33, padding: "0 6px 0 10px", border: "1px solid var(--color-divider)", fontSize: 13 }}>
            <span style={{ color: "var(--ink2)" }}>Conta</span>
            <select aria-label="Conta" value={f.conta} onChange={(e) => f.setConta(e.target.value)} style={{ border: 0, background: "transparent", color: "inherit", font: "600 13px var(--font-body)", cursor: "pointer" }}>{opcoes}</select>
          </label>}
    </div>
  );
}
