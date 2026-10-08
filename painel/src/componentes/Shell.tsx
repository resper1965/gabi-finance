import { useEffect, useState, type ReactNode } from "react";
import { Activity, CalendarDays, Calendar, Eye, EyeOff, HeartPulse, LayoutDashboard, LayoutGrid, ListChecks, Mail, Moon, PanelLeft, Sun, Tag, Users, Workflow, Building2, Menu, type LucideIcon } from "lucide-react";
import { AREAS, GRUPOS, type Area } from "../navegacao";
import { useLocal } from "../lib/local";
import { OcultarContext } from "../lib/ocultar";

const ICONE: Record<string, LucideIcon> = {
  hoje: CalendarDays, temas: LayoutGrid, agenda: Calendar, msgs: Mail, tarefas: ListChecks,
  caixa: LayoutDashboard, gastos: Workflow, cobrar: Building2, regras: Tag,
  familia: HeartPulse, cadastros: Users, gabi: Activity,
};
const BARRA_CELULAR = ["hoje", "agenda", "msgs", "caixa"];

export function useCelular(): boolean {
  const consulta = "(max-width: 759px)";
  const [v, setV] = useState(() => window.matchMedia?.(consulta).matches ?? false);
  useEffect(() => {
    const m = window.matchMedia?.(consulta);
    if (!m) return;
    const f = () => setV(m.matches);
    m.addEventListener("change", f);
    f();
    return () => m.removeEventListener("change", f);
  }, []);
  return v;
}

export interface ShellProps {
  /** Recebe a área e a aba atuais e devolve a tela. */
  tela: (area: Area, aba: string) => ReactNode;
  /** Seletores de período/conta só aparecem nas telas de dinheiro. */
  seletores?: (area: Area) => ReactNode;
}

export function Shell({ tela, seletores }: ShellProps) {
  const celular = useCelular();
  const [areaId, setAreaId] = useLocal("gabi.area", "hoje");
  const [recolhido, setRecolhido] = useLocal("gabi.menu", "0");
  const [tema, setTema] = useLocal("gabi.tema", "claro");
  const [oculto, setOculto] = useLocal("gabi.ocultar", "0");
  const [mais, setMais] = useState(false);
  const area = AREAS.find((a) => a.id === areaId) ?? AREAS[0];
  const [abaSalva, setAbaSalva] = useLocal(`gabi.aba.${area.id}`, area.abas[0][0]);
  const aba = area.abas.some(([id]) => id === abaSalva) ? abaSalva : area.abas[0][0];
  const mini = recolhido === "1" && !celular;

  const ir = (id: string) => { setAreaId(id); setMais(false); };

  return (
    <OcultarContext.Provider value={oculto === "1"}>
      <div data-theme={tema === "escuro" ? "dark" : "light"} data-celular={celular} style={{ display: "flex", flexDirection: "column", height: "100vh", background: "var(--color-bg)", color: "var(--color-text)" }}>
        <div style={{ flex: 1, minHeight: 0, display: "flex" }}>
          {!celular && (
            <nav aria-label="Painéis" style={{ flex: "none", width: mini ? 60 : 236, borderRight: "1px solid var(--color-divider)", display: "flex", flexDirection: "column", minHeight: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 12px 8px 14px" }}>
                <Marca />
                {!mini && <span style={{ flex: 1, font: "600 19px/1 var(--font-heading)" }}>gabi<span style={{ color: "var(--ink2)" }}>.brain</span></span>}
                <button className="btn btn-ghost btn-icon" aria-label={mini ? "Expandir menu" : "Recolher menu"} onClick={() => setRecolhido(mini ? "0" : "1")}><PanelLeft size={16} strokeWidth={1.5} /></button>
              </div>
              <div style={{ flex: 1, overflow: "auto", padding: "0 8px 12px" }}>
                {GRUPOS.map((g) => (
                  <div key={g.titulo}>
                    {g.titulo && !mini && <span style={{ display: "block", padding: "14px 10px 6px", font: "600 10.5px/1 var(--font-body)", letterSpacing: ".1em", textTransform: "uppercase", color: "var(--ink2)" }}>{g.titulo}</span>}
                    {g.areas.map((a) => <ItemNav key={a.id} area={a} atual={a.id === area.id} mini={mini} ir={ir} />)}
                  </div>
                ))}
              </div>
            </nav>
          )}
          <main style={{ flex: 1, minWidth: 0, overflow: "auto", display: "flex", flexDirection: "column" }}>
            <header style={{ padding: celular ? "14px 14px 0" : "22px 28px 0", display: "flex", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}>
              <div style={{ flex: 1 }}>
                <div style={{ font: "600 10.5px/1 var(--font-body)", letterSpacing: ".08em", textTransform: "uppercase", color: "var(--ink2)" }}>{area.pergunta}</div>
                <h1 style={{ margin: "6px 0 0", font: `600 ${celular ? 24 : 30}px/1.1 var(--font-heading)` }}>{area.rotulo}</h1>
              </div>
              {seletores?.(area)}
              <button className="btn btn-ghost btn-icon" aria-label={oculto === "1" ? "Mostrar valores" : "Ocultar valores"} aria-pressed={oculto === "1"} onClick={() => setOculto(oculto === "1" ? "0" : "1")}>{oculto === "1" ? <EyeOff size={18} strokeWidth={1.5} /> : <Eye size={18} strokeWidth={1.5} />}</button>
              <button className="btn btn-ghost btn-icon" aria-label="Alternar tema" onClick={() => setTema(tema === "escuro" ? "claro" : "escuro")}>{tema === "escuro" ? <Sun size={18} strokeWidth={1.5} /> : <Moon size={18} strokeWidth={1.5} />}</button>
            </header>
            {area.abas.length > 1 && (
              <div role="tablist" style={{ display: "flex", gap: 4, padding: celular ? "10px 14px 0" : "12px 28px 0", borderBottom: "1px solid var(--color-divider)", overflowX: "auto" }}>
                {area.abas.map(([id, rotulo]) => (
                  <button key={id} role="tab" aria-selected={id === aba} onClick={() => setAbaSalva(id)}
                    style={{ minHeight: celular ? 44 : 36, padding: "0 12px", background: "transparent", border: 0, borderBottom: `2px solid ${id === aba ? "var(--color-accent)" : "transparent"}`, color: id === aba ? "var(--color-text)" : "var(--ink2)", fontWeight: id === aba ? 700 : 500, cursor: "pointer", whiteSpace: "nowrap" }}>
                    {rotulo}
                  </button>
                ))}
              </div>
            )}
            <div style={{ padding: celular ? 14 : 28, display: "flex", flexDirection: "column", gap: 22 }}>{tela(area, aba)}</div>
          </main>
        </div>
        {celular && (
          <nav aria-label="Barra inferior" style={{ flex: "none", display: "flex", borderTop: "1px solid var(--color-divider)", background: "var(--color-bg)" }}>
            {BARRA_CELULAR.map((id) => {
              const a = AREAS.find((x) => x.id === id)!;
              return <ItemBarra key={id} icone={ICONE[id]} rotulo={a.rotulo} atual={id === area.id} onClick={() => ir(id)} />;
            })}
            <ItemBarra icone={Menu} rotulo="Mais" atual={false} onClick={() => setMais(!mais)} />
          </nav>
        )}
        {celular && mais && (
          <div role="dialog" aria-label="Mais áreas" style={{ position: "fixed", left: 0, right: 0, bottom: 56, padding: 14, background: "var(--color-bg)", borderTop: "1px solid var(--color-divider)", boxShadow: "var(--shadow-lg)" }}>
            {AREAS.filter((a) => !BARRA_CELULAR.includes(a.id)).map((a) => <ItemNav key={a.id} area={a} atual={a.id === area.id} mini={false} ir={ir} />)}
          </div>
        )}
      </div>
    </OcultarContext.Provider>
  );
}

function ItemNav({ area, atual, mini, ir }: { area: Area; atual: boolean; mini: boolean; ir: (id: string) => void }) {
  const I = ICONE[area.id];
  return (
    <button onClick={() => ir(area.id)} aria-current={atual ? "page" : undefined} aria-label={area.rotulo} title={area.rotulo}
      style={{ display: "flex", alignItems: "center", gap: 10, width: "100%", minHeight: 40, padding: "0 8px", border: 0, borderLeft: `2px solid ${atual ? "var(--color-accent)" : "transparent"}`, background: atual ? "var(--sel)" : "transparent", color: "var(--color-text)", fontWeight: atual ? 700 : 500, fontSize: 14.5, textAlign: "left", cursor: "pointer" }}>
      <I size={19} strokeWidth={1.5} style={{ flex: "none", marginLeft: mini ? 6 : 0 }} />
      {!mini && <span>{area.rotulo}</span>}
    </button>
  );
}

function ItemBarra({ icone: I, rotulo, atual, onClick }: { icone: LucideIcon; rotulo: string; atual: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} aria-current={atual ? "page" : undefined}
      style={{ flex: 1, minHeight: 56, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 2, border: 0, background: "transparent", color: atual ? "var(--color-accent-700)" : "var(--ink2)", font: "500 11px var(--font-body)", cursor: "pointer" }}>
      <I size={20} strokeWidth={1.5} />{rotulo}
    </button>
  );
}

/** Marca da Gabi: quadro de 23px, círculo central, mira e ponto no acento (viewBox 0 0 32 32). */
export function Marca() {
  return (
    <svg aria-hidden="true" width="32" height="32" viewBox="0 0 32 32" style={{ flex: "none", fill: "none", stroke: "var(--color-accent-700)", strokeWidth: 1.25 }}>
      <rect x="4.5" y="4.5" width="23" height="23" /><circle cx="16" cy="16" r="6.5" /><path d="M16 1v8M16 23v8M1 16h8M23 16h8" />
      <circle cx="19.5" cy="12.5" r="2.2" style={{ fill: "var(--color-accent)", stroke: "none" }} />
    </svg>
  );
}
