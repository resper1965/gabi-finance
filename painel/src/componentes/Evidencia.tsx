import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useProveniencia } from "../lib/proveniencia";
import { Etiqueta } from "./Etiqueta";
import { formatarDadosAte, formatarHora } from "./Faixa";

/** conferido: a rodada fechou com o extrato; a_conferir: fonte parada, dado desatualizado ou valor incerto; projecao: calculado, ainda não aconteceu. */
export type EstadoEvidencia = "conferido" | "a_conferir" | "projecao";

export interface InfoEvidencia {
  codigo: string;            // "E-01": número do item no laudo
  rotulo: string;            // o que é o valor
  fonte?: string;            // nome da fonte no envelope ("open-finance", "notas-nibo"); sem ela, todas as do envelope
  base?: ReactNode;          // de onde sai o número (contas somadas, regra do cálculo)
  estado?: EstadoEvidencia;  // sem ele, sai do envelope
}

const ESTADO: Record<EstadoEvidencia, [Parameters<typeof Etiqueta>[0]["tipo"], string]> = {
  conferido: ["ok", "conferido"], a_conferir: ["conferir", "a conferir"], projecao: ["nota", "projeção"],
};

/** Liga um gatilho (o código do item) a um quadro de proveniência: fonte → rodada → conferência.
 *  Abre ao passar o mouse (com uma pausa curta) e na hora ao focar pelo teclado ou tocar; Esc fecha. O quadro é fixo na janela,
 *  então nunca é cortado por uma área com rolagem. `zona` vai no elemento que também abre ao passar o mouse (a linha inteira). */
export function useEvidencia(info: InfoEvidencia) {
  const prov = useProveniencia();
  const id = useId();
  const ref = useRef<HTMLButtonElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [pos, setPos] = useState<{ top: number; left: number; acima: boolean } | null>(null);
  const fontes = (prov?.fontes ?? []).filter((f) => !info.fonte || f.nome === info.fonte);
  const parada = fontes.find((f) => f.estado !== "ok");
  const estado: EstadoEvidencia = info.estado ?? (prov && !prov.desatualizado && !parada && prov.dadosAte ? "conferido" : "a_conferir");

  const posicionar = () => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    const acima = r.bottom + 240 > window.innerHeight && r.top > 260;
    setPos({ top: acima ? r.top - 8 : r.bottom + 8, left: Math.max(8, Math.min(r.left, window.innerWidth - 308)), acima });
  };
  const abrir = (atraso = 0) => {
    clearTimeout(timer.current);
    if (atraso) timer.current = setTimeout(posicionar, atraso); else posicionar();
  };
  const fechar = () => { clearTimeout(timer.current); setPos(null); };
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    if (!pos) return;
    const f = () => fechar();
    window.addEventListener("scroll", f, true);
    window.addEventListener("resize", f);
    return () => { window.removeEventListener("scroll", f, true); window.removeEventListener("resize", f); };
  }, [pos]);

  const aberta = pos !== null;
  const [tipo, texto] = ESTADO[estado];
  const quadro = pos && createPortal(
    <div role="tooltip" id={id} className="ev-pop" style={{ top: pos.top, left: pos.left, transform: pos.acima ? "translateY(-100%)" : undefined }}>
      <div className="ev-pop-cab"><strong>{info.rotulo}</strong><span className="mono">{info.codigo}</span></div>
      <ol className="ev-cadeia">
        <li><span className="ev-k">Fonte</span><span className="ev-passo">
          {fontes.length ? fontes.map((f) => f.nome).join(", ") : "sem fonte registrada"}
          {info.base && <span className="celula-sub">{info.base}</span>}</span></li>
        <li><span className="ev-k">Rodada</span><span className="ev-passo">
          {prov?.dadosAte ? <>dados até <span className="mono">{formatarDadosAte(prov.dadosAte)}</span></> : "nenhuma rodada conferida ainda"}
          {prov?.proximaRodada && <span className="celula-sub">próxima às {formatarHora(prov.proximaRodada)}</span>}</span></li>
        <li><span className="ev-k">Conferência</span><span className="ev-passo"><Etiqueta tipo={tipo} texto={texto} />
          {parada && <span className="celula-sub">{parada.nome} parou</span>}</span></li>
      </ol>
      {estado === "projecao" && <p className="ev-pop-nota">Projeção: soma o saldo conferido com o que vence e o que deve entrar. Ainda não aconteceu.</p>}
    </div>, document.body);

  return {
    estado, aberta, quadro,
    gatilho: {
      ref, type: "button" as const, className: "ev", "data-estado": estado, "data-aberta": aberta,
      "aria-describedby": aberta ? id : undefined,
      onFocus: () => abrir(0), onBlur: fechar,
      onClick: () => (aberta ? fechar() : abrir(0)),
      onKeyDown: (e: React.KeyboardEvent) => { if (e.key === "Escape") fechar(); },
    },
    zona: { onMouseEnter: () => abrir(260), onMouseLeave: fechar },
  };
}

/** Etiqueta de evidência em linha: o valor seguido do código do item; passar o mouse, focar ou tocar mostra a proveniência. */
export function Evidencia({ children, ...info }: InfoEvidencia & { children: ReactNode }) {
  const ev = useEvidencia(info);
  return (
    <>
      <button {...ev.gatilho} {...ev.zona}>
        {children}<span className="ev-cod">{info.codigo}</span>
      </button>
      {ev.quadro}
    </>
  );
}
