import { useState } from "react";
import { Bloco } from "../../componentes/Bloco";
import { Estat, GradeKpi } from "../../componentes/Kpi";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { BarrasSemanas, type Semana } from "../../graficos/BarrasSemanas";
import { dataCurta, num } from "../../lib/formato";
import { useOcultar } from "../../lib/ocultar";
import { useApi } from "../../lib/useApi";

interface Lanc { id: number; data: string; estabelecimento: string; valor: string; conta: string; categoria: { nome: string | null } }

const soma = (l: { valor: string }[]) => l.reduce((s, i) => s + num(i.valor), 0);

export function Semanas() {
  const oculto = useOcultar();
  const leitura = useApi<{ semanas: Semana[] }>("/api/v1/caixa/semanas");
  const [inicio, setInicio] = useState<string | null>(null);
  const sem = leitura.env?.dados.semanas.find((s) => s.inicio === inicio);
  const lanc = useApi<{ itens: Lanc[] }>(sem && !sem.projecao ? `/api/v1/lancamentos?de=${sem.inicio}&ate=${sem.fim}&limite=200` : null);
  return (
    <Painel leitura={leitura} arquivo="extratos por semana">
      {(d) => {
        const reais = d.semanas.filter((s) => !s.projecao);
        const entradas = reais.reduce((s, w) => s + Math.abs(soma(w.entradas)), 0), saidas = reais.reduce((s, w) => s + Math.abs(soma(w.saidas)), 0);
        const ultima = d.semanas[d.semanas.length - 1];
        return (
          <>
            <GradeKpi min={170}>
              <Estat rotulo="Entradas realizadas"><Valor valor={entradas} /></Estat>
              <Estat rotulo="Saídas realizadas"><Valor valor={saidas} /></Estat>
              <Estat rotulo="Líquido no período"><Valor valor={entradas - saidas} /></Estat>
              <Estat rotulo={`Saldo projetado em ${d.semanas.filter((s) => s.projecao).length} semanas`}>{ultima?.saldo ? <Valor valor={ultima.saldo} /> : "—"}</Estat>
            </GradeKpi>
            <Bloco titulo="Entradas e saídas por semana" nota="clique numa semana para ver os lançamentos">
              <BarrasSemanas semanas={d.semanas} escolhida={inicio} aoEscolher={setInicio} oculto={oculto} />
            </Bloco>
            {sem && (
              <Bloco>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                  <div>
                    <h3 style={{ margin: 0, fontSize: 20 }}>Semana de {dataCurta(sem.inicio)} a {dataCurta(sem.fim)}</h3>
                    <span style={{ fontSize: 12.5, color: "var(--ink2)" }}>entradas <Valor valor={Math.abs(soma(sem.entradas))} /> · saídas <Valor valor={Math.abs(soma(sem.saidas))} /> · líquido <Valor valor={soma(sem.entradas) + soma(sem.saidas)} /></span>
                  </div>
                  <button className="btn btn-secondary" onClick={() => setInicio(null)}>Fechar</button>
                </div>
                {sem.projecao && <span style={{ font: "500 12px var(--mono)", color: "var(--warn)" }}>▲ semana futura: valores projetados, ainda não aconteceram</span>}
                <div style={{ display: "flex", flexDirection: "column" }}>
                  {sem.projecao
                    ? [...sem.entradas, ...sem.saidas].map((i) => (
                        <div key={i.categoria + i.valor} style={{ display: "grid", gridTemplateColumns: "52px minmax(0,1fr) auto", gap: "4px 12px", padding: "9px 0", borderTop: "1px solid var(--line2)", alignItems: "baseline" }}>
                          <span /><span style={{ fontWeight: 600 }}>{i.categoria}</span><span style={{ fontWeight: 600 }}><Valor valor={i.valor} /></span>
                        </div>))
                    : (lanc.env?.dados.itens ?? []).map((l) => (
                        <div key={l.id} style={{ display: "grid", gridTemplateColumns: "52px minmax(0,1fr) auto", gap: "4px 12px", padding: "9px 0", borderTop: "1px solid var(--line2)", alignItems: "baseline" }}>
                          <span style={{ font: "500 12px var(--mono)", color: "var(--ink2)" }}>{dataCurta(l.data)}</span>
                          <span style={{ minWidth: 0 }}><span style={{ fontWeight: 600 }}>{l.estabelecimento}</span> <span style={{ fontSize: 12, color: "var(--ink2)" }}>· {l.categoria.nome ?? "sem categoria"} · {l.conta}</span></span>
                          <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 600, color: num(l.valor) > 0 ? "var(--ok)" : undefined, whiteSpace: "nowrap" }}><Valor valor={l.valor} /></span>
                        </div>))}
                  {!sem.projecao && lanc.env && lanc.env.dados.itens.length === 0 && <p style={{ color: "var(--ink2)", margin: 0 }}>Nenhum lançamento nesta semana.</p>}
                </div>
              </Bloco>
            )}
          </>
        );
      }}
    </Painel>
  );
}
