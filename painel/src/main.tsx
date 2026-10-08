import "@fontsource/barlow/400.css";
import "@fontsource/barlow/500.css";
import "@fontsource/barlow/700.css";
import "@fontsource/barlow-condensed/400.css";
import "@fontsource/barlow-condensed/600.css";
import "./tema/industry.css";
import "./tema/gabi.css";
import { createRoot } from "react-dom/client";
import { App } from "./App";

createRoot(document.getElementById("raiz")!).render(<App />);
