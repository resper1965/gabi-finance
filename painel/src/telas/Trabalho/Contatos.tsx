import { useState } from "react";
import { Painel } from "../../componentes/Painel";
import { Vazio } from "../../componentes/Estados";
import { useApi } from "../../lib/useApi";
import { useIr } from "../../lib/ocultar";

type Tipo = "email" | "agenda" | "pedido" | "whatsapp";
interface Aberto { tipo: Tipo; rotulo: string; qtd: number; desde: string | null; dias: number | null; quando: string | null; detalhe: string | null; rota: { area: string; aba: string | null } }
interface Contato { chave: string; pessoa_id: string | null; nome: string; urgencia: number; dias: number; tipos: Tipo[]; abertos: Aberto[] }
interface Dados { total: number; itens: Contato[] }

const FILTROS: [string, string][] = [["todos", "Todos"], ["email", "E-mail"], ["agenda", "Agenda"], ["whatsapp", "WhatsApp"]];
const IR: Record<Tipo, string> = { email: "Ver Prioridades", agenda: "Ver Agenda", pedido: "Ver Pedidos", whatsapp: "Ver Escuta" };
const suave = { color: "var(--ink2)" } as const;

const haQuanto = (d: number | null) => (d === null ? "" : d === 0 ? "hoje" : d === 1 ? "há 1 dia" : `há ${d} dias`);
const BRT = new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

/** Mensagens › Contatos: com quem tenho algo em aberto, o mais urgente primeiro. Só leitura; nada é enviado e a Gabi não responde por você. Nome, assunto e título são dado de terceiros e saem como texto puro. */
export function Contatos() {
  const [filtro, setFiltro] = useState("todos");
  const leitura = useApi<Dados>("/api/v1/contatos");
  const ir = useIr();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div role="group" aria-label="Filtro" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {FILTROS.map(([k, rotulo]) => (
          <button key={k} className={`btn ${filtro === k ? "btn-primary" : "btn-secondary"}`} aria-pressed={filtro === k} onClick={() => setFiltro(k)}>{rotulo}</button>))}
      </div>
      <Painel leitura={leitura} arquivo="contatos">
        {(d) => {
          const itens = d.itens.filter((c) => filtro === "todos" || c.tipos.includes(filtro as Tipo));
          if (d.itens.length === 0) return <Vazio frase="Ninguém com algo em aberto agora." />;
          if (itens.length === 0) return <Vazio frase="Nenhum contato com algo em aberto neste filtro." />;
          return (
            <section style={{ border: "1px solid var(--color-divider)", padding: "10px 12px" }}>
              <h4 style={{ margin: "0 0 8px" }}>Com quem tenho algo em aberto · {itens.length}</h4>
              <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 10 }}>
                {itens.map((c) => (
                  <li key={c.chave} data-contato style={{ borderTop: "1px solid var(--color-divider)", paddingTop: 8 }}>
                    <strong>{c.nome}</strong>
                    <ul style={{ margin: "4px 0 0", padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 4 }}>
                      {c.abertos.filter((a) => filtro === "todos" || a.tipo === filtro).map((a, i) => (
                        <li key={i} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
                          <span>{a.rotulo}
                            {a.tipo === "agenda" && a.quando && <small style={suave}> · {BRT.format(new Date(a.quando))}</small>}
                            {a.detalhe && <small style={suave}> · {a.detalhe}</small>}
                            {a.tipo !== "agenda" && a.dias !== null && <small style={suave}> · {haQuanto(a.dias)}</small>}</span>
                          <button className="btn btn-secondary" aria-label={`${IR[a.tipo]}: ${c.nome}`} onClick={() => ir(a.rota.area, a.rota.aba ?? undefined)}>{IR[a.tipo]}</button>
                        </li>))}
                    </ul>
                  </li>))}
              </ul>
            </section>
          );
        }}
      </Painel>
    </div>
  );
}
