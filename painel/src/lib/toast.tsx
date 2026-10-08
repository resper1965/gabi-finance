import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

const Ctx = createContext<(msg: string) => void>(() => {});
export const useToast = () => useContext(Ctx);

/** Toast: faixa escura na base, centralizada, some em 5 s. Usado em toda confirmação de ação. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [msg, setMsg] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const mostrar = useCallback((m: string) => {
    setMsg(m);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setMsg(null), 5000);
  }, []);
  return (
    <Ctx.Provider value={mostrar}>
      {children}
      {msg && <div role="status" data-toast style={{ position: "fixed", left: "50%", bottom: 24, transform: "translateX(-50%)", padding: "10px 16px", background: "var(--proto)", color: "#e3ebf3", boxShadow: "var(--shadow-md)", zIndex: 50 }}>{msg}</div>}
    </Ctx.Provider>
  );
}
