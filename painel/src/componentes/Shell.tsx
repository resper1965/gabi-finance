import { useEffect, useState, type ReactNode } from "react";
import { Activity, Bell, Building2, Calendar, CalendarDays, ChevronLeft, ChevronRight, Eye, EyeOff, HeartPulse, LayoutDashboard, LayoutGrid, ListChecks, Mail, Menu, Moon, Sun, Tag, Users, Workflow, type LucideIcon } from "lucide-react";
import { AREAS, GRUPOS, type Area } from "../navegacao";
import { useLocal, gravarLocal } from "../lib/local";
import { IrContext, OcultarContext } from "../lib/ocultar";
import { FaixaSlot } from "./Faixa";
import { CustoGabi } from "./CustoGabi";

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
  seletores?: (area: Area, celular: boolean) => ReactNode;
}

const icone = { fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round", strokeLinejoin: "round" } as const;

export function Shell({ tela, seletores }: ShellProps) {
  const celular = useCelular();
  const [areaId, setAreaId] = useLocal("gabi.area", "hoje");
  const [recolhido, setRecolhido] = useLocal("gabi.menu", "0");
  const [tema, setTema] = useLocal("gabi.tema", "claro");
  const [oculto, setOculto] = useLocal("gabi.ocultar", "0");
  const [mais, setMais] = useState(false);
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  const area = AREAS.find((a) => a.id === areaId) ?? AREAS[0];
  const [abaSalva, setAbaSalva] = useLocal(`gabi.aba.${area.id}`, area.abas[0][0]);
  const aba = area.abas.some(([id]) => id === abaSalva) ? abaSalva : area.abas[0][0];
  const mini = recolhido === "1" && !celular;
  const pad = celular ? 14 : 28;

  const ir = (id: string, aba?: string) => { if (aba) gravarLocal(`gabi.aba.${id}`, aba); setAreaId(id); setMais(false); };

  return (
    <OcultarContext.Provider value={oculto === "1"}>
      <IrContext.Provider value={ir}>
        <FaixaSlot.Provider value={slot}>
          <div data-theme={tema === "escuro" ? "dark" : "light"} data-celular={celular} style={{ ["--pad" as string]: `${pad}px`, display: "flex", flexDirection: "column", height: "100vh", background: "var(--color-bg)", color: "var(--color-text)", fontFamily: "var(--font-body)", fontSize: 14, lineHeight: 1.45 }}>
            <div style={{ flex: 1, minHeight: 0, display: "flex" }}>
              {!celular && (
                <nav aria-label="Painéis" style={{ flex: "none", width: mini ? 60 : 236, borderRight: "1px solid var(--color-divider)", display: "flex", flexDirection: "column", minHeight: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 12px 8px 14px", flexWrap: "wrap" }}>
                    <Marca />
                    {!mini && (
                      <span style={{ flex: 1, display: "flex", flexDirection: "column", lineHeight: 1.15 }}>
                        <span style={{ font: "600 19px/1 var(--font-heading)" }}>gabi<span style={{ color: "var(--ink2)" }}>.brain</span></span>
                        <span style={{ font: "500 11px/1.2 var(--mono)", letterSpacing: ".06em", textTransform: "uppercase", color: "var(--ink2)" }}>ai agent</span>
                      </span>
                    )}
                    <button className="btn btn-ghost btn-icon" aria-label={mini ? "Expandir menu" : "Recolher menu"} title={mini ? "Expandir menu" : "Recolher menu"} onClick={() => setRecolhido(mini ? "0" : "1")} style={{ width: 28, height: 28, color: "var(--ink2)" }}>
                      {mini ? <ChevronRight size={16} {...icone} /> : <ChevronLeft size={16} {...icone} />}
                    </button>
                  </div>
                  <div style={{ flex: 1, overflow: "auto", overflowX: "hidden", padding: "0 8px 12px", display: "flex", flexDirection: "column", gap: 1 }}>
                    {GRUPOS.map((g) => (
                      <div key={g.titulo} style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                        {g.titulo && !mini && <span style={{ padding: "14px 10px 6px", font: "600 10.5px/1 var(--font-body)", letterSpacing: ".1em", textTransform: "uppercase", color: "var(--ink2)" }}>{g.titulo}</span>}
                        {g.titulo && mini && <span style={{ display: "block", margin: "8px 8px", borderTop: "1px solid var(--line2)" }} />}
                        {g.areas.map((a) => <ItemNav key={a.id} area={a} atual={a.id === area.id} mini={mini} ir={ir} />)}
                      </div>
                    ))}
                  </div>
                  {!mini && <CustoGabi />}
                </nav>
              )}
              <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", minHeight: 0, position: "relative" }}>
                <header style={{ flex: "none", display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", padding: celular ? "10px 14px" : "12px 28px", borderBottom: "1px solid var(--color-divider)" }}>
                  {celular && <Marca />}
                  <div style={{ flex: "1 1 140px", minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={{ font: "600 10.5px/1.2 var(--font-body)", letterSpacing: ".08em", textTransform: "uppercase", color: "var(--ink2)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{area.abas.find(([id]) => id === aba)?.[2] ?? area.pergunta}</span>
                    <h1 style={{ margin: 0, font: `600 ${celular ? 24 : 30}px/1.05 var(--font-heading)`, letterSpacing: "-.01em" }}>{area.rotulo}</h1>
                  </div>
                  {!celular && seletores?.(area, false)}
                  <div style={{ display: "flex", gap: 6 }}>
                    <button className="btn btn-secondary btn-icon" aria-label={oculto === "1" ? "Mostrar valores" : "Ocultar valores"} title={oculto === "1" ? "Mostrar valores" : "Ocultar valores"} aria-pressed={oculto === "1"} onClick={() => setOculto(oculto === "1" ? "0" : "1")}>{oculto === "1" ? <EyeOff size={18} {...icone} /> : <Eye size={18} {...icone} />}</button>
                    <button className="btn btn-secondary btn-icon" aria-label={tema === "escuro" ? "Tema claro" : "Tema escuro"} title={tema === "escuro" ? "Tema claro" : "Tema escuro"} onClick={() => setTema(tema === "escuro" ? "claro" : "escuro")}>{tema === "escuro" ? <Sun size={18} {...icone} /> : <Moon size={18} {...icone} />}</button>
                    <button className="btn btn-secondary btn-icon" aria-label="Alertas" title="Alertas"><Bell size={18} {...icone} /></button>
                  </div>
                  {celular && <div style={{ flex: "1 0 100%" }}>{seletores?.(area, true)}</div>}
                  {area.abas.length > 1 && (
                    <div role="tablist" style={{ flex: "1 0 100%", display: "flex", overflowX: "auto", marginBottom: celular ? -10 : -12 }}>
                      {area.abas.map(([id, rotulo]) => (
                        <button key={id} role="tab" aria-selected={id === aba} onClick={() => setAbaSalva(id)}
                          style={{ flex: "none", display: "flex", alignItems: "center", gap: 6, minHeight: 40, padding: "0 14px", border: 0, borderBottom: `2px solid ${id === aba ? "var(--color-accent)" : "transparent"}`, background: "transparent", color: id === aba ? "var(--color-text)" : "var(--ink2)", fontWeight: id === aba ? 700 : 500, fontSize: 14, cursor: "pointer", whiteSpace: "nowrap" }}>
                          {rotulo}
                        </button>
                      ))}
                    </div>
                  )}
                </header>
                <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
                  <div ref={setSlot} />
                  <div style={{ padding: pad, paddingBottom: 40, display: "flex", flexDirection: "column", gap: 22, maxWidth: 1400 }}>{tela(area, aba)}</div>
                </div>
              </div>
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
        </FaixaSlot.Provider>
      </IrContext.Provider>
    </OcultarContext.Provider>
  );
}

function ItemNav({ area, atual, mini, ir }: { area: Area; atual: boolean; mini: boolean; ir: (id: string) => void }) {
  const I = ICONE[area.id];
  return (
    <button onClick={() => ir(area.id)} aria-current={atual ? "page" : undefined} aria-label={area.rotulo} title={area.pergunta}
      style={{ position: "relative", display: "flex", alignItems: "center", gap: 10, width: "100%", minHeight: 40, padding: "0 8px", border: 0, borderLeft: `2px solid ${atual ? "var(--color-accent)" : "transparent"}`, background: atual ? "var(--sel)" : "transparent", color: "var(--color-text)", fontWeight: atual ? 700 : 500, fontSize: 14.5, textAlign: "left", cursor: "pointer" }}>
      <I size={19} {...icone} style={{ flex: "none", marginLeft: mini ? 6 : 0 }} />
      {!mini && <span style={{ flex: 1, minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{area.rotulo}</span>}
    </button>
  );
}

function ItemBarra({ icone: I, rotulo, atual, onClick }: { icone: LucideIcon; rotulo: string; atual: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} aria-current={atual ? "page" : undefined}
      style={{ flex: 1, minHeight: 56, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 2, border: 0, background: "transparent", color: atual ? "var(--color-accent-700)" : "var(--ink2)", font: "500 11px var(--font-body)", cursor: "pointer" }}>
      <I size={20} {...icone} />{rotulo}
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
