import { useCallback, useEffect, useState } from "react";
import { api, ErroApi, type Envelope } from "./api";

export interface Leitura<T> {
  estado: "carregando" | "ok" | "erro";
  env: Envelope<T> | null; // mantém os últimos dados bons mesmo em erro
  erro: ErroApi | null;
  recarregar: () => void;
}

export function useApi<T>(url: string | null): Leitura<T> {
  const [env, setEnv] = useState<Envelope<T> | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [estado, setEstado] = useState<Leitura<T>["estado"]>("carregando");
  const [rev, setRev] = useState(0);
  useEffect(() => {
    if (url === null) return;
    let vivo = true;
    setEstado((e) => (env ? e : "carregando"));
    api.get<T>(url).then(
      (e) => { if (vivo) { setEnv(e); setErro(null); setEstado("ok"); } },
      (x) => { if (vivo) { setErro(x as ErroApi); setEstado("erro"); } },
    );
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, rev]);
  const recarregar = useCallback(() => setRev((n) => n + 1), []);
  return { estado, env, erro, recarregar };
}
