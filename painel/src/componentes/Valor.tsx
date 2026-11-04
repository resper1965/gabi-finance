import { useOcultar } from "../lib/ocultar";
import { formatarBRL } from "../lib/formato";

/** Valor monetário. A API manda string "1234.56"; aqui só se formata, nunca se calcula. */
export function Valor({ valor }: { valor: string | number }) {
  const oculto = useOcultar();
  return (
    <span style={{ fontVariantNumeric: "tabular-nums" }}>
      {oculto ? "R$ ••••••" : formatarBRL(valor)}
    </span>
  );
}
