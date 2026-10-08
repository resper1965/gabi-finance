import { createContext, useContext } from "react";

/** "Ocultar valores" (olho no cabeçalho): true troca todo valor monetário por R$ ••••••. */
export const OcultarContext = createContext(false);
export const useOcultar = () => useContext(OcultarContext);
