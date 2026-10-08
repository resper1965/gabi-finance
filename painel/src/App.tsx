import { Shell } from "./componentes/Shell";
import { Vazio } from "./componentes/Estados";

export function App() {
  return <Shell tela={(area) => <Vazio frase={`${area.rotulo} ainda não foi construída nesta fase.`} />} />;
}
