import { useState } from "react";
import { Painel } from "../componentes/Painel";
import { api } from "../lib/api";
import { useToast } from "../lib/toast";
import { useApi } from "../lib/useApi";

interface Passo { passo: string; titulo: string; explicacao: string; estado: "pendente" | "feito" | "depois"; detalhe: string | null }
const ROTULO = { pendente: "pendente", feito: "feito", depois: "para depois" };

/** Assistente de configuração: cada passo explica o que o app lê, é testado na hora e pode ficar para depois. O app nunca pede nem guarda senha aqui. */
export function Configuracao() {
  const leitura = useApi<{ passos: Passo[] }>("/api/v1/setup");
  const [resultado, setResultado] = useState<Record<string, string>>({});
  const avisar = useToast();
  const agir = async (p: Passo, acao: "testar" | "depois") => {
    try {
      const r = (await api.post<{ ok: boolean; detalhe: string }>(`/api/v1/setup/${p.passo}`, { acao })).dados;
      setResultado({ ...resultado, [p.passo]: `${r.ok ? "✓" : "✗"} ${r.detalhe}` });
      leitura.recarregar();
    } catch (e) { avisar((e as Error).message); }
  };
  return (
    <Painel leitura={leitura} arquivo="setup">
      {(d) => (
        <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 12 }}>
          {d.passos.map((p, i) => (
            <li key={p.passo} style={{ border: "1px solid var(--color-divider)", padding: 14, display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <strong>{i + 1}. {p.titulo}</strong>
                <span data-estado={p.estado} style={{ fontSize: 12.5, color: p.estado === "feito" ? "var(--ok)" : "var(--ink2)" }}>{ROTULO[p.estado]}</span>
              </div>
              <p style={{ margin: 0, textWrap: "pretty" }}>{p.explicacao}</p>
              {(resultado[p.passo] ?? p.detalhe) && <p role="status" style={{ margin: 0, fontSize: 13.5 }}>{resultado[p.passo] ?? p.detalhe}</p>}
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-primary" onClick={() => agir(p, "testar")}>Testar conexão</button>
                {p.estado !== "feito" && <button className="btn btn-secondary" onClick={() => agir(p, "depois")}>Deixar para depois</button>}
              </div>
            </li>))}
        </ol>
      )}
    </Painel>
  );
}
