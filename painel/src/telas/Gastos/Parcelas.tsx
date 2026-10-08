import { Bloco } from "../../componentes/Bloco";
import { Etiqueta } from "../../componentes/Etiqueta";
import { Estat, GradeKpi } from "../../componentes/Kpi";
import { Painel } from "../../componentes/Painel";
import { useCelular } from "../../componentes/Shell";
import { Valor } from "../../componentes/Valor";
import { mesCurto, num } from "../../lib/formato";
import { useApi } from "../../lib/useApi";

interface Item { descricao: string; conta: string; parcela: number; parcelas: number; restante: number; valor_parcela: string; termina_em: string; termina_neste_mes: boolean }
interface Dados { itens: Item[]; por_mes: { mes: string; total: string }[] }
const MES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
const nomeMes = (ym: string) => MES[Number(ym.slice(5, 7)) - 1];

export function Parcelas() {
  const celular = useCelular();
  const leitura = useApi<Dados>("/api/v1/parcelas");
  return (
    <Painel leitura={leitura} arquivo="compras parceladas">
      {(d) => {
        const faltam = d.itens.reduce((s, i) => s + i.restante * num(i.valor_parcela), 0);
        const ultima = d.itens.reduce((m, i) => (i.termina_em > m ? i.termina_em : m), "");
        const terminam = d.itens.filter((i) => i.termina_neste_mes);
        const liberado = terminam.reduce((s, i) => s + num(i.valor_parcela), 0);
        const topo = Math.max(1, ...d.por_mes.map((m) => num(m.total)));
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            <GradeKpi min={190}>
              {d.por_mes[0] && <Estat rotulo={`Comprometido em ${nomeMes(d.por_mes[0].mes)}`}><Valor valor={d.por_mes[0].total} /></Estat>}
              {d.por_mes[1] && <Estat rotulo={`Em ${nomeMes(d.por_mes[1].mes)}`}><Valor valor={d.por_mes[1].total} /></Estat>}
              <Estat rotulo="Falta pagar, no total"><Valor valor={faltam} /></Estat>
              <Estat rotulo="Última parcela">{ultima ? mesCurto(ultima) : "—"}</Estat>
            </GradeKpi>
            {terminam.length > 0 && (
              <div style={{ border: "1px solid var(--ok)", background: "var(--ok-bg)", padding: "12px 14px", display: "flex", gap: 10, alignItems: "flex-start" }}>
                <span aria-hidden="true" style={{ font: "700 14px var(--mono)", color: "var(--ok)" }}>✓</span>
                <span style={{ textWrap: "pretty" }}><strong>Termina neste mês:</strong> {terminam.map((i) => i.descricao).join(", ")}. No mês seguinte, libera <Valor valor={liberado} /> por mês no orçamento.</span>
              </div>
            )}
            <Bloco titulo="Comprometido por mês" nota="soma das parcelas já contratadas, até a última">
              <svg role="img" aria-label="Valor comprometido em parcelas por mês" viewBox="0 0 760 190" style={{ width: "100%", height: "auto", display: "block", overflow: "visible" }}>
                <line x1={44} x2={760} y1={160} y2={160} style={{ stroke: "var(--color-text)" }} />
                {d.por_mes.map((m, i) => {
                  const larg = (716 / Math.max(1, d.por_mes.length)), h = (num(m.total) / topo) * 130, x = 44 + i * larg + larg * 0.2;
                  return <g key={m.mes}><rect x={x} y={160 - h} width={larg * 0.6} height={h} style={{ fill: "var(--s3)" }} /><text x={x + larg * 0.3} y={160 - h - 5} style={{ fill: "var(--color-text)", font: "600 10.5px var(--mono)", textAnchor: "middle" }}>{Math.round(num(m.total)).toLocaleString("pt-BR")}</text><text x={x + larg * 0.3} y={178} style={{ fill: "var(--ink2)", font: "500 10.5px var(--mono)", textAnchor: "middle" }}>{mesCurto(m.mes)}</text></g>;
                })}
              </svg>
            </Bloco>
            <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <h3 style={{ margin: 0, fontSize: 20 }}>Compras parceladas</h3>
              {!celular ? (
                <table className="table" style={{ fontSize: 13.5 }}>
                  <thead><tr><th>Compra</th><th>Cartão</th><th style={{ textAlign: "right" }}>Parcela</th><th>Andamento</th><th style={{ textAlign: "right" }}>Falta</th><th>Termina</th></tr></thead>
                  <tbody>{d.itens.map((i) => (
                    <tr key={i.descricao + i.conta}>
                      <td style={{ fontWeight: 600 }}>{i.descricao}</td><td>{i.conta}</td>
                      <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}><Valor valor={i.valor_parcela} /></td>
                      <td style={{ minWidth: 140 }}><span style={{ display: "flex", alignItems: "center", gap: 8 }}><span style={{ flex: 1, height: 5, background: "var(--line2)" }}><span style={{ display: "block", height: "100%", width: `${(i.parcela / i.parcelas) * 100}%`, background: "var(--color-accent)" }} /></span><span style={{ font: "500 12px var(--mono)" }}>{i.parcela}/{i.parcelas}</span></span></td>
                      <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: 600 }}><Valor valor={i.restante * num(i.valor_parcela)} /></td>
                      <td>{i.termina_neste_mes ? <Etiqueta tipo="ok" texto="este mês" /> : mesCurto(i.termina_em)}</td>
                    </tr>))}</tbody>
                </table>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>{d.itens.map((i) => (
                  <div key={i.descricao + i.conta} style={{ border: "1px solid var(--color-divider)", padding: "10px 12px", display: "flex", flexDirection: "column", gap: 6 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}><span style={{ fontWeight: 600 }}>{i.descricao}</span><span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700 }}><Valor valor={i.valor_parcela} /></span></div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}><span style={{ flex: 1, height: 5, background: "var(--line2)" }}><span style={{ display: "block", height: "100%", width: `${(i.parcela / i.parcelas) * 100}%`, background: "var(--color-accent)" }} /></span><span style={{ font: "500 12px var(--mono)" }}>{i.parcela}/{i.parcelas}</span></div>
                    <div style={{ fontSize: 12, color: "var(--ink2)" }}>{i.conta} · falta <Valor valor={i.restante * num(i.valor_parcela)} /> · termina {mesCurto(i.termina_em)}</div>
                  </div>))}
                </div>
              )}
            </section>
          </div>
        );
      }}
    </Painel>
  );
}
