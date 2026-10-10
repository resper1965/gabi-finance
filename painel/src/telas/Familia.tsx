import { useState } from "react";
import { Painel } from "../componentes/Painel";
import { api } from "../lib/api";
import { dataCurta } from "../lib/formato";
import { useToast } from "../lib/toast";
import { useApi } from "../lib/useApi";

interface Pessoa { id: string; nome: string }
interface Marcador { marcador: string; valor: string; unidade: string | null; em: string; fora_da_faixa: boolean }
interface Ponto { em: string; valor: string; unidade: string | null; fora_da_faixa: boolean }
interface Laudo { paperless_id: number; pessoa_sugerida: string | null; marcadores: { marcador: string; valor: string; unidade: string | null; em: string | null }[] }

/** Linha do tempo de um marcador (SVG simples; o ponto fora da faixa de referência aparece em vermelho). */
function Linha({ pontos }: { pontos: Ponto[] }) {
  const nums = pontos.map((p) => Number(p.valor.replace(",", "."))).filter((n) => !Number.isNaN(n));
  if (nums.length < 2) return <p style={{ color: "var(--ink2)", margin: 0 }}>Só um ponto até agora.</p>;
  const lo = Math.min(...nums), hi = Math.max(...nums), span = hi - lo || 1;
  const x = (i: number) => 10 + (i * 280) / (pontos.length - 1), y = (n: number) => 70 - ((n - lo) / span) * 60;
  return (
    <svg role="img" aria-label="Série do marcador" viewBox="0 0 300 80" style={{ width: "100%", maxWidth: 420, height: 90 }}>
      <polyline fill="none" stroke="var(--ink2)" strokeWidth="1.5" points={pontos.map((p, i) => `${x(i)},${y(Number(p.valor.replace(",", ".")))}`).join(" ")} />
      {pontos.map((p, i) => <circle key={i} cx={x(i)} cy={y(Number(p.valor.replace(",", ".")))} r="4" fill={p.fora_da_faixa ? "var(--bad, #c0392b)" : "var(--ok)"} />)}
    </svg>
  );
}

function Exames({ pessoa }: { pessoa: Pessoa }) {
  const lista = useApi<{ marcadores: Marcador[] }>(`/api/v1/familia/exames/${pessoa.id}`);
  const [marcador, setMarcador] = useState<string | null>(null);
  const serie = useApi<{ pontos: Ponto[] }>(marcador ? `/api/v1/familia/exames/${pessoa.id}/serie?marcador=${encodeURIComponent(marcador)}` : null);
  const [resumo, setResumo] = useState<string | null>(null);
  const avisar = useToast();
  const gerar = async () => {
    try { setResumo((await api.get<{ texto: string }>(`/api/v1/familia/exames/${pessoa.id}/resumo`)).dados.texto); } catch (e) { avisar((e as Error).message); }
  };
  return (
    <Painel leitura={lista} arquivo="familia-exames">
      {(d) => (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {d.marcadores.length === 0 && <p style={{ color: "var(--ink2)" }}>Nenhum exame de {pessoa.nome} ainda.</p>}
          {d.marcadores.map((m) => (
            <button key={m.marcador} className="btn btn-secondary" onClick={() => setMarcador(m.marcador)} aria-pressed={marcador === m.marcador}
              style={{ display: "flex", justifyContent: "space-between", textAlign: "left", gap: 12 }}>
              <span>{m.marcador}</span>
              <span style={{ color: m.fora_da_faixa ? "var(--bad, #c0392b)" : "inherit", fontWeight: 600 }}>{m.valor} {m.unidade ?? ""}{m.fora_da_faixa ? " · fora da faixa" : ""} <small>({dataCurta(m.em)})</small></span>
            </button>))}
          {marcador && serie.env && <div><h4 style={{ margin: "0 0 6px" }}>{marcador}</h4><Linha pontos={serie.env.dados.pontos} /></div>}
          {d.marcadores.length > 0 && <div><button className="btn btn-primary" onClick={gerar}>Gerar resumo para a consulta</button></div>}
          {resumo && <pre aria-label="Resumo para a consulta" style={{ whiteSpace: "pre-wrap", background: "var(--color-surface)", padding: 12, margin: 0 }}>{resumo}</pre>}
        </div>
      )}
    </Painel>
  );
}

function Laudos({ pessoas }: { pessoas: Pessoa[] }) {
  const leitura = useApi<{ itens: Laudo[] }>("/api/v1/familia/laudos");
  const [doc, setDoc] = useState("");
  const [dono, setDono] = useState<Record<number, string>>({});
  const avisar = useToast();
  if (leitura.estado === "erro" && leitura.erro?.status === 403) return null; // só o boss (grau total) confirma laudo: para os outros a área some
  const agir = async (fn: () => Promise<unknown>, ok: string) => { try { await fn(); avisar(ok); leitura.recarregar(); } catch (e) { avisar((e as Error).message); } };
  return (
    <Painel leitura={leitura} arquivo="familia-laudos">
      {(d) => (
        <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <h3 style={{ margin: 0, fontSize: 20 }}>Laudos para confirmar · {d.itens.length}</h3>
          <form style={{ display: "flex", gap: 8 }} onSubmit={(e) => { e.preventDefault(); if (doc) agir(() => api.post("/api/v1/familia/laudos", { paperless_id: Number(doc) }), "Laudo lido: confirme de quem é."); }}>
            <input aria-label="Número do documento no Paperless" value={doc} onChange={(e) => setDoc(e.target.value.replace(/\D/g, ""))} placeholder="Nº do documento no Paperless" />
            <button className="btn btn-secondary" type="submit">Ler laudo</button>
          </form>
          {d.itens.map((l) => (
            <div key={l.paperless_id} style={{ border: "1px solid var(--color-divider)", padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
              <strong>Documento {l.paperless_id} · {l.marcadores.length} marcadores</strong>
              <ul style={{ margin: 0, paddingLeft: 18 }}>{l.marcadores.map((m, i) => <li key={i}>{m.marcador}: {m.valor} {m.unidade ?? ""}</li>)}</ul>
              <label>De quem é o laudo?{" "}
                <select aria-label={`De quem é o laudo ${l.paperless_id}`} value={dono[l.paperless_id] ?? l.pessoa_sugerida ?? ""} onChange={(e) => setDono({ ...dono, [l.paperless_id]: e.target.value })}>
                  <option value="">escolher…</option>
                  {pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
                </select>
              </label>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-secondary" onClick={() => agir(() => api.post(`/api/v1/familia/laudos/${l.paperless_id}/rejeitar`), "Laudo descartado.")}>Descartar</button>
                <button className="btn btn-primary" disabled={!(dono[l.paperless_id] ?? l.pessoa_sugerida)}
                  onClick={() => agir(() => api.post(`/api/v1/familia/laudos/${l.paperless_id}/confirmar`, { pessoa_id: dono[l.paperless_id] ?? l.pessoa_sugerida }), "Exames registrados.")}>Confirmar e registrar</button>
              </div>
            </div>))}
        </section>
      )}
    </Painel>
  );
}

/** Família: exames por pessoa. Quem vê o quê vem da matriz de acesso no servidor; a saúde fica em arquivo próprio e criptografado. */
export function Familia() {
  const pessoas = useApi<{ itens: Pessoa[] }>("/api/v1/familia/pessoas");
  const [escolhida, setEscolhida] = useState<string | null>(null);
  return (
    <Painel leitura={pessoas} arquivo="familia">
      {(d) => {
        const atual = d.itens.find((p) => p.id === (escolhida ?? d.itens[0]?.id));
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            <label>Pessoa{" "}
              <select aria-label="Pessoa" value={atual?.id ?? ""} onChange={(e) => setEscolhida(e.target.value)}>
                {d.itens.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
              </select>
            </label>
            {atual ? <Exames key={atual.id} pessoa={atual} /> : <p style={{ color: "var(--ink2)" }}>Nenhuma pessoa liberada para você.</p>}
            <Laudos pessoas={d.itens} />
          </div>
        );
      }}
    </Painel>
  );
}
