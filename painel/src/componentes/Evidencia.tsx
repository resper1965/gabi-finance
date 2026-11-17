import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useProveniencia, type FonteEvidencia } from "../lib/proveniencia";
import { Etiqueta } from "./Etiqueta";
import { formatarDadosAte, formatarHora } from "./Faixa";

/** conferido: a rodada fechou com o extrato; a_conferir: fonte parada, dado desatualizado ou valor incerto; projecao: calculado, ainda não aconteceu. */
export type EstadoEvidencia = "conferido" | "a_conferir" | "projecao";

export interface InfoEvidencia {
  codigo: string;            // "AP-01": código estável do item na tela (prefixo da tela + número fixo)
  rotulo: string;            // o que é o valor
  fontes: FonteEvidencia[];  // cada entrada que alimenta o número; um item composto lista todas
  cita?: string;             // itens de outras telas que o número soma ("AP-01 + AP-02")
  base?: ReactNode;          // regra do cálculo
  estado?: EstadoEvidencia;  // sem ele, sai do envelope (estado das fontes que o envelope descreve)
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
  const abertaAntes = useRef(false); // estado no instante do toque: o foco que vem com o toque já abre, então o clique não pode fechar de novo
  const [pos, setPos] = useState<{ top: number; left: number; acima: boolean } | null>(null);
  const doEnvelope = (nome: string) => prov?.fontes.find((f) => f.nome === nome);
  const descritas = info.fontes.map((f) => doEnvelope(f.nome)).filter((f) => f !== undefined);
  const parada = descritas.find((f) => f.estado !== "ok");
  const estado: EstadoEvidencia = info.estado ?? (prov && !prov.desatualizado && !parada && prov.dadosAte && descritas.length ? "conferido" : "a_conferir");

  const posicionar = () => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    const altura = 150 + info.fontes.length * 64 + (info.cita ? 20 : 0); // estimativa: o quadro cresce uma linha por fonte
    const acima = r.bottom + 8 + altura > window.innerHeight && r.top - 8 - altura > 0;
    const top = acima ? r.top - 8 : Math.max(8, Math.min(r.bottom + 8, window.innerHeight - altura - 8));
    setPos({ top, left: Math.max(8, Math.min(r.left, window.innerWidth - 348)), acima });
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
        <li><span className="ev-k">{info.fontes.length > 1 ? "Fontes" : "Fonte"}</span><span className="ev-passo ev-fontes">
          {info.fontes.map((f) => {
            const e = doEnvelope(f.nome);
            return (
              <span key={f.nome} className="ev-fonte">
                <span><span className="mono">{f.nome}</span> · {f.papel}</span>
                <span className="celula-sub">{e ? (e.estado === "ok" ? "no envelope: em dia" : `no envelope: ${e.estado}`) : "fora do envelope: sem estado informado"}</span>
              </span>);
          })}
          {info.cita && <span className="celula-sub">soma {info.cita}</span>}
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
      onPointerDown: () => { abertaAntes.current = aberta; },
      onClick: () => { if (abertaAntes.current) fechar(); else abrir(0); abertaAntes.current = false; },
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
