import { createContext, useContext } from "react";

/** "Ocultar valores" (olho no cabeçalho): true troca todo valor monetário por R$ ••••••. */
export const OcultarContext = createContext(false);
export const useOcultar = () => useContext(OcultarContext);

/** Navegar para outra área/aba a partir de uma tela (ex.: item de "Precisa da sua atenção"). */
export const IrContext = createContext<(area: string, aba?: string) => void>(() => {});
export const useIr = () => useContext(IrContext);
