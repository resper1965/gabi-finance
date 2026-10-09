import { Bloco } from "../componentes/Bloco";
import { Etiqueta } from "../componentes/Etiqueta";
import { Painel } from "../componentes/Painel";
import { api } from "../lib/api";
import { useToast } from "../lib/toast";
import { useApi } from "../lib/useApi";
import { CadastrosCobranca } from "./CadastrosCobranca";
import { CadastrosCaixas } from "./CadastrosCaixas";
import { CadastrosEquivalencias } from "./CadastrosEquivalencias";

interface Conta { id: number; apelido: string; instituicao: string; tipo: string; estado: string; limite: string | null }

const ESTADO: Record<string, string> = { sim: "entra no caixa único", nao: "fica de fora", a_decidir: "esperando você decidir" };

/** Fase 1: só as contas, para o Ricardo decidir quais entram no caixa único (G5). Demais cadastros chegam depois. */
export function Cadastros() {
  const leitura = useApi<{ itens: Conta[] }>("/api/v1/cadastros/contas");
  const avisar = useToast();
  const decidir = async (c: Conta, estado: "sim" | "nao") => {
    try { await api.patch(`/api/v1/cadastros/contas/${c.id}`, { estado }); avisar(`Anotado: ${c.apelido} ${estado === "sim" ? "entra" : "não entra"} no caixa único.`); leitura.recarregar(); }
    catch (e) { avisar((e as Error).message); }
  };
  return (
    <Painel leitura={leitura} arquivo="contas conectadas">
      {(d) => (
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <Bloco titulo="Contas">
          <p style={{ color: "var(--ink2)", marginTop: 0 }}>Conta nova só entra no caixa único depois que você decidir.</p>
          {d.itens.map((c) => (
            <div key={c.id} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", padding: "8px 0", borderBottom: "1px solid var(--line2)" }}>
              <span style={{ flex: "1 1 160px" }}>{c.apelido}<small style={{ display: "block", color: "var(--ink2)" }}>{c.instituicao} · {c.tipo}</small></span>
              <Etiqueta tipo={c.estado === "a_decidir" ? "conferir" : "ok"} texto={ESTADO[c.estado] ?? c.estado} />
              <button className="btn btn-secondary" disabled={c.estado === "sim"} onClick={() => decidir(c, "sim")}>Entra no caixa único</button>
              <button className="btn btn-secondary" disabled={c.estado === "nao"} onClick={() => decidir(c, "nao")}>Não entra</button>
            </div>
          ))}
        </Bloco>
        <CadastrosEquivalencias />
        <CadastrosCobranca />
        <CadastrosCaixas />
        </div>
      )}
    </Painel>
  );
}
