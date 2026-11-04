import { useCallback, useEffect, useRef, useState } from "react";
import { api, ErroApi, type Envelope } from "./api";

export interface Leitura<T> {
  estado: "carregando" | "ok" | "erro";
  env: Envelope<T> | null; // mantém os últimos dados bons mesmo em erro
  erro: ErroApi | null;
  recarregar: () => Promise<void>; // resolve quando a releitura termina (ok ou erro)
}

interface Guardado<T> { url: string | null; env: Envelope<T> | null; erro: ErroApi | null }

export function useApi<T>(url: string | null): Leitura<T> {
  // dado, erro e a url a que pertencem ficam juntos: trocar de url nunca mostra o dado da anterior
  const [g, setG] = useState<Guardado<T>>({ url: null, env: null, erro: null });
  const [rev, setRev] = useState(0);
  const esperando = useRef<(() => void)[]>([]);
  const liberar = () => { const f = esperando.current; esperando.current = []; f.forEach((r) => r()); };
  useEffect(() => {
    if (url === null) return;
    let vivo = true;
    api.get<T>(url).then(
      (e) => { if (vivo) { setG({ url, env: e, erro: null }); liberar(); } },
      (x) => { if (vivo) { setG((p) => ({ url, env: p.url === url ? p.env : null, erro: x as ErroApi })); liberar(); } },
    );
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, rev]);
  const recarregar = useCallback(() => new Promise<void>((r) => { esperando.current.push(r); setRev((n) => n + 1); }), []);
  const atual = g.url === url;
  const env = atual ? g.env : null;
  const erro = atual ? g.erro : null;
  const estado: Leitura<T>["estado"] = erro ? "erro" : env ? "ok" : "carregando";
  return { estado, env, erro, recarregar };
}
