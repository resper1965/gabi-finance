import { useState } from "react";
import { Painel } from "../componentes/Painel";
import { api } from "../lib/api";
import { dataCurta } from "../lib/formato";
import { useToast } from "../lib/toast";
import { useApi } from "../lib/useApi";

interface Documento { id: number; documento: string | null; caso: string | null; estado: string; data: string }
interface Dossie { dossie: number; paciente: string | null; prestador: string | null; mes: string; estado: string; parado_desde?: string | null; faltam: string[]; documentos: Documento[] }

const ESTADOS: [string, string][] = [["a_pedir", "A pedir"], ["a_conferir", "A conferir"], ["pedido", "Pedido"], ["recebido", "Recebido"]];
const ROTULO: Record<string, string> = { ...Object.fromEntries(ESTADOS), sem_nf: "Sem nota fiscal", sem_aprovacao: "Sem aprovação do plano" };
const mes = (m: string) => `${m.slice(5, 7)}/${m.slice(0, 4)}`;

function Semana() {
  const leitura = useApi<{ texto: string }>("/api/v1/reembolso-saude/semana");
  return (
    <Painel leitura={leitura} arquivo="reembolso-semana">
      {(d) => (
        <section aria-label="Resumo da semana">
          <h3 style={{ margin: "0 0 6px", fontSize: 20 }}>Resumo da semana</h3>
          <pre style={{ whiteSpace: "pre-wrap", background: "var(--color-surface)", padding: 12, margin: 0 }}>{d.texto}</pre>
        </section>)}
    </Painel>
  );
}

/** Reembolso do plano de saúde: dossiês com paciente e prestador (lidos do cofre; só boss com grau total). "Marquei como pedido" e "Recebi" só ANOTAM a intenção:
 *  o estado muda na próxima rodada e nada é enviado ao plano (R2). */
export function Reembolso() {
  const leitura = useApi<{ dossies: Dossie[] }>("/api/v1/reembolso-saude/dossies");
  const [filtro, setFiltro] = useState<string>("todos");
  const avisar = useToast();
  const agir = async (n: number, acao: "pedi" | "recebi") => {
    try { await (acao === "pedi" ? api.post(`/api/v1/reembolso-saude/dossies/${n}/pedi`) : api.post(`/api/v1/reembolso-saude/dossies/${n}/recebi`)); avisar("Anotado. O estado muda na próxima rodada; nada foi enviado ao plano."); leitura.recarregar(); } catch (e) { avisar((e as Error).message); }
  };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <Semana />
      <Painel leitura={leitura} arquivo="reembolso-dossies">
        {(d) => {
          const itens = d.dossies.filter((x) => filtro === "todos" || x.estado === filtro);
          return (
            <section style={{ display: "flex", flexDirection: "column", gap: 10 }} aria-label="Dossiês de reembolso">
              <h3 style={{ margin: 0, fontSize: 20 }}>Dossiês · {d.dossies.length}</h3>
              <div role="group" aria-label="Filtrar por estado" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {[["todos", "Todos"], ...ESTADOS].map(([id, rotulo]) => (
                  <button key={id} className={id === filtro ? "btn btn-primary" : "btn btn-secondary"} aria-pressed={id === filtro} onClick={() => setFiltro(id)}>{rotulo}</button>))}
              </div>
              {d.dossies.length === 0 && <p style={{ color: "var(--ink2)" }}>Nenhum dossiê de reembolso ainda.</p>}
              {d.dossies.length > 0 && itens.length === 0 && <p style={{ color: "var(--ink2)" }}>Nenhum dossiê neste estado.</p>}
              {itens.map((x) => (
                <article key={x.dossie} aria-label={`Dossiê ${x.dossie}`} style={{ border: "1px solid var(--color-divider)", padding: 12, display: "flex", flexDirection: "column", gap: 6 }}>
                  <strong>Dossiê {x.dossie} · {mes(x.mes)} · {ROTULO[x.estado] ?? x.estado}</strong>
                  <span>{x.paciente ?? "paciente não identificado"} · {x.prestador ?? "prestador não identificado"}</span>
                  <span>{x.documentos.length} documento{x.documentos.length === 1 ? "" : "s"}{x.parado_desde ? ` · parado desde ${dataCurta(x.parado_desde)}` : ""}</span>
                  {x.faltam.length > 0 && <span>Falta: {x.faltam.join(", ")}</span>}
                  {x.estado === "a_pedir" && x.faltam.length === 0 && <span>Tudo o que o plano exige está nos documentos.</span>}
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {x.estado === "a_pedir" && <button className="btn btn-primary" onClick={() => agir(x.dossie, "pedi")}>Marquei como pedido</button>}
                    {(x.estado === "pedido" || x.estado === "a_conferir") && <button className="btn btn-secondary" onClick={() => agir(x.dossie, "recebi")}>Recebi</button>}
                  </div>
                </article>))}
            </section>);
        }}
      </Painel>
    </div>
  );
}
