import { useState } from "react";
import { Bloco } from "../../componentes/Bloco";
import { Painel } from "../../componentes/Painel";
import { useCelular } from "../../componentes/Shell";
import { Valor } from "../../componentes/Valor";
import { corDestino, type Fluxo, type No } from "../../graficos/Sankey";
import { useFiltros } from "../../lib/filtros";
import { dataCurta, num } from "../../lib/formato";
import { useApi } from "../../lib/useApi";

interface Destino {
  periodo: { de: string; ate: string }; nos: No[]; fluxos: Fluxo[]; total: string;
  comparacao: { categoria: string; atual: string; anterior: string; variacao: string }[];
}
interface Agrupado { itens: { nome: string; valor: string; pct: number; variacao: string }[]; total: string }
type Vista = "categoria" | "fornecedor" | "gastador" | "pessoa";
const ROTULO: Record<Vista, string> = { categoria: "Categorias", fornecedor: "Fornecedores", gastador: "Quem gastou", pessoa: "Para quem foi" };
const MES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
const ROTULO_PERIODO: Record<string, string> = { semana: "Últimos 7 dias", "12m": "Últimos 12 meses" };
const pct = (a: number, b: number) => (b ? `${Math.round((a / b) * 100)}%` : "0%");

export function ParaOndeVai() {
  const { periodo } = useFiltros();
  const celular = useCelular();
  const [vista, setVista] = useState<Vista>("categoria");
  const [escolhido, setEscolhido] = useState<{ nome: string; tipo: string } | null>(null);
  const destino = useApi<Destino>(`/api/v1/destino?periodo=${periodo}`);
  const agrupado = useApi<Agrupado>(`/api/v1/destino/agrupado?periodo=${periodo}&por=${vista}`);
  const categorias = useApi<{ itens: { id: number; nome: string }[] }>("/api/v1/cadastros/categorias").env?.dados.itens ?? [];
  const empresas = useApi<{ itens: { id: string | number; nome: string }[] }>("/api/v1/cadastros/empresas").env?.dados.itens ?? [];
  const pessoas = useApi<{ itens: { id: string | number; nome: string }[] }>("/api/v1/cadastros/pessoas").env?.dados.itens ?? [];
  let filtro: string | null = null;
  if (escolhido) {
    const emp = empresas.find((e) => escolhido.nome === `A receber: ${e.nome}`);
    const cat = categorias.find((c) => c.nome === escolhido.nome);
    const pes = escolhido.tipo === "pessoa" ? pessoas.find((x) => x.nome === escolhido.nome) : undefined;
    const gas = escolhido.tipo === "gastador" ? pessoas.find((x) => x.nome === escolhido.nome) : undefined;
    filtro = escolhido.tipo === "gastador" ? (gas ? `gastador=${gas.id}` : escolhido.nome === "(a indicar)" ? "pendente=gastador" : null) : escolhido.tipo === "origem" ? `conta=${encodeURIComponent(escolhido.nome)}` : pes ? `para_quem=${pes.id}` : emp ? `empresa=${emp.id}` : cat ? `categoria=${cat.id}` : `texto=${encodeURIComponent(escolhido.nome)}`;
  }
  const lanc = useApi<{ itens: { id: number; data: string; estabelecimento: string; valor: string; conta: string; categoria: { nome: string | null } }[] }>(
    filtro && destino.env ? `/api/v1/lancamentos?${filtro}&de=${destino.env.dados.periodo.de}&ate=${destino.env.dados.periodo.ate}&limite=50` : null);

  return (
    <Painel leitura={destino} arquivo="custos do período">
      {(d) => {
        const total = num(d.total);
        const destinos = d.nos.filter((n) => n.tipo === "destino").map((n) => ({ nome: n.nome, valor: d.fluxos.filter((f) => f.para === n.nome).reduce((s, f) => s + num(f.valor), 0) })).sort((a, b) => b.valor - a.valor);
        const pessoal = destinos.find((x) => x.nome === "Consumo pessoal")?.valor ?? 0;
        const rotulo = periodo === "mes" ? MES[Number(d.periodo.de.slice(5, 7)) - 1][0].toUpperCase() + MES[Number(d.periodo.de.slice(5, 7)) - 1].slice(1) : ROTULO_PERIODO[periodo];
        const sobe = d.comparacao.filter((c) => num(c.variacao) > 0).sort((a, b) => num(b.variacao) - num(a.variacao));
        const cai = d.comparacao.filter((c) => num(c.variacao) < 0).sort((a, b) => num(a.variacao) - num(b.variacao));
        const linha = (c: Destino["comparacao"][number], cor: string) => (
          <div key={c.categoria} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto auto", gap: 10, padding: "8px 0", borderTop: "1px solid var(--line2)", alignItems: "baseline" }}>
            <span><span style={{ fontWeight: 600 }}>{c.categoria}</span> <span style={{ fontSize: 12, color: "var(--ink2)" }}><Valor valor={c.anterior} /> → <Valor valor={c.atual} /></span></span>
            <span style={{ fontVariantNumeric: "tabular-nums", fontSize: 13 }}><Valor valor={c.variacao} /></span>
            <span style={{ font: "600 12px var(--mono)", color: cor, minWidth: 58, textAlign: "right" }}>{num(c.anterior) ? `${num(c.variacao) > 0 ? "+" : ""}${Math.round((num(c.variacao) / num(c.anterior)) * 100)}%` : "novo"}</span>
          </div>
        );
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 4, maxWidth: 640 }}>
                <span style={{ font: "600 10.5px var(--font-body)", letterSpacing: ".08em", textTransform: "uppercase", color: "var(--ink2)" }}>{rotulo} · saiu <Valor valor={d.total} /></span>
                <p style={{ margin: 0, font: "600 22px/1.2 var(--font-heading)", textWrap: "pretty" }}>
                  {pct(pessoal, total)} do que saiu é consumo seu (<Valor valor={pessoal} />). O resto, <Valor valor={total - pessoal} />, é das empresas e volta como reembolso.
                </p>
              </div>
              <div role="group" aria-label="Visualização" className="seg">
                {(Object.keys(ROTULO) as Vista[]).map((v) => (
                  <button key={v} className="seg-opt" aria-pressed={vista === v} onClick={() => { setVista(v); setEscolhido(null); }}
                    style={{ border: 0, borderLeft: "1px solid var(--color-divider)", marginLeft: -1, background: vista === v ? "var(--color-accent)" : "transparent", color: vista === v ? "var(--color-bg)" : "var(--color-text)" }}>{ROTULO[v]}</button>
                ))}
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,160px),1fr))", gap: 10 }}>
              {destinos.map((x) => (
                <button key={x.nome} onClick={() => setEscolhido({ nome: x.nome, tipo: "destino" })} style={{ display: "flex", flexDirection: "column", gap: 3, padding: "10px 12px", border: "1px solid var(--color-divider)", borderTop: `3px solid ${corDestino(x.nome)}`, background: "transparent", color: "inherit", textAlign: "left", cursor: "pointer", font: "inherit" }}>
                  <span style={{ fontSize: 12.5, fontWeight: 600 }}>{x.nome}</span>
                  <span style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
                    <span style={{ font: "600 19px/1.1 var(--font-heading)", fontVariantNumeric: "tabular-nums" }}><Valor valor={x.valor} /></span>
                    <span style={{ font: "500 12px var(--mono)", color: "var(--ink2)" }}>{pct(x.valor, total)}</span>
                  </span>
                </button>
              ))}
            </div>
            <Bloco>
              {(vista === "fornecedor" || vista === "categoria") && agrupado.env && <>
                <span style={{ fontSize: 12, color: "var(--ink2)" }}>{vista === "categoria" ? "para onde foi o dinheiro, por categoria" : "maiores fornecedores do período"} · toque para ver os lançamentos</span>
                <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column" }}>
                  {agrupado.env.dados.itens.map((r, i) => (
                    <li key={r.nome} onClick={() => setEscolhido({ nome: r.nome, tipo: vista === "categoria" ? "categoria" : "texto" })} style={{ display: "grid", gridTemplateColumns: "22px minmax(0,1fr) auto", gap: "2px 10px", padding: "9px 0", borderTop: "1px solid var(--line2)", alignItems: "center", cursor: "pointer" }}>
                      <span style={{ font: "500 11px var(--mono)", color: "var(--ink2)" }}>{i + 1}</span>
                      <span style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
                        <span style={{ fontWeight: 600 }}>{r.nome}</span>
                        <span style={{ height: 4, background: "var(--line2)" }}><span style={{ display: "block", height: "100%", width: `${Math.min(100, r.pct)}%`, background: "var(--color-accent)" }} /></span>
                      </span>
                      <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 600, whiteSpace: "nowrap" }}><Valor valor={r.valor} /></span>
                    </li>
                  ))}
                </ol>
              </>}
              {(vista === "pessoa" || vista === "gastador") && agrupado.env && <>
                <span style={{ fontSize: 12, color: "var(--ink2)" }}>{vista === "gastador" ? "quem passou o cartão (o portador); nos cartões compartilhados é você quem indica" : "categoria diz o quê, \"para quem\" diz de quem é o gasto"} · toque numa pessoa para ver os lançamentos</span>
                {agrupado.env.dados.itens.map((p) => (
                  <button key={p.nome} onClick={() => setEscolhido({ nome: p.nome, tipo: vista })} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: "4px 12px", padding: "10px 4px", border: 0, borderTop: "1px solid var(--line2)", background: "transparent", color: "inherit", textAlign: "left", cursor: "pointer", font: "inherit" }}>
                    <span style={{ display: "flex", flexDirection: "column", gap: 5, minWidth: 0 }}>
                      <span style={{ font: "600 17px/1.1 var(--font-heading)" }}>{p.nome}</span>
                      <span style={{ height: 6, background: "var(--line2)" }}><span style={{ display: "block", height: "100%", width: `${Math.min(100, p.pct)}%`, background: "var(--color-accent)" }} /></span>
                    </span>
                    <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
                      <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700 }}><Valor valor={p.valor} /></span>
                      <span style={{ font: "500 11.5px var(--mono)", color: "var(--ink2)" }}>{p.pct}%</span>
                    </span>
                  </button>
                ))}
              </>}
            </Bloco>
            {escolhido && lanc.env && (
              <Bloco>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                  <div><h3 style={{ margin: 0, fontSize: 20 }}>{escolhido.nome}</h3><span style={{ fontSize: 12.5, color: "var(--ink2)" }}>{lanc.env.dados.itens.length} lançamentos · maiores primeiro</span></div>
                  <button className="btn btn-secondary" onClick={() => setEscolhido(null)}>Limpar seleção</button>
                </div>
                {[...lanc.env.dados.itens].sort((a, b) => Math.abs(num(b.valor)) - Math.abs(num(a.valor))).map((i) => (
                  <div key={i.id} style={{ display: "grid", gridTemplateColumns: "48px minmax(0,1fr) auto", gap: "4px 12px", padding: "9px 0", borderTop: "1px solid var(--line2)", alignItems: "baseline" }}>
                    <span style={{ font: "500 12px var(--mono)", color: "var(--ink2)" }}>{dataCurta(i.data)}</span>
                    <span style={{ minWidth: 0 }}><span style={{ fontWeight: 600 }}>{i.estabelecimento}</span> <span style={{ fontSize: 12, color: "var(--ink2)" }}>· {i.categoria.nome ?? "sem categoria"} · {i.conta}</span></span>
                    <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 600, whiteSpace: "nowrap" }}><Valor valor={i.valor} /></span>
                  </div>
                ))}
              </Bloco>
            )}
            <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,340px),1fr))", gap: 22 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}><h3 style={{ margin: 0, fontSize: 19 }}>Subiu em relação ao período anterior</h3>{sobe.map((c) => linha(c, "var(--danger)"))}</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}><h3 style={{ margin: 0, fontSize: 19 }}>Caiu</h3>{cai.map((c) => linha(c, "var(--ok)"))}</div>
            </section>
          </div>
        );
      }}
    </Painel>
  );
}
