import { useRef, useState } from "react";
import { useToast } from "./toast";

export type Acao = ReturnType<typeof useAcao>;

/** Executa uma ação sob trava (uma por vez na tela), avisa o resultado e espera a releitura; em erro mantém a tela como está e guarda a mensagem na chave (linha) que falhou. */
export function useAcao() {
  const avisar = useToast();
  const trava = useRef(false);
  const [ocupado, setOcupado] = useState(false);
  const [erros, setErros] = useState<Record<string, string>>({});
  const agir = async (chave: string, fn: () => Promise<unknown>, ok: string, recarregar?: () => Promise<void>) => {
    if (trava.current) return false;
    trava.current = true; setOcupado(true);
    setErros((e) => { const { [chave]: _, ...resto } = e; return resto; });
    try { await fn(); avisar(ok); await recarregar?.(); return true; }
    catch (e) { const m = (e as Error).message; setErros((x) => ({ ...x, [chave]: m })); avisar(m); return false; }
    finally { trava.current = false; setOcupado(false); }
  };
  return { ocupado, erros, agir };
}
export const Aviso = ({ erro, id }: { erro?: string; id?: string }) => (erro ? <p role="alert" id={id} className="erro-linha">Erro: {erro}</p> : null);

