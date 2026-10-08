import { useOcultar } from "../lib/ocultar";

const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

/** Valor monetário. A API manda string "1234.56"; aqui só se formata, nunca se calcula. */
export function Valor({ valor }: { valor: string | number }) {
  const oculto = useOcultar();
  return (
    <span style={{ fontVariantNumeric: "tabular-nums" }}>
      {oculto ? "R$ ••••••" : BRL.format(Number(valor)).replace(/ /g, " ")}
    </span>
  );
}
