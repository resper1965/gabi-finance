import { useState } from "react";
import { Bloco } from "../componentes/Bloco";
import { Painel } from "../componentes/Painel";
import { Vazio } from "../componentes/Estados";
import { api } from "../lib/api";
import { useToast } from "../lib/toast";
import { useApi } from "../lib/useApi";

interface Remetente { numero: string; nome: string | null; qtd: number }
interface Aprovado { pessoa_id: string; nome: string; numero: string | null; papel: string | null }
interface Grupo { id_grupo: string; nome: string; aprovado: boolean }
interface Parametros { modo: "registro" | "ativo"; palavras_risco: string[]; horas_sem_receber: number; anexo_max_mb: number }

const PAPEIS: [string, string][] = [["familia", "Família"], ["prestador", "Prestador"], ["cobranca", "Cobrança"]];
const rotuloPapel = (p: string | null) => PAPEIS.find(([k]) => k === p)?.[1] ?? "—";
const suave = { color: "var(--ink2)" } as const;
const linha = { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", justifyContent: "space-between", borderTop: "1px solid var(--color-divider)", padding: "8px 0" } as const;
const lista = { listStyle: "none", margin: 0, padding: 0 } as const;

/** Executa uma ação, avisa o resultado e recarrega; em erro mantém a tela como está e mostra a mensagem. */
function useAcao(recarregar: () => void) {
  const avisar = useToast();
  const [erro, setErro] = useState<string | null>(null);
  const agir = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); setErro(null); avisar(ok); recarregar(); return true; } catch (e) { const m = (e as Error).message; setErro(m); avisar(m); return false; }
  };
  return { erro, agir };
}
const Aviso = ({ erro }: { erro: string | null }) => (erro ? <p role="alert" style={{ margin: 0, color: "var(--danger)" }}>{erro}</p> : null);

function Fila() {
  const leitura = useApi<{ fila: Remetente[]; aprovados: Aprovado[] }>(`/api/v1/escuta/remetentes`);
  const { erro, agir } = useAcao(leitura.recarregar);
  const [escolhendo, setEscolhendo] = useState<string | null>(null);
  return (
    <Painel leitura={leitura} arquivo="escuta-remetentes">
      {(d) => (
        <>
          <Bloco titulo={`Novos remetentes · ${d.fila.length}`} nota="Quem escreveu e a Gabi ainda não conhece.">
            <Aviso erro={erro} />
            {d.fila.length === 0 ? <Vazio frase="Nenhum remetente novo na fila." /> : (
              <ul style={lista}>
                {d.fila.map((r) => (
                  <li key={r.numero} style={linha}>
                    <span><strong>{r.nome ?? r.numero}</strong>{r.nome && <span style={suave}> · {r.numero}</span>} <span style={suave}>· {r.qtd} {r.qtd === 1 ? "mensagem" : "mensagens"}</span></span>
                    <span style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                      {escolhendo === r.numero ? (
                        <>
                          <span style={suave}>Aprovar como:</span>
                          {PAPEIS.map(([papel, rotulo]) => (
                            <button key={papel} className="btn btn-primary" onClick={async () => { if (await agir(() => api.post(`/api/v1/escuta/remetentes/${encodeURIComponent(r.numero)}/aprovar`, { papel }), "Remetente aprovado.")) setEscolhendo(null); }}>{rotulo}</button>))}
                          <button className="btn btn-secondary" onClick={() => setEscolhendo(null)}>Cancelar</button>
                        </>
                      ) : (
                        <>
                          <button className="btn btn-primary" onClick={() => setEscolhendo(r.numero)}>Aprovar</button>
                          <button className="btn btn-secondary" onClick={() => agir(() => api.post(`/api/v1/escuta/remetentes/${encodeURIComponent(r.numero)}/ignorar`), "Remetente ignorado.")}>Ignorar</button>
                          <button className="btn btn-secondary" onClick={() => agir(() => api.post(`/api/v1/escuta/remetentes/${encodeURIComponent(r.numero)}/bloquear`), "Remetente bloqueado.")}>Bloquear</button>
                        </>
                      )}
                    </span>
                  </li>))}
              </ul>)}
          </Bloco>
          <Bloco titulo={`Aprovados · ${d.aprovados.length}`}>
            {d.aprovados.length === 0 ? <Vazio frase="Ninguém aprovado ainda." /> : (
              <ul style={lista}>
                {d.aprovados.map((a) => (
                  <li key={a.pessoa_id} style={linha}><strong>{a.nome}</strong><span style={suave}>{a.numero ?? "sem número"} · {rotuloPapel(a.papel)}</span></li>))}
              </ul>)}
          </Bloco>
        </>
      )}
    </Painel>
  );
}

function Grupos() {
  const leitura = useApi<{ grupos: Grupo[] }>(`/api/v1/escuta/grupos`);
  const { erro, agir } = useAcao(leitura.recarregar);
  return (
    <Painel leitura={leitura} arquivo="escuta-grupos">
      {(d) => (
        <Bloco titulo="Grupos">
          <Aviso erro={erro} />
          {d.grupos.length === 0 ? <Vazio frase="Nenhum grupo visto ainda." /> : (
            <ul style={lista}>
              {d.grupos.map((g) => (
                <li key={g.id_grupo} style={linha}>
                  <strong>{g.nome}</strong>
                  {g.aprovado ? <span style={suave}>Aprovado</span>
                    : <button className="btn btn-primary" aria-label={`Aprovar grupo ${g.nome}`} onClick={() => agir(() => api.post(`/api/v1/escuta/grupos/${encodeURIComponent(g.id_grupo)}/aprovar`), "Grupo aprovado.")}>Aprovar</button>}
                </li>))}
            </ul>)}
        </Bloco>
      )}
    </Painel>
  );
}

function Ajustes() {
  const leitura = useApi<Parametros>(`/api/v1/escuta/parametros`);
  const { erro, agir } = useAcao(leitura.recarregar);
  const [confirmando, setConfirmando] = useState(false);
  const [nova, setNova] = useState("");
  const [horas, setHoras] = useState<string | null>(null);
  const [mb, setMb] = useState<string | null>(null);
  const gravar = (corpo: Partial<Parametros>, ok: string) => agir(() => api.put(`/api/v1/escuta/parametros`, corpo), ok);
  return (
    <Painel leitura={leitura} arquivo="escuta-parametros">
      {(p) => (
        <Bloco titulo="Ajustes da escuta">
          <Aviso erro={erro} />
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }} role="group" aria-label="Modo">
            <span>Modo:</span>
            {(["registro", "ativo"] as const).map((m) => (
              <button key={m} className={`btn ${p.modo === m ? "btn-primary" : "btn-secondary"}`} aria-pressed={p.modo === m}
                onClick={() => { if (m === p.modo) setConfirmando(false); else if (m === "ativo") setConfirmando(true); else { setConfirmando(false); gravar({ modo: "registro" }, "Modo registro."); } }}>{m === "registro" ? "Registro" : "Ativo"}</button>))}
          </div>
          {confirmando && (
            <div role="alert" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <p style={{ margin: 0 }}>Atenção: em registro a escuta só registra; em ativo ela cria pedidos e avisa.</p>
              <span style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-primary" onClick={async () => { if (await gravar({ modo: "ativo" }, "Modo ativo ligado.")) setConfirmando(false); }}>Confirmar modo ativo</button>
                <button className="btn btn-secondary" onClick={() => setConfirmando(false)}>Cancelar</button>
              </span>
            </div>)}
          <div>
            <div style={{ marginBottom: 6 }}>Palavras de risco</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
              {p.palavras_risco.length === 0 && <span style={suave}>Nenhuma palavra ainda.</span>}
              {p.palavras_risco.map((w) => (
                <span key={w} style={{ border: "1px solid var(--color-divider)", padding: "2px 8px", display: "inline-flex", gap: 6, alignItems: "center" }}>
                  {w}<button className="btn btn-secondary" aria-label={`Remover ${w}`} style={{ padding: "0 6px" }} onClick={() => gravar({ palavras_risco: p.palavras_risco.filter((x) => x !== w) }, "Palavra removida.")}>×</button>
                </span>))}
            </div>
            <form style={{ display: "flex", gap: 8 }} onSubmit={async (e) => {
              e.preventDefault();
              const w = nova.trim();
              if (!w || p.palavras_risco.includes(w)) return;
              if (await gravar({ palavras_risco: [...p.palavras_risco, w] }, "Palavra adicionada.")) setNova("");
            }}>
              <input aria-label="Nova palavra de risco" value={nova} maxLength={60} onChange={(e) => setNova(e.target.value)} />
              <button className="btn btn-secondary" type="submit" aria-label="Adicionar palavra">Adicionar</button>
            </form>
          </div>
          <form style={{ display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }} onSubmit={(e) => {
            e.preventDefault();
            const corpo: Partial<Parametros> = {};
            if (horas !== null) corpo.horas_sem_receber = Number(horas);
            if (mb !== null) corpo.anexo_max_mb = Number(mb);
            if (Object.keys(corpo).length) gravar(corpo, "Limites salvos.").then((ok) => { if (ok) { setHoras(null); setMb(null); } });
          }}>
            <label>Horas sem receber<br /><input type="number" min={1} max={168} value={horas ?? p.horas_sem_receber} onChange={(e) => setHoras(e.target.value)} /></label>
            <label>Tamanho máximo de anexo (MB)<br /><input type="number" min={1} max={100} value={mb ?? p.anexo_max_mb} onChange={(e) => setMb(e.target.value)} /></label>
            <button className="btn btn-primary" type="submit">Salvar limites</button>
          </form>
        </Bloco>
      )}
    </Painel>
  );
}

/** Escuta: quem a Gabi escuta no WhatsApp. Número, nome e palavras de risco são dados do servidor; nada vai para o console. */
export function Escuta() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <Fila />
      <Grupos />
      <Ajustes />
    </div>
  );
}
