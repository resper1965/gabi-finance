import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

/** Ação opcional do toast (ex.: "Desfazer"): um botão dentro da faixa; clicar fecha o toast e roda `fazer`. */
export interface AcaoToast { rotulo: string; fazer: () => void }
const Ctx = createContext<(msg: string, acao?: AcaoToast) => void>(() => {});
export const useToast = () => useContext(Ctx);

/** Toast: faixa escura na base, centralizada, some em 5 s. Usado em toda confirmação de ação. */
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
        <div role="status" data-toast style={{ position: "fixed", left: "50%", bottom: 24, transform: "translateX(-50%)", padding: "10px 16px", background: "var(--proto)", color: "#e3ebf3", boxShadow: "var(--shadow-md)", zIndex: 50, display: "flex", gap: 14, alignItems: "center" }}>
          {msg.texto}
          {msg.acao && <button type="button" style={{ background: "none", border: 0, padding: 0, color: "inherit", font: "inherit", fontWeight: 700, textDecoration: "underline", cursor: "pointer" }}
            onClick={() => { const a = msg.acao!; clearTimeout(timer.current); setMsg(null); a.fazer(); }}>{msg.acao.rotulo}</button>}
        </div>)}
    </Ctx.Provider>
  );
}
