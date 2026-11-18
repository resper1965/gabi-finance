import { useEffect, useState, type ReactNode } from "react";
import { Bell, Building2, ChevronsLeft, ChevronsRight, Eye, EyeOff, KeyRound, Landmark, Menu, Moon, ReceiptText, Sun, Tags, Users, type LucideIcon } from "lucide-react";
import { AREAS, GRUPOS, type Area } from "../navegacao";
import { useLocal, gravarLocal } from "../lib/local";
import { IrContext, OcultarContext } from "../lib/ocultar";
import { FaixaSlot } from "./Faixa";
import { CustoGabi } from "./CustoGabi";

const ICONE: Record<string, LucideIcon> = {
  caixa: Landmark, gastos: ReceiptText, cobrar: Building2, regras: Tags,
  cadastros: Users, gabi: KeyRound,
};
const BARRA_CELULAR = ["caixa", "gastos", "cobrar", "regras"];
const traco = { strokeWidth: 1.7 } as const;

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
  /** Itens que pedem decisão: total no sino e um número por área do menu (0 = sem selo). */
  contagens?: Contagens;
  /** Painel que o sino abre e fecha (a lista de avisos). */
  avisos?: ReactNode;
}

export interface Contagens { sino: number; menu: Record<string, number> }

/** Selo numérico (sino e menu); some quando não há nada a decidir. */
function Selo({ n }: { n?: number }) {
  if (!n) return null;
  return <span data-selo className="selo">{n > 99 ? "99+" : n}</span>;
}

/** #caixa/contas ou #cadastros/despesas (área/aba) na URL abre essa tela na carga, p.ex. um link que a Gabi manda no Telegram. */
function gravarLinkDaUrl(): null {
  const [id, aba] = window.location.hash.replace(/^#/, "").split("/");
  const alvo = AREAS.find((a) => a.id === id);
  if (!alvo) return null;
  gravarLocal("gabi.area", id);
  if (alvo.abas.some(([x]) => x === aba)) gravarLocal(`gabi.aba.${id}`, aba);
  return null;
}

/** Sem preferência gravada, o tema segue o sistema. */
const temaDoSistema = () => (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "escuro" : "claro");

export function Shell({ tela, seletores, contagens, avisos }: ShellProps) {
  const celular = useCelular();
  const [sinoAberto, setSinoAberto] = useState(false);
  useState(gravarLinkDaUrl); // antes dos useLocal abaixo, que já leem o que o link gravou
  const [areaId, setAreaId] = useLocal("gabi.area", "caixa");
  const [recolhido, setRecolhido] = useLocal("gabi.menu", "0");
  const [tema, setTema] = useLocal("gabi.tema", temaDoSistema());
  const [oculto, setOculto] = useLocal("gabi.ocultar", "0");
  const [mais, setMais] = useState(false);
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  const area = AREAS.find((a) => a.id === areaId) ?? AREAS[0];
  const [abaSalva, setAbaSalva] = useLocal(`gabi.aba.${area.id}`, area.abas[0][0]);
  const aba = area.abas.some(([id]) => id === abaSalva) ? abaSalva : area.abas[0][0];
  const mini = recolhido === "1" && !celular;
  const escuro = tema === "escuro";
  const pergunta = area.abas.find(([id]) => id === aba)?.[2] ?? area.pergunta;

  // o tema vale para a página inteira (barras de rolagem, seleção e os quadros que saem por portal)
  useEffect(() => { document.documentElement.dataset.theme = escuro ? "dark" : "light"; }, [escuro]);
  useEffect(() => { window.history.replaceState?.(null, "", `#${area.id}/${aba}`); }, [area.id, aba]);
  useEffect(() => {
    if (!sinoAberto && !mais) return;
    const f = (e: KeyboardEvent) => { if (e.key === "Escape") { setSinoAberto(false); setMais(false); } };
    window.addEventListener("keydown", f);
    return () => window.removeEventListener("keydown", f);
  }, [sinoAberto, mais]);

  const ir = (id: string, aba?: string) => { if (aba) gravarLocal(`gabi.aba.${id}`, aba); setAreaId(id); setMais(false); };
  const icone = celular ? 18 : 17;

  return (
    <OcultarContext.Provider value={oculto === "1"}>
      <IrContext.Provider value={ir}>
        <FaixaSlot.Provider value={slot}>
          <div className="app" data-theme={escuro ? "dark" : "light"} data-celular={celular}>
            <div className="app-corpo">
              {!celular && (
                <nav aria-label="Painéis" className="trilho" data-mini={mini}>
                  <div className="trilho-cabeca">
                    <Marca />
                    {!mini && <span className="marca-nome"><strong>gabi<span>.finance</span></strong><small>laudo do caixa</small></span>}
                    <button className="trilho-botao" aria-label={mini ? "Expandir menu" : "Recolher menu"} title={mini ? "Expandir menu" : "Recolher menu"} onClick={() => setRecolhido(mini ? "0" : "1")}>
                      {mini ? <ChevronsRight size={16} {...traco} /> : <ChevronsLeft size={16} {...traco} />}
                    </button>
                  </div>
                  <div className="trilho-lista">
                    {GRUPOS.map((g, i) => (
                      <div key={g.titulo} role="group" aria-label={g.titulo ?? undefined}>
                        {g.titulo && !mini && <div className="trilho-grupo" aria-hidden="true">{g.titulo}</div>}
                        {g.titulo && mini && i > 0 && <div className="trilho-divisor" />}
                        {g.areas.map((a) => <ItemNav key={a.id} area={a} atual={a.id === area.id} mini={mini} ir={ir} selo={contagens?.menu[a.id]} />)}
                      </div>
                    ))}
                  </div>
                  {!mini && <CustoGabi />}
                </nav>
              )}
              <div className="principal">
                <header className="topo">
                  <div className="topo-linha">
                    {celular && <span className="marca-celular"><Marca /></span>}
                    <h1 className="topo-pergunta">{pergunta}</h1>
                    {!celular && seletores?.(area, false)}
                    <div className="topo-acoes">
                      <button className="btn btn-icon" aria-label={oculto === "1" ? "Mostrar valores" : "Ocultar valores"} title={oculto === "1" ? "Mostrar valores" : "Ocultar valores"} aria-pressed={oculto === "1"} onClick={() => setOculto(oculto === "1" ? "0" : "1")}>
                        {oculto === "1" ? <EyeOff size={icone} {...traco} /> : <Eye size={icone} {...traco} />}</button>
                      <button className="btn btn-icon" aria-label={escuro ? "Tema claro" : "Tema escuro"} title={escuro ? "Tema claro" : "Tema escuro"} onClick={() => setTema(escuro ? "claro" : "escuro")}>
                        {escuro ? <Sun size={icone} {...traco} /> : <Moon size={icone} {...traco} />}</button>
                      <button className="btn btn-icon" aria-label="Alertas" title="Alertas" aria-expanded={sinoAberto} onClick={() => setSinoAberto((v) => !v)} style={{ position: "relative" }}>
                        <Bell size={icone} {...traco} /><span className="sino-selo"><Selo n={contagens?.sino} /></span></button>
                    </div>
                  </div>
                  {celular && seletores?.(area, true)}
                  {area.abas.length > 1 ? (
                    <div role="tablist" aria-label={area.rotulo} className="abas">
                      {area.abas.map(([id, rotulo]) => (
                        <button key={id} role="tab" className="aba" aria-selected={id === aba} tabIndex={id === aba ? 0 : -1} onClick={() => setAbaSalva(id)}
                          onKeyDown={(e) => {
                            const i = area.abas.findIndex(([x]) => x === id);
                            const passo = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
                            if (!passo) return;
                            const proxima = area.abas[(i + passo + area.abas.length) % area.abas.length][0];
                            setAbaSalva(proxima);
                            (e.currentTarget.parentElement?.querySelector(`[data-aba="${proxima}"]`) as HTMLElement | null)?.focus();
                          }} data-aba={id}>
                          {rotulo}
                        </button>
                      ))}
                    </div>
                  ) : <div className="sem-abas" />}
                  {sinoAberto && avisos && <div className="avisos-pop">{avisos}</div>}
                </header>
                <div ref={setSlot} />
                <div className="conteudo">
                  <main className="pagina">{tela(area, aba)}</main>
                </div>
              </div>
            </div>
            {celular && (
              <nav aria-label="Barra inferior" className="barra">
                {BARRA_CELULAR.map((id) => {
                  const a = AREAS.find((x) => x.id === id)!;
                  return <ItemBarra key={id} icone={ICONE[id]} rotulo={a.rotulo} atual={id === area.id && !mais} onClick={() => ir(id)} selo={contagens?.menu[id]} />;
                })}
                <ItemBarra icone={Menu} rotulo="Mais" atual={false} expandido={mais} onClick={() => setMais(!mais)} />
              </nav>
            )}
            {celular && mais && (
              <div role="dialog" aria-label="Mais áreas" className="mais">
                {AREAS.filter((a) => !BARRA_CELULAR.includes(a.id)).map((a) => <ItemNav key={a.id} area={a} atual={a.id === area.id} mini={false} ir={ir} />)}
              </div>
            )}
          </div>
        </FaixaSlot.Provider>
      </IrContext.Provider>
    </OcultarContext.Provider>
  );
}

function ItemNav({ area, atual, mini, ir, selo }: { area: Area; atual: boolean; mini: boolean; ir: (id: string) => void; selo?: number }) {
  const I = ICONE[area.id];
  return (
    <button className="trilho-item" onClick={() => ir(area.id)} aria-current={atual ? "page" : undefined} aria-label={area.rotulo} title={mini ? area.rotulo : area.pergunta}>
      <I size={18} {...traco} aria-hidden="true" />
      {!mini && <span className="rotulo">{area.rotulo}</span>}
      <Selo n={selo} />
    </button>
  );
}

function ItemBarra({ icone: I, rotulo, atual, onClick, selo, expandido }: { icone: LucideIcon; rotulo: string; atual: boolean; onClick: () => void; selo?: number; expandido?: boolean }) {
  return (
    <button className="barra-item" onClick={onClick} aria-current={atual ? "page" : undefined} aria-expanded={expandido}>
      <I size={20} {...traco} aria-hidden="true" />{rotulo}
      {selo ? <span style={{ position: "absolute", top: 6, left: "calc(50% + 6px)" }}><Selo n={selo} /></span> : null}
    </button>
  );
}

/** Marca da Gabi: folha de laudo com o canto dobrado e a etiqueta de evidência presa nela. */
export function Marca() {
  return (
    <svg aria-hidden="true" width="26" height="26" viewBox="0 0 26 26" style={{ flex: "none", fill: "none", stroke: "currentColor", strokeWidth: 1.4, strokeLinejoin: "round" }}>
      <path d="M5 2.5h11l5 5v16H5z" /><path d="M16 2.5v5h5" />
      <path d="M8.5 13h6M8.5 16.5h9M8.5 20h5" strokeLinecap="round" />
      <rect x="14.5" y="17.5" width="7" height="5" style={{ fill: "var(--ambar)", stroke: "var(--ambar-borda)" }} />
    </svg>
  );
}
