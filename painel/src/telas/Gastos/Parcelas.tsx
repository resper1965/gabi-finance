import { Bloco } from "../../componentes/Bloco";
import { Etiqueta } from "../../componentes/Etiqueta";
import { Achados } from "../../componentes/Achados";
import { CalendarCheck } from "lucide-react";
import { Painel } from "../../componentes/Painel";
import { useCelular } from "../../componentes/Shell";
import { Valor } from "../../componentes/Valor";
import { mesCurto, num } from "../../lib/formato";
import { FONTE } from "../../lib/proveniencia";
import { useApi } from "../../lib/useApi";
import { useOcultar } from "../../lib/ocultar";

interface Item { descricao: string; conta: string; parcela: number; parcelas: number; restante: number; valor_parcela: string; termina_em: string; termina_neste_mes: boolean }
interface Dados { itens: Item[]; por_mes: { mes: string; total: string }[] }
const MES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
const nomeMes = (ym: string) => MES[Number(ym.slice(5, 7)) - 1];

export function Parcelas() {
  const celular = useCelular();
  const oculto = useOcultar();
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
          <div className="pilha" style={{ gap: 32, maxWidth: 1120 }}>
            <Achados itens={[
              ...(d.por_mes[0] ? [{ codigo: "PC-01", rotulo: `Comprometido em ${nomeMes(d.por_mes[0].mes)}`, fontes: [FONTE.extrato()], base: "parcelas já contratadas que caem neste mês", valor: <Valor valor={d.por_mes[0].total} /> }] : []),
              ...(d.por_mes[1] ? [{ codigo: "PC-02", rotulo: `Em ${nomeMes(d.por_mes[1].mes)}`, fontes: [FONTE.extrato()], base: "parcelas já contratadas para o mês seguinte", valor: <Valor valor={d.por_mes[1].total} />,
                prova: liberado > 0 ? <>libera <Valor valor={liberado} /> por mês</> : undefined }] : []),
              { codigo: "PC-03", rotulo: "Falta pagar, no total", fontes: [FONTE.extrato()], base: `${d.itens.length} compras: parcelas restantes × valor da parcela`, valor: <Valor valor={faltam} /> },
              { codigo: "PC-04", rotulo: "Última parcela", fontes: [FONTE.extrato()], base: "a compra que termina por último", valor: <span className="mono" style={{ fontSize: "var(--t1)" }}>{ultima ? mesCurto(ultima) : "—"}</span> },
            ]} />
            {terminam.length > 0 && (
              <div className="quadro" data-tom="ok">
                <CalendarCheck size={18} strokeWidth={1.7} aria-hidden="true" />
                <span><strong>Termina neste mês:</strong> {terminam.map((i) => i.descricao).join(", ")}. No mês seguinte, libera <Valor valor={liberado} /> por mês no orçamento.</span>
              </div>
            )}
            <Bloco titulo="Comprometido por mês" nota="soma das parcelas já contratadas, até a última">
              <svg role="img" aria-label="Valor comprometido em parcelas por mês" viewBox="0 0 760 190" className="grafico" style={{ width: "100%", height: "auto", overflow: "visible" }}>
                <line x1={44} x2={760} y1={160} y2={160} style={{ stroke: "var(--tinta)" }} />
                {d.por_mes.map((m, i) => {
                  const larg = (716 / Math.max(1, d.por_mes.length)), h = (num(m.total) / topo) * 130, x = 44 + i * larg + larg * 0.2;
                  return <g key={m.mes}><rect x={x} y={160 - h} width={larg * 0.6} height={h} style={{ fill: i === 0 ? "var(--serie-1)" : "var(--serie-3)" }} /><text x={x + larg * 0.3} y={160 - h - 5} style={{ fill: "var(--tinta)", textAnchor: "middle" }}>{oculto ? "••••" : Math.round(num(m.total)).toLocaleString("pt-BR")}</text><text x={x + larg * 0.3} y={178} style={{ textAnchor: "middle" }}>{mesCurto(m.mes)}</text></g>;
                })}
              </svg>
            </Bloco>
            <Bloco titulo="Compras parceladas" nota={`${d.itens.length} compras em andamento`}>
              {!celular ? (
                <table className="tabela">
                  <thead><tr><th>Compra</th><th>Cartão</th><th className="num">Parcela</th><th>Andamento</th><th className="num">Falta</th><th>Termina</th></tr></thead>
                  <tbody>{d.itens.map((i) => (
                    <tr key={i.descricao + i.conta}>
                      <td className="forte">{i.descricao}</td><td className="suave">{i.conta}</td>
                      <td className="num"><Valor valor={i.valor_parcela} /></td>
                      <td style={{ minWidth: 160 }}><span className="fila" style={{ flexWrap: "nowrap" }}><span className="barra-fina cresce"><span style={{ width: `${(i.parcela / i.parcelas) * 100}%` }} /></span><span className="mono">{i.parcela}/{i.parcelas}</span></span></td>
                      <td className="num forte"><Valor valor={i.restante * num(i.valor_parcela)} /></td>
                      <td>{i.termina_neste_mes ? <Etiqueta tipo="ok" texto="este mês" /> : <span className="mono">{mesCurto(i.termina_em)}</span>}</td>
                    </tr>))}</tbody>
                </table>
              ) : (
                <ul className="pauta">{d.itens.map((i) => (
                  <li key={i.descricao + i.conta} className="pilha-curta">
                    <div className="fila-entre" style={{ flexWrap: "nowrap" }}><span className="linha-titulo">{i.descricao}</span><span className="linha-valor"><Valor valor={i.valor_parcela} /></span></div>
                    <div className="fila" style={{ flexWrap: "nowrap" }}><span className="barra-fina cresce"><span style={{ width: `${(i.parcela / i.parcelas) * 100}%` }} /></span><span className="mono">{i.parcela}/{i.parcelas}</span></div>
                    <div className="miudo">{i.conta} · falta <Valor valor={i.restante * num(i.valor_parcela)} /> · termina {mesCurto(i.termina_em)}</div>
                  </li>))}
                </ul>
              )}
            </Bloco>
          </div>
        );
      }}
    </Painel>
  );
}
