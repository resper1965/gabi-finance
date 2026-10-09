import { Painel } from "../../componentes/Painel";
import { api } from "../../lib/api";
import { dataCurta } from "../../lib/formato";
import { useToast } from "../../lib/toast";
import { useApi } from "../../lib/useApi";

interface Tarefa { id: number; origem: string; titulo: string; prazo: string | null; estado: string }

/** Tarefas: marcar conclui NA ORIGEM (Microsoft To Do / Google Tasks); só então aparece como feita aqui. */
export function Tarefas() {
  const leitura = useApi<{ itens: Tarefa[] }>("/api/v1/tarefas");
  const avisar = useToast();
  const concluir = async (t: Tarefa) => {
    try { await api.post(`/api/v1/tarefas/${t.id}/concluir`); avisar("Concluída na origem."); leitura.recarregar(); } catch (e) { avisar((e as Error).message); }
  };
  return (
    <Painel leitura={leitura} arquivo="tarefas">
      {(d) => (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {d.itens.length === 0 && <p style={{ color: "var(--ink2)" }}>Nenhuma tarefa.</p>}
          {d.itens.map((t) => (
            <label key={t.id} data-tarefa style={{ display: "flex", gap: 10, alignItems: "center", border: "1px solid var(--color-divider)", padding: "8px 12px", opacity: t.estado === "concluida" ? 0.6 : 1 }}>
              <input type="checkbox" aria-label={`Concluir ${t.titulo}`} checked={t.estado === "concluida"} disabled={t.estado === "concluida"} onChange={() => concluir(t)} />
              <span style={{ textDecoration: t.estado === "concluida" ? "line-through" : "none" }}>{t.titulo}</span>
              <small style={{ marginLeft: "auto" }}>{t.origem}{t.prazo ? ` · ${dataCurta(t.prazo.slice(0, 10))}` : ""}</small>
            </label>))}
        </div>
      )}
    </Painel>
  );
}
