import { useState } from "react";
import { ArrowRight, Search, Sparkles } from "lucide-react";
import { Etiqueta } from "../componentes/Etiqueta";
import { Vazio } from "../componentes/Estados";
import { Painel } from "../componentes/Painel";
import { api } from "../lib/api";
import { dataCurta, formatarBRL } from "../lib/formato";
import { useToast } from "../lib/toast";
import { useApi } from "../lib/useApi";

interface Condicao { conta_id?: number[]; valor_min?: number; valor_max?: number; dias_semana?: number[] }
interface Regra { id: number; padrao: string; acao: Record<string, number | string>; condicao?: Condicao | null; ativa: boolean; criado_em: string; casam: number }
interface Sug { id: number; tipo: string; payload: { padrao?: string; acao?: Record<string, number | string>; condicao?: Condicao | null }; motivo: string; impacto: { passado?: number; futuro_estimado?: number } | null }
interface Item { id: number | string; nome: string }

const DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];
const reais = (c: number) => formatarBRL((c / 100).toFixed(2));
/** "só se: conta 1, 2 · de R$ 10,00 a R$ 50,00 · sáb, dom" (vazio quando a regra não tem condição). */
export function textoCondicao(c?: Condicao | null): string {
  if (!c) return "";
  const p: string[] = [];
  if (c.conta_id?.length) p.push(`conta ${c.conta_id.join(", ")}`);
  if (c.valor_min !== undefined && c.valor_max !== undefined) p.push(`de ${reais(c.valor_min)} a ${reais(c.valor_max)}`);
  else if (c.valor_min !== undefined) p.push(`a partir de ${reais(c.valor_min)}`);
  else if (c.valor_max !== undefined) p.push(`até ${reais(c.valor_max)}`);
  if (c.dias_semana?.length) p.push(c.dias_semana.map((d) => DIAS[d]).join(", "));
  return p.length ? `só se: ${p.join(" · ")}` : "";
}

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
          <div className="pilha" style={{ gap: 32, maxWidth: 1040 }}>
            <div className="quadro" data-tom="nota">
              <Sparkles size={18} strokeWidth={1.7} aria-hidden="true" />
              <span><strong>A Gabi só sugere.</strong> Nenhuma regra liga sozinha. Quando você aprova, ela passa a valer para os lançamentos passados e para os próximos, e você pode desligar quando quiser.</span>
            </div>
            <section className="secao" aria-label="Sugestões da Gabi">
              <div className="secao-cab">
                <span className="fila" style={{ gap: 10 }}><h2>Sugestões da Gabi</h2>{sugs.length > 0 && <Etiqueta tipo="conferir" texto={`${sugs.length} ${sugs.length === 1 ? "pendente" : "pendentes"}`} />}</span>
                {marcadas.length > 0 && (
                  <span className="fila">
                    <span className="miudo num">{marcadas.length} selecionadas</span>
                    <button className="btn btn-sm" onClick={() => decidir(marcadas, "rejeitar")}>Rejeitar</button>
                    <button className="btn btn-primary btn-sm" onClick={() => decidir(marcadas, "aprovar")}>Aprovar e ligar</button>
                  </span>
                )}
              </div>
              {sugs.length === 0 && <Vazio frase="Sem sugestões de regra por enquanto. Quando você classificar o mesmo estabelecimento algumas vezes, a Gabi propõe aqui." />}
              <ul className="pauta">
                {sugs.map((g) => (
                  <li key={g.id} data-sugestao className="sugestao">
                    <input type="checkbox" aria-label={`Selecionar sugestão ${g.payload.padrao}`} checked={marcadas.includes(g.id)} onChange={(e) => setMarcadas(e.target.checked ? [...marcadas, g.id] : marcadas.filter((x) => x !== g.id))} style={{ marginTop: 6 }} />
                    <div className="pilha-curta" style={{ gap: 8 }}>
                      <div className="fila">
                        <code className="padrao">{g.payload.padrao}</code>
                        <ArrowRight size={15} strokeWidth={1.8} aria-hidden="true" style={{ color: "var(--tinta-3)" }} />
                        {g.payload.acao?.categoria_id !== undefined && categorias.length > 0
                          ? (
                            <select aria-label={`Categoria da sugestão ${g.payload.padrao}`} value={edicoes[g.id] ?? Number(g.payload.acao.categoria_id ?? 0)}
                              onChange={(e) => setEdicoes({ ...edicoes, [g.id]: Number(e.target.value) })} style={{ fontWeight: 600 }}>
                              {g.payload.acao.categoria_id == null && <option value={0}>escolher…</option>}
                              {categorias.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
                            </select>
                          )
                          : <span className="forte">{alvo(g.payload.acao)}</span>}
                        <Etiqueta tipo="conferir" texto="sugestão" />
                      </div>
                      <span className="suave">{g.motivo}</span>
                      {g.impacto && <span className="miudo">afeta <strong style={{ color: "var(--tinta)" }}>{g.impacto.passado ?? 0} lançamentos passados</strong> e todos os próximos (~{g.impacto.futuro_estimado ?? 0} por mês)</span>}
                      <div className="fila">
                        <button className="btn btn-primary btn-sm" disabled={g.payload.acao?.categoria_id === null && !edicoes[g.id]} onClick={() => decidir([g.id], "aprovar")}>Aprovar e ligar</button>
                        <button className="btn btn-sm" onClick={() => decidir([g.id], "rejeitar")}>Rejeitar</button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
            <section className="secao" aria-label="Regras ativas">
              <div className="secao-cab">
                <span className="fila" style={{ gap: 10 }}><h2>Regras ativas</h2><span className="secao-nota num">{d.itens.filter((r) => r.ativa).length} ligadas de {d.itens.length}</span></span>
                <span className="busca" style={{ flex: "0 1 280px" }}><Search size={15} strokeWidth={1.8} aria-hidden="true" /><input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar regra" aria-label="Buscar regra" /></span>
              </div>
              {ativas.length === 0 && <Vazio frase={busca ? "Nenhuma regra com esse texto." : "Nenhuma regra ainda. Aprove uma sugestão da Gabi ou use \"sempre assim\" em Lançamentos."} />}
              <ul className="pauta">
                {ativas.map((r) => (
                  <li key={r.id} className="linha-item" style={{ opacity: r.ativa ? 1 : 0.7 }}>
                    <span className="pilha-curta" style={{ gap: 3 }}>
                      <span className="fila"><code className="padrao">{r.padrao}</code><ArrowRight size={14} strokeWidth={1.8} aria-hidden="true" style={{ color: "var(--tinta-3)" }} /><span className="forte">{alvo(r.acao)}</span>
                        {textoCondicao(r.condicao) && <span className="miudo">({textoCondicao(r.condicao)})</span>}</span>
                      <span className="miudo"><span className="num">{r.casam}</span> lançamentos · criada em <span className="mono">{dataCurta(r.criado_em.slice(0, 10))}</span></span>
                    </span>
                    <button role="switch" className="interruptor" aria-checked={r.ativa} aria-label={`Regra ${r.padrao} ${r.ativa ? "ligada" : "desligada"}`} onClick={() => alternar(r)}>
                      <span className="interruptor-trilho" aria-hidden="true" />
                      <span className="interruptor-rotulo">{r.ativa ? "ligada" : "desligada"}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        );
      }}
    </Painel>
  );
}
