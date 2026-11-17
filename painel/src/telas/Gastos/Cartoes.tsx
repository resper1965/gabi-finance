import { useState } from "react";
import { Bloco } from "../../componentes/Bloco";
import { Etiqueta, type TipoEtiqueta } from "../../componentes/Etiqueta";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { useCelular } from "../../componentes/Shell";
import { api } from "../../lib/api";
import { dataCurta, mesCurto, num } from "../../lib/formato";
import { useToast } from "../../lib/toast";
import { useApi } from "../../lib/useApi";

interface Cartao {
  id: number; apelido: string; limite: string | null;
  fatura_aberta: { id: string; vencimento: string; total: string; status: string; percentual_limite: number | null } | null;
  serie_12m: { mes: string; total: string }[]; por_categoria: { categoria: string; valor: string }[];
}
interface Campo { id: number | string | null; nome: string | null; origem: string | null }
interface Lanc { id: number; data: string; estabelecimento: string; valor: string; conta: string; parcela: number | null; parcelas: number | null; categoria: Campo; para_quem: Campo; empresa: Campo; gastador?: Campo; portadores?: string[] }
interface Item { id: number | string; nome: string }

const COR = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)"];
const ORIGEM: Record<string, [TipoEtiqueta, string]> = { banco: ["banco", "banco"], regra: ["regra", "regra"], gabi: ["conferir", "Gabi sugere"], voce: ["ok", "você"], fonte: ["banco", "fonte"] };
const selecao = { height: 32, border: "1px solid var(--line3)", background: "var(--raised)", color: "var(--color-text)", font: "600 12.5px var(--font-body)", padding: "0 4px" } as const;

function Origem({ campo }: { campo: Campo }) {
  const o = campo.origem && ORIGEM[campo.origem];
  return o ? <Etiqueta tipo={o[0]} texto={o[1]} /> : null;
}

export function Cartoes() {
  const celular = useCelular();
  const avisar = useToast();
  const leitura = useApi<{ itens: Cartao[] }>("/api/v1/cartoes");
  const pessoas = useApi<{ itens: Item[] }>("/api/v1/cadastros/pessoas").env?.dados.itens ?? [];
  const categorias = useApi<{ itens: Item[] }>("/api/v1/cadastros/categorias").env?.dados.itens ?? [];
  const empresas = useApi<{ itens: Item[] }>("/api/v1/cadastros/empresas").env?.dados.itens ?? [];
  const [sel, setSel] = useState<number | "todos">("todos");
  const [q, setQ] = useState("");
  const [fCat, setFCat] = useState(""), [fEmp, setFEmp] = useState(""), [fBen, setFBen] = useState(""), [fTipo, setFTipo] = useState("");
  const [marcados, setMarcados] = useState<number[]>([]);
  const [bCat, setBCat] = useState(""), [bBen, setBBen] = useState(""), [bEmp, setBEmp] = useState(""), [bGasto, setBGasto] = useState(""), [bQuem, setBQuem] = useState(""), [bRegra, setBRegra] = useState(false);
  const filtros = `&limite=200${q ? `&texto=${encodeURIComponent(q)}` : ""}${fCat ? `&categoria=${fCat}` : ""}${fEmp ? `&empresa=${fEmp}` : ""}${fBen ? `&para_quem=${fBen}` : ""}`;
  const assinaturas = useApi<{ itens: { nome: string }[] }>("/api/v1/assinaturas").env?.dados.itens ?? [];
  const nomesAssinatura = new Set(assinaturas.map((a) => a.nome.toLowerCase()));
  const lanc = useApi<{ itens: Lanc[]; total: number }>(leitura.env ? `/api/v1/lancamentos?x=1${filtros}` : null);

  return (
    <Painel leitura={leitura} arquivo="faturas dos cartões">
      {(d) => {
        if (d.itens.length === 0) return <Bloco><p style={{ margin: 0 }}>Nenhum cartão liberado. Escolha em Cadastros quais contas entram.</p></Bloco>;
        const cartoes = sel === "todos" ? d.itens : d.itens.filter((c) => c.id === sel);
        const nomes = new Set(cartoes.map((c) => c.apelido));
        const linhas = (lanc.env?.dados.itens ?? []).filter((l) => nomes.has(l.conta)).filter((l) => fTipo !== "parcelado" || (l.parcelas ?? 0) > 1)
          .filter((l) => fTipo !== "assinatura" || nomesAssinatura.has(l.estabelecimento.toLowerCase()));
        const meses = d.itens[0].serie_12m.map((m) => m.mes);
        const topo = Math.max(1, ...meses.map((_, i) => cartoes.reduce((s, c) => s + num(c.serie_12m[i]?.total), 0)));
        const cats = new Map<string, number>();
        cartoes.forEach((c) => c.por_categoria.forEach((p) => cats.set(p.categoria, (cats.get(p.categoria) ?? 0) + num(p.valor))));
        const totCat = [...cats.values()].reduce((a, b) => a + b, 0);
        const lista = [...cats.entries()].sort((a, b) => b[1] - a[1]);
        const mudar = async (ids: number[], mudancas: Record<string, number | string | boolean | null>, regra: boolean, texto: string) => {
          try { await api.post("/api/v1/lancamentos/lote", { ids, mudancas, criar_regra: regra }); avisar(texto); setMarcados([]); setBQuem(""); lanc.recarregar(); leitura.recarregar(); }
          catch (e) { avisar((e as Error).message); }
        };
        const nomePessoa = (pid: string) => pessoas.find((p) => String(p.id) === pid)?.nome ?? pid;
        // no lote, só quem é portador de TODOS os marcados (a API recusa quem não for)
        const portadoresMarcados = linhas.filter((l) => marcados.includes(l.id)).map((l) => l.portadores ?? [])
          .reduce<string[] | null>((acc, ps) => (acc === null ? ps : acc.filter((x) => ps.includes(x))), null) ?? [];
        const quemValido = bQuem !== "" && portadoresMarcados.includes(bQuem);  // escolha que não vale para os marcados agora não vai
        const quemGastou = (l: Lanc) => l.gastador?.nome ?? ((l.portadores?.length ?? 0) >= 2 ? <span style={{ color: "var(--warn)", fontWeight: 600 }}>a indicar</span> : "—");
        const aplicar = () => {
          const m: Record<string, number | string | boolean | null> = {};
          if (bCat) m.categoria_id = Number(bCat);
          if (bBen) m.beneficiario_id = Number(bBen);
          if (bEmp) m.empresa_id = bEmp === "none" ? null : bEmp;  // id da empresa é texto ("ness"); Number() virava NaN → null e limpava
          if (bGasto) m.gasto = bGasto === "auto" ? null : bGasto === "sim";
          if (quemValido) m.gastador_id = bQuem;
          return mudar(marcados, m, bRegra, `${marcados.length} lançamentos atualizados por você${bRegra ? " e regra criada" : ""}.`);
        };
        const beneficiario = (l: Lanc) => (
          <select aria-label={`Para quem: ${l.estabelecimento}`} value={String(l.para_quem.id ?? "")} onChange={(e) => mudar([l.id], { beneficiario_id: Number(e.target.value) }, false, `Anotado: ${l.estabelecimento}, só este lançamento.`)}
            style={{ ...selecao, maxWidth: celular ? undefined : 150, height: celular ? 44 : 28, flex: celular ? 1 : undefined, borderStyle: l.para_quem.origem === "gabi" ? "dashed" : "solid" }}>
            <option value="">sem dono</option>{pessoas.map((p) => <option key={p.id} value={String(p.id)}>{celular ? "Para " : ""}{p.nome}</option>)}
          </select>
        );
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            <div style={{ overflowX: "auto" }}>
              <div role="group" aria-label="Cartão" className="seg">
                {([["todos", "Todos os cartões"], ...d.itens.map((c) => [c.id, c.apelido] as const)] as const).map(([id, r]) => (
                  <button key={id} className="seg-opt" aria-pressed={sel === id} onClick={() => setSel(id as number | "todos")}
                    style={{ whiteSpace: "nowrap", border: 0, borderLeft: "1px solid var(--color-divider)", marginLeft: -1, background: sel === id ? "var(--color-accent)" : "transparent", color: sel === id ? "var(--color-bg)" : "var(--color-text)" }}>{r}</button>
                ))}
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,220px),1fr))", gap: 14 }}>
              {cartoes.filter((c) => c.fatura_aberta).map((c) => {
                const f = c.fatura_aberta!;
                return (
                  <div key={c.id} className="blueprint" style={{ padding: 14, display: "flex", flexDirection: "column", gap: 6 }}>
                    <i className="corner tl" /><i className="corner tr" /><i className="corner bl" /><i className="corner br" />
                    <span style={{ font: "600 10.5px var(--font-body)", letterSpacing: ".08em", textTransform: "uppercase", color: "var(--ink2)" }}>Fatura aberta · {c.apelido}</span>
                    <span style={{ font: "600 26px/1.05 var(--font-heading)", fontVariantNumeric: "tabular-nums" }}><Valor valor={f.total} /></span>
                    <span style={{ fontSize: 12.5, color: "var(--ink2)" }}>vence <strong style={{ color: "var(--color-text)" }}>{dataCurta(f.vencimento)}</strong></span>
                    {f.percentual_limite !== null && <>
                      <span style={{ height: 4, background: "var(--line2)" }}><span style={{ display: "block", height: "100%", width: `${Math.min(100, f.percentual_limite)}%`, background: "var(--color-accent)" }} /></span>
                      <span style={{ fontSize: 12, color: "var(--ink2)" }}>{f.percentual_limite.toLocaleString("pt-BR")}% do limite{c.limite ? <> de <Valor valor={c.limite} /></> : null}</span></>}
                  </div>
                );
              })}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,420px),1fr))", gap: 22, alignItems: "start" }}>
              <Bloco titulo="Últimos 12 meses">
                <svg role="img" aria-label="Barras mensais por cartão" viewBox="0 0 640 170" style={{ width: "100%", height: "auto", display: "block" }}>
                  <line x1={0} x2={640} y1={140} y2={140} style={{ stroke: "var(--color-text)" }} />
                  {meses.map((m, i) => {
                    let y = 140;
                    return (
                      <g key={m}>
                        {cartoes.map((c, k) => {
                          const h = (num(c.serie_12m[i]?.total) / topo) * 120; y -= h;
                          return <rect key={c.id} x={14 + i * 52} y={y} width={34} height={h} style={{ fill: COR[k % COR.length], fillOpacity: i === meses.length - 1 ? 0.4 : 1, stroke: i === meses.length - 1 ? "var(--ink2)" : "none", strokeDasharray: "3 2" }} />;
                        })}
                        <text x={31 + i * 52} y={158} style={{ fill: "var(--ink2)", font: "500 10.5px var(--mono)", textAnchor: "middle" }}>{mesCurto(m)}</text>
                      </g>
                    );
                  })}
                </svg>
                <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 12, color: "var(--ink2)" }}>
                  {cartoes.map((c, k) => <span key={c.id} style={{ display: "flex", alignItems: "center", gap: 5 }}><span style={{ width: 10, height: 10, background: COR[k % COR.length] }} />{c.apelido}</span>)}
                  <span style={{ display: "flex", alignItems: "center", gap: 5 }}><span style={{ width: 10, height: 10, border: "1px dashed var(--ink2)" }} />mês atual, fatura ainda aberta</span>
                </div>
              </Bloco>
              <Bloco titulo="Fatura aberta por categoria" nota={<Valor valor={totCat} />} style={{ gap: 8 }}>
                {lista.map(([nome, v], i) => (
                  <div key={nome} style={{ display: "grid", gridTemplateColumns: "minmax(0,130px) minmax(0,1fr) auto", gap: 10, alignItems: "center", padding: "4px 0" }}>
                    <span style={{ fontSize: 13 }}>{nome}</span>
                    <span style={{ height: 10, background: "var(--line2)" }}><span style={{ display: "block", height: "100%", width: `${totCat ? (v / totCat) * 100 : 0}%`, background: COR[Math.min(i, 4)] }} /></span>
                    <span style={{ fontVariantNumeric: "tabular-nums", fontSize: 13, whiteSpace: "nowrap" }}><Valor valor={v} /> <span style={{ color: "var(--ink2)", font: "500 11px var(--mono)" }}>{totCat ? Math.round((v / totCat) * 100) : 0}%</span></span>
                  </div>
                ))}
              </Bloco>
            </div>
            <section style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", alignItems: "baseline" }}>
                <h3 style={{ margin: 0, fontSize: 20 }}>Lançamentos</h3>
                <span style={{ fontSize: 12.5, color: "var(--ink2)" }}>{linhas.length} lançamentos · categoria diz o quê, "para quem" diz de quem é o gasto · borda tracejada = sugestão da Gabi, ainda não confirmada</span>
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <input aria-label="Buscar estabelecimento" placeholder="Buscar estabelecimento" value={q} onChange={(e) => setQ(e.target.value)} className="input" style={{ flex: "1 1 220px", height: 36 }} />
                <select className="input" aria-label="Categoria" value={fCat} onChange={(e) => setFCat(e.target.value)} style={{ width: "auto" }}><option value="">Todas as categorias</option>{categorias.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}</select>
                <select className="input" aria-label="Empresa" value={fEmp} onChange={(e) => setFEmp(e.target.value)} style={{ width: "auto" }}><option value="">Todas as empresas</option>{empresas.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}</select>
                <select className="input" aria-label="Para quem" value={fBen} onChange={(e) => setFBen(e.target.value)} style={{ width: "auto" }}><option value="">Para qualquer pessoa</option>{pessoas.map((c) => <option key={c.id} value={c.id}>Para {c.nome}</option>)}</select>
                <select className="input" aria-label="Tipo" value={fTipo} onChange={(e) => setFTipo(e.target.value)} style={{ width: "auto" }}><option value="">À vista e parcelado</option><option value="parcelado">Só parcelado</option><option value="assinatura">Só assinatura</option></select>
              </div>
              <div role="group" aria-label="Edição em lote" style={{ position: "sticky", top: 0, zIndex: 2, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", padding: "8px 12px", border: `1px solid ${marcados.length ? "var(--color-accent)" : "var(--color-divider)"}`, background: "var(--color-bg)" }}>
                <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", minHeight: 32, fontSize: 13 }}>
                  <input type="checkbox" checked={linhas.length > 0 && marcados.length === linhas.length} onChange={(e) => setMarcados(e.target.checked ? linhas.map((l) => l.id) : [])} style={{ width: 18, height: 18 }} />Todos
                </label>
                {marcados.length === 0 && <span style={{ fontSize: 12.5, color: "var(--ink2)" }}>Marque linhas para mudar categoria, "para quem" ou empresa de uma vez.</span>}
                {marcados.length > 0 && <>
                  <strong style={{ fontSize: 13 }}>{marcados.length} selecionados</strong>
                  <select aria-label="Nova categoria" value={bCat} onChange={(e) => setBCat(e.target.value)} style={selecao}><option value="">Categoria: manter</option>{categorias.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}</select>
                  <select aria-label="Novo para quem" value={bBen} onChange={(e) => setBBen(e.target.value)} style={selecao}><option value="">Para quem: manter</option>{pessoas.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}</select>
                  <select aria-label="Nova empresa" value={bEmp} onChange={(e) => setBEmp(e.target.value)} style={selecao}><option value="">Empresa: manter</option><option value="none">Nenhuma · pessoal</option>{empresas.map((c) => <option key={c.id} value={c.id}>Reembolso {c.nome}</option>)}</select>
                  <select aria-label="É gasto?" value={bGasto} onChange={(e) => setBGasto(e.target.value)} style={selecao}><option value="">Gasto: manter</option><option value="sim">É gasto</option><option value="nao">Não é gasto</option><option value="auto">A Gabi decide</option></select>
                  {portadoresMarcados.length > 1 && <select aria-label="Quem gastou" value={bQuem} onChange={(e) => setBQuem(e.target.value)} style={selecao}><option value="">Quem gastou: manter</option>{portadoresMarcados.map((pid) => <option key={pid} value={pid}>{nomePessoa(pid)}</option>)}</select>}
                  <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, cursor: "pointer" }}><input type="checkbox" checked={bRegra} onChange={(e) => setBRegra(e.target.checked)} style={{ width: 16, height: 16 }} />criar regra para os próximos</label>
                  <span style={{ flex: 1 }} />
                  <button className="btn btn-ghost" onClick={() => setMarcados([])}>Limpar</button>
                  <button className="btn btn-primary" disabled={!bCat && !bBen && !bEmp && !bGasto && !quemValido} onClick={aplicar}>Aplicar</button>
                </>}
              </div>
              {linhas.length === 0 && <div style={{ border: "1px dashed var(--line3)", padding: 20 }}>Nenhum lançamento com esses filtros.</div>}
              {!celular && linhas.length > 0 && (
                <div style={{ overflowX: "auto", maxWidth: "100%" }}>
                  <table className="table" style={{ fontSize: 13.5 }}>
                    <thead><tr><th style={{ width: 32 }} /><th>Data</th><th>Estabelecimento</th><th>Cartão</th><th>Categoria</th><th>Quem gastou</th><th>Para quem</th><th>Tipo</th><th style={{ textAlign: "right" }}>Valor</th></tr></thead>
                    <tbody>
                      {linhas.map((l) => (
                        <tr key={l.id} data-lancamento={l.id} style={{ background: marcados.includes(l.id) ? "var(--sel)" : undefined }}>
                          <td><input type="checkbox" aria-label={`Selecionar ${l.estabelecimento}`} checked={marcados.includes(l.id)} onChange={(e) => setMarcados(e.target.checked ? [...marcados, l.id] : marcados.filter((x) => x !== l.id))} style={{ width: 17, height: 17 }} /></td>
                          <td style={{ font: "500 12.5px var(--mono)", color: "var(--ink2)" }}>{dataCurta(l.data)}</td>
                          <td style={{ fontWeight: 600 }}>{l.estabelecimento}</td>
                          <td>{l.conta}</td>
                          <td><span style={{ display: "inline-flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>{l.categoria.nome ?? "sem categoria"}<Origem campo={l.categoria} /></span></td>
                          <td>{quemGastou(l)}</td>
                          <td><span style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-start" }}>{beneficiario(l)}<Origem campo={l.para_quem} /></span></td>
                          <td>{l.parcelas && l.parcelas > 1 ? `${l.parcela}/${l.parcelas}` : "à vista"}</td>
                          <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: 600 }}><Valor valor={l.valor} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {celular && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {linhas.map((l) => (
                    <div key={l.id} data-lancamento={l.id} style={{ border: "1px solid var(--color-divider)", padding: "10px 12px", display: "flex", flexDirection: "column", gap: 5 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                        <label style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 600, cursor: "pointer" }}>
                          <input type="checkbox" checked={marcados.includes(l.id)} onChange={(e) => setMarcados(e.target.checked ? [...marcados, l.id] : marcados.filter((x) => x !== l.id))} style={{ width: 20, height: 20 }} />{l.estabelecimento}
                        </label>
                        <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700, whiteSpace: "nowrap" }}><Valor valor={l.valor} /></span>
                      </div>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", fontSize: 12, color: "var(--ink2)" }}>
                        <span style={{ fontFamily: "var(--mono)" }}>{dataCurta(l.data)}</span><span>· {l.conta} · {l.categoria.nome ?? "sem categoria"}</span><Origem campo={l.categoria} />
                      </div>
                      <div style={{ fontSize: 12, color: "var(--ink2)" }}>Quem gastou: {quemGastou(l)}</div>
                      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>{beneficiario(l)}<Origem campo={l.para_quem} /></div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        );
      }}
    </Painel>
  );
}
