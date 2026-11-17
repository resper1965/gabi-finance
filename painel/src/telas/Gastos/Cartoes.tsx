import { useState } from "react";
import { Search } from "lucide-react";
import { Bloco } from "../../componentes/Bloco";
import { Evidencia } from "../../componentes/Evidencia";
import { Vazio } from "../../componentes/Estados";
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

const COR = ["var(--serie-1)", "var(--serie-3)", "var(--serie-2)", "var(--serie-4)", "var(--serie-5)"];
const ORIGEM: Record<string, [TipoEtiqueta, string]> = { banco: ["banco", "banco"], regra: ["regra", "regra"], gabi: ["conferir", "Gabi sugere"], voce: ["ajuste", "você"], fonte: ["banco", "fonte"] };

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
        if (d.itens.length === 0) return <Vazio frase="Nenhum cartão liberado. Escolha em Cadastros quais contas entram no caixa único." />;
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
        const quemGastou = (l: Lanc) => l.gastador?.nome ?? ((l.portadores?.length ?? 0) >= 2 ? <Etiqueta tipo="conferir" texto="a indicar" /> : <span className="suave">—</span>);
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
            className="campo-sm" style={{ maxWidth: celular ? undefined : 160, minHeight: celular ? 44 : 28, flex: celular ? 1 : undefined, borderStyle: l.para_quem.origem === "gabi" ? "dashed" : "solid", borderColor: l.para_quem.origem === "gabi" ? "var(--ambar-borda)" : undefined }}>
            <option value="">sem dono</option>{pessoas.map((p) => <option key={p.id} value={String(p.id)}>{celular ? "Para " : ""}{p.nome}</option>)}
          </select>
        );
        return (
          <div className="pilha" style={{ gap: 32 }}>
            <div className="rolagem-x">
              <div role="group" aria-label="Cartão" className="seg">
                {([["todos", "Todos os cartões"], ...d.itens.map((c) => [c.id, c.apelido] as const)] as const).map(([id, r]) => (
                  <button key={id} className="seg-opt" aria-pressed={sel === id} onClick={() => setSel(id as number | "todos")}>{r}</button>
                ))}
              </div>
            </div>
            <Bloco titulo="Faturas abertas" nota="o total de cada fatura ainda não fechada">
              <ul className="pauta">
                {cartoes.filter((c) => c.fatura_aberta).map((c, k) => {
                  const f = c.fatura_aberta!;
                  return (
                    <li key={c.id} className="fatura">
                      <span className="pilha-curta" style={{ gap: 2 }}><span className="linha-titulo">{c.apelido}</span><span className="miudo">vence <span className="mono" style={{ color: "var(--tinta)" }}>{dataCurta(f.vencimento)}</span></span></span>
                      {f.percentual_limite !== null ? (
                        <span className="pilha-curta" style={{ gap: 4 }}>
                          <span className="barra-fina" style={{ height: 6 }}><span style={{ width: `${Math.min(100, f.percentual_limite)}%`, background: f.percentual_limite >= 80 ? "var(--carimbo-vermelho)" : "var(--tinta-2)" }} /></span>
                          <span className="miudo">{f.percentual_limite.toLocaleString("pt-BR")}% do limite{c.limite ? <> de <Valor valor={c.limite} /></> : null}</span>
                        </span>) : <span className="miudo">sem limite informado</span>}
                      <span className="linha-valor" style={{ fontSize: "var(--t2)" }}>
                        <Evidencia codigo={`E-${String(k + 1).padStart(2, "0")}`} rotulo={`Fatura aberta · ${c.apelido}`} fonte="open-finance" base={`fatura ${f.status}, vence em ${dataCurta(f.vencimento)}`}><Valor valor={f.total} /></Evidencia>
                      </span>
                    </li>
                  );
                })}
              </ul>
              {cartoes.every((c) => !c.fatura_aberta) && <Vazio frase="Nenhuma fatura aberta nos cartões escolhidos." />}
            </Bloco>
            <div className="grade-2">
              <Bloco titulo="Últimos 12 meses" nota="soma das faturas por mês">
                <svg role="img" aria-label="Barras mensais por cartão" viewBox="0 0 640 170" className="grafico" style={{ width: "100%", height: "auto" }}>
                  <line x1={0} x2={640} y1={140} y2={140} style={{ stroke: "var(--tinta)" }} />
                  {meses.map((m, i) => {
                    let y = 140;
                    return (
                      <g key={m}>
                        {cartoes.map((c, k) => {
                          const h = (num(c.serie_12m[i]?.total) / topo) * 120; y -= h;
                          return <rect key={c.id} x={14 + i * 52} y={y} width={34} height={h} style={{ fill: COR[k % COR.length], fillOpacity: i === meses.length - 1 ? 0.4 : 1, stroke: i === meses.length - 1 ? "var(--tinta-3)" : "none", strokeDasharray: "3 2" }} />;
                        })}
                        <text x={31 + i * 52} y={158} style={{ textAnchor: "middle" }}>{mesCurto(m)}</text>
                      </g>
                    );
                  })}
                </svg>
                <div className="legenda">
                  {cartoes.map((c, k) => <span key={c.id}><span className="amostra-cor" style={{ background: COR[k % COR.length] }} />{c.apelido}</span>)}
                  <span><span className="amostra-cor" style={{ border: "1px dashed var(--tinta-3)" }} />mês atual, fatura ainda aberta</span>
                </div>
              </Bloco>
              <Bloco titulo="Fatura aberta por categoria" nota={<>total <Valor valor={totCat} /></>}>
                <ul className="pauta">
                  {lista.map(([nome, v], i) => (
                    <li key={nome} className="categoria-linha">
                      <span>{nome}</span>
                      <span className="barra-fina" style={{ height: 8 }}><span style={{ width: `${totCat ? (v / totCat) * 100 : 0}%`, background: COR[Math.min(i, 4)] }} /></span>
                      <span className="num" style={{ whiteSpace: "nowrap", textAlign: "right" }}><Valor valor={v} /> <span className="mono suave">{totCat ? Math.round((v / totCat) * 100) : 0}%</span></span>
                    </li>
                  ))}
                </ul>
              </Bloco>
            </div>
            <Bloco titulo="Lançamentos" nota={<>{linhas.length} lançamentos · categoria diz o quê, "para quem" diz de quem é o gasto · borda tracejada âmbar = sugestão da Gabi, ainda não confirmada</>}>
              <div className="fila">
                <span className="busca"><Search size={15} strokeWidth={1.8} aria-hidden="true" /><input aria-label="Buscar estabelecimento" placeholder="Buscar estabelecimento" value={q} onChange={(e) => setQ(e.target.value)} /></span>
                <select className="input" aria-label="Categoria" value={fCat} onChange={(e) => setFCat(e.target.value)} style={{ width: "auto" }}><option value="">Todas as categorias</option>{categorias.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}</select>
                <select className="input" aria-label="Empresa" value={fEmp} onChange={(e) => setFEmp(e.target.value)} style={{ width: "auto" }}><option value="">Todas as empresas</option>{empresas.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}</select>
                <select className="input" aria-label="Para quem" value={fBen} onChange={(e) => setFBen(e.target.value)} style={{ width: "auto" }}><option value="">Para qualquer pessoa</option>{pessoas.map((c) => <option key={c.id} value={c.id}>Para {c.nome}</option>)}</select>
                <select className="input" aria-label="Tipo" value={fTipo} onChange={(e) => setFTipo(e.target.value)} style={{ width: "auto" }}><option value="">À vista e parcelado</option><option value="parcelado">Só parcelado</option><option value="assinatura">Só assinatura</option></select>
              </div>
              <div role="group" aria-label="Edição em lote" className="lote" data-ativo={marcados.length > 0}>
                <label className="opcao">
                  <input type="checkbox" checked={linhas.length > 0 && marcados.length === linhas.length} onChange={(e) => setMarcados(e.target.checked ? linhas.map((l) => l.id) : [])} />Todos
                </label>
                {marcados.length === 0 && <span className="miudo">Marque linhas para mudar categoria, "para quem" ou empresa de uma vez.</span>}
                {marcados.length > 0 && <>
                  <strong className="num">{marcados.length} selecionados</strong>
                  <select aria-label="Nova categoria" value={bCat} onChange={(e) => setBCat(e.target.value)} className="campo-sm"><option value="">Categoria: manter</option>{categorias.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}</select>
                  <select aria-label="Novo para quem" value={bBen} onChange={(e) => setBBen(e.target.value)} className="campo-sm"><option value="">Para quem: manter</option>{pessoas.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}</select>
                  <select aria-label="Nova empresa" value={bEmp} onChange={(e) => setBEmp(e.target.value)} className="campo-sm"><option value="">Empresa: manter</option><option value="none">Nenhuma · pessoal</option>{empresas.map((c) => <option key={c.id} value={c.id}>Reembolso {c.nome}</option>)}</select>
                  <select aria-label="É gasto?" value={bGasto} onChange={(e) => setBGasto(e.target.value)} className="campo-sm"><option value="">Gasto: manter</option><option value="sim">É gasto</option><option value="nao">Não é gasto</option><option value="auto">A Gabi decide</option></select>
                  {portadoresMarcados.length > 1 && <select aria-label="Quem gastou" value={bQuem} onChange={(e) => setBQuem(e.target.value)} className="campo-sm"><option value="">Quem gastou: manter</option>{portadoresMarcados.map((pid) => <option key={pid} value={pid}>{nomePessoa(pid)}</option>)}</select>}
                  <label className="opcao miudo"><input type="checkbox" checked={bRegra} onChange={(e) => setBRegra(e.target.checked)} />criar regra para os próximos</label>
                  <span style={{ flex: 1 }} />
                  <button className="btn btn-ghost btn-sm" onClick={() => setMarcados([])}>Limpar</button>
                  <button className="btn btn-primary btn-sm" disabled={!bCat && !bBen && !bEmp && !bGasto && !quemValido} onClick={aplicar}>Aplicar</button>
                </>}
              </div>
              {linhas.length === 0 && lanc.env && <Vazio frase="Nenhum lançamento com esses filtros. Limpe a busca ou troque o cartão." />}
              {!lanc.env && <div className="esqueleto"><span className="esqueleto-linha" /><span className="esqueleto-linha" style={{ width: "85%" }} /><span className="esqueleto-linha" style={{ width: "70%" }} /></div>}
              {!celular && linhas.length > 0 && (
                <div className="tabela-rolagem">
                  <table className="tabela">
                    <thead><tr><th style={{ width: 32 }}><span className="sr-only">Selecionar</span></th><th>Data</th><th>Estabelecimento</th><th>Cartão</th><th>Categoria</th><th>Quem gastou</th><th>Para quem</th><th>Tipo</th><th className="num">Valor</th></tr></thead>
                    <tbody>
                      {linhas.map((l) => (
                        <tr key={l.id} data-lancamento={l.id} data-marcado={marcados.includes(l.id)}>
                          <td><input type="checkbox" aria-label={`Selecionar ${l.estabelecimento}`} checked={marcados.includes(l.id)} onChange={(e) => setMarcados(e.target.checked ? [...marcados, l.id] : marcados.filter((x) => x !== l.id))} /></td>
                          <td className="mono suave">{dataCurta(l.data)}</td>
                          <td className="forte">{l.estabelecimento}</td>
                          <td>{l.conta}</td>
                          <td><span style={{ display: "inline-flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>{l.categoria.nome ?? "sem categoria"}<Origem campo={l.categoria} /></span></td>
                          <td>{quemGastou(l)}</td>
                          <td><span style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-start" }}>{beneficiario(l)}<Origem campo={l.para_quem} /></span></td>
                          <td>{l.parcelas && l.parcelas > 1 ? <span className="mono">{l.parcela}/{l.parcelas}</span> : <span className="suave">à vista</span>}</td>
                          <td className="num forte"><Valor valor={l.valor} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {celular && (
                <ul className="pauta">
                  {linhas.map((l) => (
                    <li key={l.id} data-lancamento={l.id} className="pilha-curta" data-marcado={marcados.includes(l.id)}>
                      <div className="fila-entre" style={{ flexWrap: "nowrap" }}>
                        <label className="opcao forte">
                          <input type="checkbox" checked={marcados.includes(l.id)} onChange={(e) => setMarcados(e.target.checked ? [...marcados, l.id] : marcados.filter((x) => x !== l.id))} style={{ width: 20, height: 20 }} />{l.estabelecimento}
                        </label>
                        <span className="linha-valor"><Valor valor={l.valor} /></span>
                      </div>
                      <div className="linha-meta"><span className="mono">{dataCurta(l.data)}</span><span>{l.conta} · {l.categoria.nome ?? "sem categoria"}</span><Origem campo={l.categoria} /></div>
                      <div className="linha-meta">Quem gastou: {quemGastou(l)}</div>
                      <div className="fila">{beneficiario(l)}<Origem campo={l.para_quem} /></div>
                    </li>
                  ))}
                </ul>
              )}
            </Bloco>
          </div>
        );
      }}
    </Painel>
  );
}
