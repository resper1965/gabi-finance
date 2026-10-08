import { Component, type ReactNode } from "react";
import { Erro } from "./Estados";

/** Se uma tela quebrar (formato inesperado da API), mostra o estado de erro em vez de uma página em branco. */
export class Limite extends Component<{ arquivo: string; children: ReactNode }, { erro: Error | null }> {
  state = { erro: null as Error | null };
  static getDerivedStateFromError(erro: Error) { return { erro }; }
  render() {
    return this.state.erro ? <Erro arquivo={this.props.arquivo} motivo={`a tela não conseguiu ler os dados (${this.state.erro.message})`} /> : this.props.children;
  }
}
