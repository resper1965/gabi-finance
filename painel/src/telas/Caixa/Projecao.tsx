import { Bloco } from "../../componentes/Bloco";
import { Estat, GradeKpi } from "../../componentes/Kpi";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { dataCurta } from "../../lib/formato";
import { useApi } from "../../lib/useApi";

interface Dia { dia: string; entradas: string; saidas: string; saldo: string }
interface Bloco_ { qtd: number; liquido: string }

/** Caixa › Previsão: saldo de hoje mais o que entra e sai dia a dia. Entrada só de nota a vencer e contrato recorrente; o que o Nibo
 *  mostra vencido e não baixado fica à parte (fila de conferência com o extrato) e nunca soma no saldo. */
export function Projecao() {
  const leitura = useApi<{ saldo_inicial: string; dias: Dia[]; menor_saldo: { dia: string; saldo: string }; aviso: string }>("/api/v1/caixa/projecao?dias=30");
  const previsao = useApi<{ a_confirmar: Bloco_; antigas: Bloco_ }>("/api/v1/cobrar/previsao");
  return (
    <Painel leitura={leitura} arquivo="previsão de caixa">
      {(d) => {
        const movimento = d.dias.filter((x, i) => i === 0 || Number(x.entradas) !== 0 || Number(x.saidas) !== 0);
        const fila = previsao.env?.dados;
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <GradeKpi min={170}>
              <Estat rotulo="Saldo hoje"><Valor valor={d.saldo_inicial} /></Estat>
              <Estat rotulo="Menor saldo"><Valor valor={d.menor_saldo.saldo} /><small style={{ display: "block", color: "var(--ink2)" }}>{dataCurta(d.menor_saldo.dia)}</small></Estat>
              <Estat rotulo={`Saldo em ${d.dias.length} dias`}><Valor valor={d.dias[d.dias.length - 1]?.saldo ?? d.saldo_inicial} /></Estat>
            </GradeKpi>
            <Bloco titulo="Saldo projetado por dia" nota="só os dias com entrada ou saída">
              <table aria-label="Saldo projetado por dia" style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead><tr style={{ textAlign: "left", color: "var(--ink2)", fontSize: 12.5 }}><th>Dia</th><th>Entradas</th><th>Saídas</th><th>Saldo</th></tr></thead>
                <tbody>
                  {movimento.map((x) => (
                    <tr key={x.dia} style={{ borderTop: "1px solid var(--line2)" }}>
                      <td>{dataCurta(x.dia)}</td><td><Valor valor={x.entradas} /></td><td><Valor valor={x.saidas} /></td><td><Valor valor={x.saldo} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Bloco>
            <section role="region" aria-label="Fila de conferência com o extrato" style={{ border: "1px dashed var(--line3)", padding: 14, display: "flex", flexDirection: "column", gap: 6 }}>
              <strong>Fila de conferência com o extrato (fora da previsão)</strong>
              {fila ? (
                <>
                  <span>{fila.a_confirmar.qtd} notas vencidas há até 60 dias e não baixadas no Nibo: <Valor valor={fila.a_confirmar.liquido} /></span>
                  <span>{fila.antigas.qtd} notas antigas (mais de 60 dias) sem baixa: <Valor valor={fila.antigas.liquido} /></span>
                </>
              ) : <span style={{ color: "var(--ink2)" }}>carregando…</span>}
            </section>
            <span style={{ fontSize: 12.5, color: "var(--ink2)" }}>{d.aviso}</span>
          </div>
        );
      }}
    </Painel>
  );
}
