import { useState } from "react";
import { Marca } from "../componentes/Shell";
import { Painel } from "../componentes/Painel";
import { api } from "../lib/api";
import { dataCurta } from "../lib/formato";
import { useToast } from "../lib/toast";
import { useApi } from "../lib/useApi";

interface Regra { id: number; padrao: string; acao: Record<string, number | string>; ativa: boolean; criado_em: string; casam: number }
interface Sug { id: number; tipo: string; payload: { padrao?: string; acao?: Record<string, number | string> }; motivo: string; impacto: { passado?: number; futuro_estimado?: number } | null }
interface Item { id: number | string; nome: string }

export function Regras() {
  const regras = useApi<{ itens: Regra[] }>("/api/v1/regras");
  const sugestoes = useApi<{ itens: Sug[] }>("/api/v1/sugestoes");
  const categorias = useApi<{ itens: Item[] }>("/api/v1/cadastros/categorias").env?.dados.itens ?? [];
  const pessoas = useApi<{ itens: Item[] }>("/api/v1/cadastros/pessoas").env?.dados.itens ?? [];
  const empresas = useApi<{ itens: Item[] }>("/api/v1/cadastros/empresas").env?.dados.itens ?? [];
  const avisar = useToast();
  const [busca, setBusca] = useState("");
  const [marcadas, setMarcadas] = useState<number[]>([]);
  const [edicoes, setEdicoes] = useState<Record<number, number>>({}); // sugestão -> categoria escolhida antes de aprovar
  const recarregar = () => { regras.recarregar(); sugestoes.recarregar(); };
  const alvo = (acao: Record<string, number | string> | undefined) => {
    if (!acao) return "?";
    if (acao.categoria_id !== undefined) return categorias.find((c) => c.id === acao.categoria_id)?.nome ?? `categoria ${acao.categoria_id}`;
    if (acao.para_quem_id !== undefined) return `Para ${pessoas.find((c) => c.id === acao.para_quem_id)?.nome ?? acao.para_quem_id}`;
    if (acao.empresa_id !== undefined) return `Reembolso ${empresas.find((c) => c.id === acao.empresa_id)?.nome ?? acao.empresa_id}`;
    return JSON.stringify(acao);
  };
  const alternar = async (r: Regra) => {
    try { await api.patch(`/api/v1/regras/${r.id}`, { ativa: !r.ativa }); avisar(`Regra ${r.ativa ? "desligada" : "ligada"} por você.`); recarregar(); }
    catch (e) { avisar((e as Error).message); }
  };
  const decidir = async (ids: number[], acao: "aprovar" | "rejeitar") => {
    try {
      for (const id of ids) {
        const s = (sugestoes.env?.dados.itens ?? []).find((x) => x.id === id);
        const nova = edicoes[id];
        const edicao = acao === "aprovar" && nova !== undefined && s ? { edicao: { acao: { ...s.payload.acao, categoria_id: nova } } } : undefined;
        await api.post(acao === "aprovar" ? `/api/v1/sugestoes/${id}/aprovar` : `/api/v1/sugestoes/${id}/rejeitar`, edicao);
      }
      avisar(acao === "aprovar" ? `${ids.length === 1 ? "Regra criada" : `${ids.length} regras criadas`} por você.` : "Sugestão rejeitada.");
      setMarcadas([]); recarregar();
    } catch (e) { avisar((e as Error).message); }
  };
  const sugs = (sugestoes.env?.dados.itens ?? []).filter((s) => s.tipo === "regra");
  return (
    <Painel leitura={regras} arquivo="regras de classificação">
      {(d) => {
        const ativas = d.itens.filter((r) => r.padrao.toLowerCase().includes(busca.toLowerCase()));
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            <div style={{ border: "1px solid var(--color-accent)", background: "var(--sel)", color: "var(--sel-ink)", padding: "12px 14px", display: "flex", gap: 10, alignItems: "flex-start" }}>
              <Marca />
              <span style={{ textWrap: "pretty" }}><strong>A Gabi só sugere.</strong> Nenhuma regra liga sozinha. Quando você aprova, ela passa a valer para os lançamentos passados e para os próximos, e você pode desligar quando quiser.</span>
            </div>
            <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                <h3 style={{ margin: 0, fontSize: 20 }}>Sugestões da Gabi · {sugs.length} pendentes</h3>
                {marcadas.length > 0 && (
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span style={{ fontSize: 13, color: "var(--ink2)" }}>{marcadas.length} selecionadas</span>
                    <button className="btn btn-secondary" onClick={() => decidir(marcadas, "rejeitar")}>Rejeitar</button>
                    <button className="btn btn-primary" onClick={() => decidir(marcadas, "aprovar")}>Aprovar e ligar</button>
                  </div>
                )}
              </div>
              {sugs.length === 0 && <div style={{ border: "1px dashed var(--line3)", padding: 18, color: "var(--ink2)" }}>Gabi: sem sugestões de regra por enquanto. Quando você classificar o mesmo estabelecimento algumas vezes, eu proponho aqui.</div>}
              {sugs.map((g) => (
                <div key={g.id} data-sugestao style={{ border: "1px solid var(--color-divider)", padding: "12px 14px", display: "grid", gridTemplateColumns: "auto minmax(0,1fr)", gap: "10px 12px" }}>
                  <input type="checkbox" aria-label={`Selecionar sugestão ${g.payload.padrao}`} checked={marcadas.includes(g.id)} onChange={(e) => setMarcadas(e.target.checked ? [...marcadas, g.id] : marcadas.filter((x) => x !== g.id))} style={{ width: 18, height: 18, marginTop: 3 }} />
                  <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                      <code style={{ font: "600 13px var(--mono)", padding: "2px 6px", background: "var(--color-surface)" }}>{g.payload.padrao}</code>
                      <span aria-hidden="true" style={{ color: "var(--ink2)" }}>→</span>
                      {g.payload.acao?.categoria_id !== undefined && categorias.length > 0
                        ? (
                          <select aria-label={`Categoria da sugestão ${g.payload.padrao}`} value={edicoes[g.id] ?? Number(g.payload.acao.categoria_id ?? 0)}
                            onChange={(e) => setEdicoes({ ...edicoes, [g.id]: Number(e.target.value) })}
                            style={{ height: 32, padding: "0 8px", border: "1px solid var(--color-divider)", background: "var(--color-surface)", color: "inherit", font: "600 14px var(--font-body)" }}>
                            {g.payload.acao.categoria_id == null && <option value={0}>escolher…</option>}
                            {categorias.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
                          </select>
                        )
                        : <span style={{ fontWeight: 600 }}>{alvo(g.payload.acao)}</span>}
                    </div>
                    <span style={{ fontSize: 13, color: "var(--ink2)", textWrap: "pretty" }}>{g.motivo}</span>
                    {g.impacto && <span style={{ fontSize: 13 }}>afeta <strong>{g.impacto.passado ?? 0} lançamentos passados</strong> e todos os próximos (~{g.impacto.futuro_estimado ?? 0} por mês)</span>}
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <button className="btn btn-primary" disabled={g.payload.acao?.categoria_id === null && !edicoes[g.id]} onClick={() => decidir([g.id], "aprovar")}>Aprovar e ligar</button>
                      <button className="btn btn-secondary" onClick={() => decidir([g.id], "rejeitar")}>Rejeitar</button>
                    </div>
                  </div>
                </div>
              ))}
            </section>
            <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                <h3 style={{ margin: 0, fontSize: 20 }}>Regras ativas · {d.itens.filter((r) => r.ativa).length}</h3>
                <label style={{ flex: "0 1 280px", display: "flex", alignItems: "center", gap: 6, height: 36, padding: "0 10px", border: "1px solid var(--color-divider)", background: "var(--color-surface)" }}>
                  <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar regra" aria-label="Buscar regra" style={{ flex: 1, minWidth: 0, border: 0, background: "transparent", outline: "none", fontSize: 14, color: "inherit" }} />
                </label>
              </div>
              <div style={{ display: "flex", flexDirection: "column" }}>
                {ativas.map((r) => (
                  <div key={r.id} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: "6px 12px", padding: "10px 0", borderTop: "1px solid var(--line2)", alignItems: "center" }}>
                    <span style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", minWidth: 0 }}>
                      <code style={{ font: "600 12.5px var(--mono)" }}>{r.padrao}</code><span style={{ color: "var(--ink2)" }}>→</span>
                      <span style={{ fontWeight: 600 }}>{alvo(r.acao)}</span>
                      <span style={{ fontSize: 12, color: "var(--ink2)" }}>· {r.casam} lançamentos · criada em {dataCurta(r.criado_em.slice(0, 10))}</span>
                    </span>
                    <button role="switch" aria-checked={r.ativa} aria-label={`Regra ${r.padrao} ${r.ativa ? "ligada" : "desligada"}`} onClick={() => alternar(r)}
                      style={{ display: "flex", alignItems: "center", gap: 8, border: 0, background: "transparent", color: "inherit", cursor: "pointer", fontSize: 12.5, minHeight: 32 }}>
                      <span style={{ position: "relative", width: 38, height: 22, border: `1px solid ${r.ativa ? "var(--ok)" : "var(--ink2)"}`, background: r.ativa ? "var(--ok-bg)" : "transparent" }}>
                        <span style={{ position: "absolute", top: 2, left: r.ativa ? 18 : 2, width: 16, height: 16, background: r.ativa ? "var(--ok)" : "var(--ink2)" }} />
                      </span>
                      <span style={{ width: 62, textAlign: "left" }}>{r.ativa ? "ligada" : "desligada"}</span>
                    </button>
                  </div>
                ))}
              </div>
            </section>
          </div>
        );
      }}
    </Painel>
  );
}
