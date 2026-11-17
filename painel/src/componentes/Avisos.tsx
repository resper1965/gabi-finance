import { api } from "../lib/api";
import { useToast } from "../lib/toast";
import { useApi } from "../lib/useApi";

interface Aviso { id: number; tipo: string; titulo: string; texto: string; criado_em: string }

/** Painel do sino: o que o gabi.finance avisa (rodada parada, conta atrasada, cobrada depois de cancelar, vence hoje, serviço que falhou).
 *  "Marcar como lido" só tira o aviso da lista; o problema em si se resolve na tela de origem. */
export function Avisos({ aoMudar }: { aoMudar?: () => void }) {
  const leitura = useApi<{ itens: Aviso[] }>("/api/v1/avisos");
  const avisar = useToast();
  const itens = leitura.env?.dados.itens ?? [];
  const lido = async (a: Aviso) => {
    try { await api.post(`/api/v1/avisos/${a.id}/lido`, {}); leitura.recarregar(); aoMudar?.(); }
    catch (e) { avisar((e as Error).message); }
  };
  return (
    <section role="region" aria-label="Avisos" style={{ display: "flex", flexDirection: "column", gap: 8, padding: 12, background: "var(--color-surface)", border: "1px solid var(--color-divider)", maxWidth: 420 }}>
      {itens.length === 0 && <p style={{ margin: 0, color: "var(--ink2)" }}>Nenhum aviso aberto.</p>}
      {itens.map((a) => (
        <div key={a.id} style={{ display: "flex", gap: 8, alignItems: "flex-start", justifyContent: "space-between", borderBottom: "1px solid var(--line2)", paddingBottom: 8 }}>
          <span><strong style={{ display: "block" }}>{a.titulo}</strong><small style={{ color: "var(--ink2)" }}>{a.texto}</small></span>
          <button className="btn btn-secondary" aria-label={`Marcar como lido: ${a.titulo}`} onClick={() => lido(a)}>Lido</button>
        </div>
      ))}
    </section>
  );
}
