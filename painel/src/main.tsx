import "@fontsource-variable/public-sans/wght.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "./tema/tokens.css";
import "./tema/laudo.css";
import { createRoot } from "react-dom/client";
import { App } from "./App";

createRoot(document.getElementById("raiz")!).render(<App />);
