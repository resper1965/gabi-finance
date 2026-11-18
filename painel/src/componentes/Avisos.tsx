import { BellOff } from "lucide-react";
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
    <section role="region" aria-label="Avisos" style={{ display: "flex", flexDirection: "column" }}>
      <div className="fila-entre" style={{ padding: "12px 16px", borderBottom: "1px solid var(--regra)" }}>
        <h2 style={{ fontSize: "var(--t1)", fontWeight: 650 }}>Avisos</h2>
        <span className="miudo">{itens.length ? `${itens.length} aberto${itens.length > 1 ? "s" : ""}` : ""}</span>
      </div>
      {itens.length === 0 && <p className="suave fila" style={{ padding: 16 }}><BellOff size={16} strokeWidth={1.7} aria-hidden="true" />Nenhum aviso aberto.</p>}
      <ul className="pauta" style={{ maxHeight: "60vh", overflowY: "auto" }}>
        {itens.map((a) => (
          <li key={a.id} className="linha-item" style={{ padding: "12px 16px" }}>
            <span className="pilha-curta" style={{ gap: 2 }}><strong className="linha-titulo">{a.titulo}</strong><span className="miudo">{a.texto}</span></span>
            <button className="btn btn-sm" aria-label={`Marcar como lido: ${a.titulo}`} onClick={() => lido(a)}>Lido</button>
          </li>
        ))}
      </ul>
    </section>
  );
}
