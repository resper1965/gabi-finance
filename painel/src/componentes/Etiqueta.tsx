export type TipoEtiqueta =
  | "erro" | "conferir" | "ok" | "nota" | "atencao" | "parado" | "regra" | "banco" | "paperless" | "ajuste";

/** Carimbo de estado: régua dupla, caixa alta, a cor nunca sozinha (o texto diz o estado).
 *  erro = vermelho (atrasado, divergente); ok = verde (pago, conferido); nota = azul; conferir = etiqueta âmbar (a conferir).
 *  parado, regra, banco, paperless e ajuste são rótulos de origem: régua simples, sem cor de estado. */
export function Etiqueta({ tipo, texto }: { tipo: TipoEtiqueta; texto: string }) {
  return <span className="carimbo" data-tipo={tipo}>{texto}</span>;
}
