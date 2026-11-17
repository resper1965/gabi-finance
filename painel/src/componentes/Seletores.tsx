import { PERIODOS, useFiltros } from "../lib/filtros";
import { useApi } from "../lib/useApi";

/** Período (Semana, Mês, 12 meses) e conta. Só nas telas de dinheiro. */
export function Seletores({ celular = false }: { celular?: boolean }) {
  const f = useFiltros();
  const contas = (useApi<{ itens: { apelido: string; estado: string }[] }>("/api/v1/cadastros/contas").env?.dados.itens ?? []).filter((c) => c.estado === "sim").map((c) => c.apelido);
  return (
    <div className="fila" style={{ flexWrap: celular ? "nowrap" : "wrap", width: celular ? "100%" : undefined }}>
      <div role="group" aria-label="Período" className="seg" style={celular ? { flex: 1 } : undefined}>
        {PERIODOS.map(([id, rotulo]) => (
          <button key={id} className="seg-opt" aria-pressed={f.periodo === id} onClick={() => f.setPeriodo(id)} style={celular ? { flex: 1 } : undefined}>{rotulo}</button>
        ))}
      </div>
      <select aria-label="Conta" value={f.conta} onChange={(e) => f.setConta(e.target.value)} style={{ maxWidth: celular ? 150 : 220 }}>
        <option value="">Todas as contas</option>
        {contas.map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
    </div>
  );
}
