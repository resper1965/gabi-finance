import { Bloco } from "../../componentes/Bloco";
import { Etiqueta } from "../../componentes/Etiqueta";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { dataCurta } from "../../lib/formato";
import { useApi } from "../../lib/useApi";

interface Nota { numero: string; tomador: string; emissao: string; vencimento: string | null; bruto: string; liquido: string; situacao: string; nibo_pago: boolean; pdf: boolean; xml: boolean }
interface Totais { a_vencer: string; a_confirmar: string; antigas: string; nibo_diz_pago: string }

const GRUPOS: [string, string, keyof Totais][] = [
  ["a_vencer", "A receber (notas a vencer)", "a_vencer"],
  ["a_confirmar", "Vencidas: confirmar pelo extrato", "a_confirmar"],
  ["antiga", "Antigas (mais de 60 dias, provável baixa que faltou no Nibo)", "antigas"],
  ["nibo_diz_pago", "O Nibo diz pago (não é prova de recebimento)", "nibo_diz_pago"],
];

/** Cobrar › Notas a receber: as NFS-e do Nibo. O Nibo é defasado: "pago" lá não vira "recebido" aqui; o recebimento real é o crédito no extrato. */
export function NotasAReceber() {
  const leitura = useApi<{ itens: Nota[]; totais: Totais }>("/api/v1/cobrar/notas");
  return (
    <Painel leitura={leitura} arquivo="notas a receber">
      {(d) => (
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          {GRUPOS.map(([sit, titulo, chave]) => {
            const itens = d.itens.filter((n) => n.situacao === sit);
            if (itens.length === 0) return null;
            return (
              <Bloco key={sit} titulo={titulo} nota={`${itens.length} nota(s) · líquido ${Number(d.totais[chave]).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`}>
                <section role="region" aria-label={sit === "a_vencer" ? "A receber" : titulo}>
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead><tr style={{ textAlign: "left", color: "var(--ink2)", fontSize: 12.5 }}><th>Nota</th><th>Tomador</th><th>Vence</th><th>Bruto</th><th>Líquido</th><th></th></tr></thead>
                    <tbody>
                      {itens.map((n) => (
                        <tr key={n.numero + n.tomador} style={{ borderTop: "1px solid var(--line2)" }}>
                          <td>{n.numero}</td><td>{n.tomador}</td><td>{n.vencimento ? dataCurta(n.vencimento) : "—"}</td><td><Valor valor={n.bruto} /></td><td><Valor valor={n.liquido} /></td>
                          <td>{n.nibo_pago && <Etiqueta tipo="conferir" texto="Nibo diz pago" />}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </section>
              </Bloco>
            );
          })}
          <span style={{ fontSize: 12.5, color: "var(--ink2)" }}>Valores líquidos, depois das retenções. Recebimento de verdade = crédito no extrato do banco; a conciliação por valor chega com o extrato conferido.</span>
        </div>
      )}
    </Painel>
  );
}
