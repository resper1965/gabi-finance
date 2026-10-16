import { useState } from "react";
import { Painel } from "../componentes/Painel";
import { api } from "../lib/api";
import { dataCurta } from "../lib/formato";
import { useToast } from "../lib/toast";
import { useApi } from "../lib/useApi";

export interface Pessoa { id: string; nome: string }
export interface Medicao { marcador: string; em: string; valor: string; unidade: string | null; ref_min: string | null; ref_max: string | null; fora_da_faixa: boolean; qualitativo: boolean }
export interface Ponto { em: string; valor: string; unidade: string | null; fora_da_faixa: boolean }
interface MarcadorLaudo { marcador: string; valor: string; unidade: string | null; em: string | null; qualitativo?: boolean }
interface Laudo { paperless_id: number; pessoa_sugerida: string | null; versao?: number; origem?: string; marcadores: MarcadorLaudo[] }
interface Falho { paperless_id: number; motivo: string | null }

const num = (v: string) => Number(v.replace(",", "."));

/** "acima" ou "abaixo" da faixa de referência, em TEXTO (a cor sozinha não basta); null = dentro ou sem faixa. */
export function posicao(m: Pick<Medicao, "valor" | "ref_min" | "ref_max" | "qualitativo">): "acima" | "abaixo" | null {
  if (m.qualitativo) return null;
  const v = num(m.valor);
  if (Number.isNaN(v)) return null;
  if (m.ref_max !== null && m.ref_max !== "" && v > num(m.ref_max)) return "acima";
  if (m.ref_min !== null && m.ref_min !== "" && v < num(m.ref_min)) return "abaixo";
  return null;
}

const COR_FORA = "var(--bad, #c0392b)";

/** Tabela marcador x data de coleta; resultados qualitativos ficam numa lista à parte (nunca viram número nem gráfico). */
export function TabelaExames({ historico }: { historico: Medicao[] }) {
  const numericos = historico.filter((h) => !h.qualitativo), qualitativos = historico.filter((h) => h.qualitativo);
  const datas = [...new Set(numericos.map((h) => h.em))].sort();
  const marcadores = [...new Set(numericos.map((h) => h.marcador))].sort();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {marcadores.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table aria-label="Exames por data de coleta" style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead><tr><th scope="col" style={{ textAlign: "left" }}>Marcador</th><th scope="col" style={{ textAlign: "left" }}>Referência</th>{datas.map((d) => <th key={d} scope="col">{dataCurta(d)}</th>)}</tr></thead>
            <tbody>
              {marcadores.map((mk) => {
                const linhas = numericos.filter((h) => h.marcador === mk);
                const ref = linhas.find((h) => h.ref_min !== null && h.ref_max !== null);
                return (
                  <tr key={mk}>
                    <th scope="row" style={{ textAlign: "left" }}>{mk}</th>
                    <td>{ref ? `${ref.ref_min} a ${ref.ref_max}` : "—"}</td>
                    {datas.map((d) => {
                      const h = linhas.find((x) => x.em === d);
                      const p = h ? posicao(h) : null;
                      return <td key={d} style={{ textAlign: "center", color: p ? COR_FORA : "inherit", fontWeight: p ? 600 : 400 }}>{h ? `${h.valor} ${h.unidade ?? ""}`.trim() : "—"}{p ? ` (${p})` : ""}</td>;
                    })}
                  </tr>);
              })}
            </tbody>
          </table>
        </div>)}
      {qualitativos.length > 0 && (
        <section aria-label="Resultados qualitativos">
          <h4 style={{ margin: "0 0 6px" }}>Resultados qualitativos (fora do gráfico)</h4>
          <ul style={{ margin: 0, paddingLeft: 18 }}>{qualitativos.map((q, i) => <li key={i}>{q.marcador}: {q.valor} <small>({dataCurta(q.em)})</small></li>)}</ul>
        </section>)}
    </div>
  );
}

/** Linha do tempo de um marcador (SVG simples) com a faixa de referência sombreada; ponto fora da faixa em vermelho. */
export function Serie({ pontos, refMin, refMax }: { pontos: Ponto[]; refMin?: string | null; refMax?: string | null }) {
  const nums = pontos.map((p) => num(p.valor)).filter((n) => !Number.isNaN(n));
  if (nums.length < 2) return <p style={{ color: "var(--ink2)", margin: 0 }}>Só um ponto até agora.</p>;
  const lo0 = refMin ? num(refMin) : NaN, hi0 = refMax ? num(refMax) : NaN;
  const lo = Math.min(...nums, ...(Number.isNaN(lo0) ? [] : [lo0])), hi = Math.max(...nums, ...(Number.isNaN(hi0) ? [] : [hi0])), span = hi - lo || 1;
  const x = (i: number) => 10 + (i * 280) / (pontos.length - 1), y = (n: number) => 70 - ((n - lo) / span) * 60;
  const topo = Number.isNaN(hi0) ? y(hi) : y(hi0), base = Number.isNaN(lo0) ? y(lo) : y(lo0);
  return (
    <svg role="img" aria-label="Série do marcador" viewBox="0 0 300 80" style={{ width: "100%", maxWidth: 420, height: 90 }}>
      {(!Number.isNaN(lo0) || !Number.isNaN(hi0)) && <rect data-testid="faixa" x="10" width="280" y={topo} height={Math.max(base - topo, 1)} fill="var(--ok)" opacity="0.15" />}
      <polyline fill="none" stroke="var(--ink2)" strokeWidth="1.5" points={pontos.map((p, i) => `${x(i)},${y(num(p.valor))}`).join(" ")} />
      {pontos.map((p, i) => <circle key={i} cx={x(i)} cy={y(num(p.valor))} r="4" fill={p.fora_da_faixa ? COR_FORA : "var(--ok)"} />)}
    </svg>
  );
}

function Versoes({ paperlessId }: { paperlessId: number }) {
  const v = useApi<{ versoes: { versao: number }[]; diferencas: { marcador: string; em: string | null; antes: string | null; depois: string | null }[] }>(`/api/v1/familia/exames/-/laudos/${paperlessId}/versoes`);
  return (
    <Painel leitura={v} arquivo="familia-versoes">
      {(d) => (
        <section aria-label={`Versões do documento ${paperlessId}`} style={{ fontSize: 14 }}>
          <strong>Versão atual {d.versoes[d.versoes.length - 1]?.versao} · comparada com a anterior</strong>
          {d.diferencas.length === 0 ? <p style={{ margin: "4px 0 0" }}>Nenhuma diferença.</p>
            : <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>{d.diferencas.map((x, i) => <li key={i}>{x.marcador}{x.em ? ` (${dataCurta(x.em)})` : ""}: {x.antes ?? "não existia"} → {x.depois ?? "sumiu"}</li>)}</ul>}
        </section>)}
    </Painel>
  );
}

function Apelidos() {
  const leitura = useApi<{ itens: { apelido: string; marcador: string }[]; sugestoes: string[] }>("/api/v1/familia/marcadores/apelidos");
  const [apelido, setApelido] = useState(""), [marcador, setMarcador] = useState("");
  const avisar = useToast();
  const agir = async (fn: () => Promise<unknown>, ok: string) => { try { await fn(); avisar(ok); leitura.recarregar(); } catch (e) { avisar((e as Error).message); } };
  return (
    <Painel leitura={leitura} arquivo="familia-apelidos">
      {(d) => (
        <details>
          <summary>Apelidos de marcador · {d.itens.length}</summary>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
            <ul style={{ margin: 0, paddingLeft: 18 }}>{d.itens.map((a) => <li key={a.apelido}>{a.apelido} → {a.marcador}</li>)}</ul>
            {d.sugestoes.length > 0 && <p style={{ margin: 0 }}>Grafias parecidas para juntar: {d.sugestoes.join(", ")}</p>}
            <form style={{ display: "flex", gap: 8, flexWrap: "wrap" }} onSubmit={(e) => { e.preventDefault(); if (apelido && marcador) agir(() => api.put("/api/v1/familia/marcadores/apelidos", { apelido, marcador }), "Apelido salvo."); }}>
              <input aria-label="Apelido" value={apelido} onChange={(e) => setApelido(e.target.value)} placeholder="Como aparece no laudo" />
              <input aria-label="Marcador" value={marcador} onChange={(e) => setMarcador(e.target.value)} placeholder="Nome do marcador" />
              <button className="btn btn-secondary" type="submit">Salvar apelido</button>
              <button className="btn btn-secondary" type="button" onClick={() => agir(() => api.post("/api/v1/familia/marcadores/reaplicar"), "Apelidos reaplicados.")}>Reaplicar nos exames</button>
            </form>
          </div>
        </details>)}
    </Painel>
  );
}

/** Fila "A confirmar": dono sugerido editável, seleção múltipla e confirmação em lote; falhas com o motivo; reprocessar e apelidos. Some para quem não é boss (403). */
export function FilaExames({ pessoas }: { pessoas: Pessoa[] }) {
  const leitura = useApi<{ itens: Laudo[]; falhos?: Falho[] }>("/api/v1/familia/laudos");
  const [doc, setDoc] = useState("");
  const [dono, setDono] = useState<Record<number, string>>({});
  const [marcados, setMarcados] = useState<Set<number>>(new Set());
  const [versoes, setVersoes] = useState<number | null>(null);
  const avisar = useToast();
  if (leitura.estado === "erro" && leitura.erro?.status === 403) return null;
  const agir = async (fn: () => Promise<unknown>, ok: string) => { try { await fn(); avisar(ok); setMarcados(new Set()); leitura.recarregar(); } catch (e) { avisar((e as Error).message); } };
  const reprocessar = (corpo: object, texto: string) => { if (window.confirm(texto)) agir(() => api.post("/api/v1/familia/exames/reprocessar", corpo), "Reprocessado."); };
  return (
    <Painel leitura={leitura} arquivo="familia-laudos">
      {(d) => {
        const donoDe = (l: Laudo) => dono[l.paperless_id] ?? l.pessoa_sugerida ?? "";
        const escolhidos = d.itens.filter((l) => marcados.has(l.paperless_id));
        return (
          <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <h3 style={{ margin: 0, fontSize: 20 }}>Laudos para confirmar · {d.itens.length}</h3>
            <form style={{ display: "flex", gap: 8 }} onSubmit={(e) => { e.preventDefault(); if (doc) agir(() => api.post("/api/v1/familia/laudos", { paperless_id: Number(doc) }), "Laudo lido: confirme de quem é."); }}>
              <input aria-label="Número do documento no Paperless" value={doc} onChange={(e) => setDoc(e.target.value.replace(/\D/g, ""))} placeholder="Nº do documento no Paperless" />
              <button className="btn btn-secondary" type="submit">Ler laudo</button>
            </form>
            {d.itens.map((l) => (
              <div key={l.paperless_id} style={{ border: "1px solid var(--color-divider)", padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input type="checkbox" aria-label={`Selecionar documento ${l.paperless_id}`} checked={marcados.has(l.paperless_id)}
                    onChange={(e) => { const n = new Set(marcados); e.target.checked ? n.add(l.paperless_id) : n.delete(l.paperless_id); setMarcados(n); }} />
                  <strong>Documento {l.paperless_id} · {l.marcadores.length} marcadores{l.versao && l.versao > 1 ? ` · versão ${l.versao}` : ""}</strong>
                </label>
                <ul style={{ margin: 0, paddingLeft: 18 }}>{l.marcadores.map((m, i) => <li key={i}>{m.marcador}: {m.valor} {m.unidade ?? ""}{m.qualitativo ? " (qualitativo)" : ""}</li>)}</ul>
                <label>De quem é o laudo?{" "}
                  <select aria-label={`De quem é o laudo ${l.paperless_id}`} value={donoDe(l)} onChange={(e) => setDono({ ...dono, [l.paperless_id]: e.target.value })}>
                    <option value="">escolher…</option>
                    {pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
                  </select>
                </label>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button className="btn btn-secondary" onClick={() => agir(() => api.post(`/api/v1/familia/laudos/${l.paperless_id}/rejeitar`), "Laudo descartado.")}>Descartar</button>
                  <button className="btn btn-secondary" onClick={() => reprocessar({ paperless_id: l.paperless_id }, `Reprocessar o documento ${l.paperless_id}? A leitura atual fica guardada como versão anterior.`)}>Reprocessar</button>
                  {l.versao && l.versao > 1 && <button className="btn btn-secondary" onClick={() => setVersoes(versoes === l.paperless_id ? null : l.paperless_id)}>Comparar versões</button>}
                </div>
                {versoes === l.paperless_id && <Versoes paperlessId={l.paperless_id} />}
              </div>))}
            {d.itens.length > 0 && (
              <div>
                <button className="btn btn-primary" disabled={escolhidos.length === 0 || escolhidos.some((l) => !donoDe(l))}
                  onClick={() => agir(() => api.post("/api/v1/familia/laudos/lote", { itens: escolhidos.map((l) => ({ paperless_id: l.paperless_id, pessoa_id: donoDe(l) })) }), "Exames registrados.")}>Confirmar selecionados</button>
              </div>)}
            {(d.falhos ?? []).length > 0 && (
              <section aria-label="Documentos que falharam">
                <h4 style={{ margin: "0 0 6px" }}>Não consegui ler · {(d.falhos ?? []).length}</h4>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {(d.falhos ?? []).map((f) => (
                    <li key={f.paperless_id}>Documento {f.paperless_id}: {f.motivo ?? "sem motivo registrado"}{" "}
                      <button className="btn btn-secondary" onClick={() => reprocessar({ paperless_id: f.paperless_id }, `Tentar de novo o documento ${f.paperless_id}?`)}>Reprocessar</button></li>))}
                </ul>
              </section>)}
            <div><button className="btn btn-secondary" onClick={() => reprocessar({ todos: true }, "Reprocessar TODOS os exames? Cada documento ganha uma versão nova (a anterior fica) e pode gastar o modelo.")}>Reprocessar todos</button></div>
            <Apelidos />
          </section>);
      }}
    </Painel>
  );
}

interface Mensagem { id: number; de_pessoa: string | null; recebida_em: string; texto: string; lida_em?: string | null }

/** Mensagens de saúde sem anexo: ficam só no cofre cifrado (nunca no banco principal). O texto é de terceiros: aparece como texto puro, nunca como instrução.
 *  "Marcar como lida" só anota a data no cofre; nada é apagado. Some para quem não é boss (403). */
export function MensagensSaude({ pessoas }: { pessoas: Pessoa[] }) {
  const leitura = useApi<{ itens: Mensagem[] }>("/api/v1/familia/mensagens");
  const avisar = useToast();
  if (leitura.estado === "erro" && leitura.erro?.status === 403) return null;
  const nome = (id: string | null) => pessoas.find((p) => p.id === id)?.nome ?? (id ? id : "remetente não identificado");
  const marcar = async (id: number) => { try { await api.post(`/api/v1/familia/mensagens/${id}/lida`); leitura.recarregar(); } catch (e) { avisar((e as Error).message); } };
  return (
    <Painel leitura={leitura} arquivo="familia-mensagens">
      {(d) => (
        <section aria-label="Mensagens de saúde" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <h3 style={{ margin: 0, fontSize: 20 }}>Mensagens de saúde · {d.itens.filter((m) => !m.lida_em).length} não lidas</h3>
          <p style={{ margin: 0, color: "var(--ink2)" }}>Estas mensagens ficam só no arquivo de saúde cifrado: não vão para o banco, para avisos nem para o servidor MCP. Cada abertura desta lista fica registrada.</p>
          {d.itens.length === 0 && <p style={{ color: "var(--ink2)" }}>Nenhuma mensagem de saúde guardada.</p>}
          {d.itens.map((m) => (
            <article key={m.id} aria-label={`Mensagem ${m.id}`} style={{ border: "1px solid var(--color-divider)", padding: 12, display: "flex", flexDirection: "column", gap: 6, opacity: m.lida_em ? 0.7 : 1 }}>
              <strong>{nome(m.de_pessoa)} · {dataCurta(m.recebida_em)}{m.lida_em ? " · lida" : ""}</strong>
              <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{m.texto}</p>
              {!m.lida_em && <div><button className="btn btn-secondary" onClick={() => marcar(m.id)}>Marcar como lida</button></div>}
            </article>))}
        </section>)}
    </Painel>
  );
}
