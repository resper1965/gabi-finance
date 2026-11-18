import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

/** Ação opcional do toast (ex.: "Desfazer"): um botão dentro da faixa; clicar fecha o toast e roda `fazer`. */
export interface AcaoToast { rotulo: string; fazer: () => void }
const Ctx = createContext<(msg: string, acao?: AcaoToast) => void>(() => {});
export const useToast = () => useContext(Ctx);

/** Toast: faixa grafite na base, centralizada, some em 5 s. Usado em toda confirmação de ação. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [msg, setMsg] = useState<{ texto: string; acao?: AcaoToast } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const mostrar = useCallback((texto: string, acao?: AcaoToast) => {
    setMsg({ texto, acao });
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setMsg(null), 5000);
  }, []);
  return (
    <Ctx.Provider value={mostrar}>
      {children}
      {msg && (
        <div role="status" data-toast className="toast" data-celular={typeof window !== "undefined" && !!window.matchMedia?.("(max-width: 759px)").matches}>
          {msg.texto}
          {msg.acao && <button type="button"
            onClick={() => { const a = msg.acao!; clearTimeout(timer.current); setMsg(null); a.fazer(); }}>{msg.acao.rotulo}</button>}
        </div>)}
    </Ctx.Provider>
  );
}
