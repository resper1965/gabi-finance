import { useState } from "react";
import { Bloco } from "../componentes/Bloco";
import { Painel } from "../componentes/Painel";
import { Vazio } from "../componentes/Estados";
import { api } from "../lib/api";
import { Aviso, useAcao, type Acao } from "../lib/useAcao";
import { useApi, type Leitura } from "../lib/useApi";

interface Fonte { id: number; conta: string; provedor: "google" | "graph"; calendario_id: string; nome: string | null; estado: "sim" | "nao" | "a_decidir"; sincronizada_em: string | null; ultimo_erro: string | null; eventos: number }
interface Parametros { privados: "mostrar" | "so_painel" | "ocultar"; fuso: string; janela_passado_dias: number; janela_futuro_dias: number }

const ESTADO = { sim: "Lendo", nao: "Desligada", a_decidir: "A decidir" } as const;
const PRIVADOS: [Parametros["privados"], string][] = [["mostrar", "Mostrar o título"], ["so_painel", "Título só no painel"], ["ocultar", "Ocultar sempre"]];
const suave = { color: "var(--ink2)" } as const;
const linha = { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", justifyContent: "space-between", borderTop: "1px solid var(--color-divider)", padding: "8px 0" } as const;
const lista = { listStyle: "none", margin: 0, padding: 0 } as const;
const inteiro = (v: string, min: number, max: number) => (/^\d+$/.test(v.trim()) && Number(v) >= min && Number(v) <= max ? Number(v) : null);
/** A última leitura vem em UTC: mostra no fuso da agenda (padrão Brasília; fuso inválido cai no padrão). */
const quando = (iso: string | null, fuso = "America/Sao_Paulo") => {
  if (!iso) return "nunca";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "nunca";
  const fmt = (tz: string) => new Intl.DateTimeFormat("pt-BR", { timeZone: tz, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }).format(d);
  try { return fmt(fuso); } catch { return fmt("America/Sao_Paulo"); }
};

function Fontes({ leitura, acao, fuso }: { leitura: Leitura<{ fontes: Fonte[] }>; acao: Acao; fuso?: string }) {
  const { ocupado, erros, agir } = acao;
  const [conta, setConta] = useState("");
  const [provedor, setProvedor] = useState<"google" | "graph">("google");
  const [resumo, setResumo] = useState<string | null>(null);
  return (
    <Painel leitura={leitura} arquivo="agenda-fontes">
      {(d) => (
        <Bloco titulo={`Agendas · ${d.fontes.length}`} nota="Só leitura: a Gabi nunca cria, move nem apaga compromisso. Nada é lido até você liberar.">
          <Aviso erro={erros.geral} />
          {d.fontes.length === 0 ? <Vazio frase="Nenhuma agenda cadastrada. Cadastre uma conta abaixo." /> : (
            <ul style={lista}>
              {d.fontes.map((f) => {
                const rotulo = f.nome ? `${f.conta} (${f.nome})` : f.conta;
                return (
                  <li key={f.id} style={linha}>
                    <span><strong>{rotulo}</strong> <span style={suave}>· {f.provedor === "google" ? "Google" : "Microsoft"} · {ESTADO[f.estado]} · {f.eventos} compromisso(s) · última leitura {quando(f.sincronizada_em, fuso)}</span></span>
                    <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {f.estado !== "sim" && <button className="btn btn-primary" disabled={ocupado} aria-label={`Liberar ${rotulo}`} onClick={() => agir(`f${f.id}`, () => api.patch(`/api/v1/agenda/fontes/${f.id}`, { estado: "sim" }), "Agenda liberada.", leitura.recarregar)}>Liberar</button>}
                      {f.estado !== "nao" && <button className="btn btn-secondary" disabled={ocupado} aria-label={`Desligar ${rotulo}`} onClick={() => agir(`f${f.id}`, () => api.patch(`/api/v1/agenda/fontes/${f.id}`, { estado: "nao" }), "Agenda desligada.", leitura.recarregar)}>Desligar</button>}
                      {f.provedor === "google" && f.calendario_id === "primary" && (
                        <button className="btn btn-secondary" disabled={ocupado} aria-label={`Descobrir calendários de ${f.conta}`} onClick={() => agir(`f${f.id}`, async () => {
                          const r = await api.post<{ calendarios: { nova: boolean }[] }>(`/api/v1/agenda/fontes/${f.id}/calendarios/descobrir`);
                          const n = r.dados.calendarios.length, novos = r.dados.calendarios.filter((c) => c.nova).length;
                          setResumo(`${f.conta}: ${n} calendário(s) encontrado(s), ${novos} novo(s). Libere os que quiser ler.`);
                        }, "Calendários descobertos.", leitura.recarregar)}>Descobrir calendários</button>)}
                    </span>
                    {f.ultimo_erro && <p style={{ margin: 0, flexBasis: "100%", ...suave }}>Último erro: {f.ultimo_erro}</p>}
                    <Aviso erro={erros[`f${f.id}`]} />
                  </li>);
              })}
            </ul>)}
          {resumo && <p role="status" style={{ margin: 0, ...suave }}>{resumo}</p>}
          <form style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "end" }} onSubmit={async (e) => {
            e.preventDefault();
            if (ocupado || !conta.trim()) return;
            if (await agir("geral", () => api.post("/api/v1/agenda/fontes", { conta: conta.trim(), provedor }), "Conta cadastrada.", leitura.recarregar)) setConta("");
          }}>
            <label>Conta (e-mail)<br /><input aria-label="Conta da agenda" value={conta} onChange={(e) => setConta(e.target.value)} /></label>
            <label>Tipo<br />
              <select aria-label="Tipo da conta" value={provedor} onChange={(e) => setProvedor(e.target.value as "google" | "graph")}>
                <option value="google">Google</option><option value="graph">Microsoft (ainda não lê)</option>
              </select></label>
            <button className="btn btn-primary" type="submit" disabled={ocupado}>Cadastrar conta</button>
          </form>
        </Bloco>
      )}
    </Painel>
  );
}

function Ajustes({ leitura, acao }: { leitura: Leitura<Parametros>; acao: Acao }) {
  const { ocupado, erros, agir } = acao;
  const [privados, setPrivados] = useState<Parametros["privados"] | null>(null);
  const [fuso, setFuso] = useState<string | null>(null);
  const [passado, setPassado] = useState<string | null>(null);
  const [futuro, setFuturo] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <Painel leitura={leitura} arquivo="agenda-parametros">
      {(p) => (
        <Bloco titulo="Ajustes da agenda">
          <Aviso erro={erros.ajustes} />
          <form style={{ display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }} onSubmit={async (e) => {
            e.preventDefault();
            if (ocupado) return;
            const corpo: Partial<Parametros> = {};
            if (privados !== null && privados !== p.privados) corpo.privados = privados;
            if (fuso !== null && fuso.trim() !== p.fuso) corpo.fuso = fuso.trim();
            if (passado !== null) { const v = inteiro(passado, 0, 60); if (v === null) { setMsg("Dias para trás: informe um inteiro de 0 a 60."); return; } corpo.janela_passado_dias = v; }
            if (futuro !== null) { const v = inteiro(futuro, 7, 365); if (v === null) { setMsg("Dias para frente: informe um inteiro de 7 a 365."); return; } corpo.janela_futuro_dias = v; }
            setMsg(null);
            if (Object.keys(corpo).length === 0) return;
            if (await agir("ajustes", () => api.put("/api/v1/agenda/parametros", corpo), "Ajustes salvos.", leitura.recarregar)) { setPrivados(null); setFuso(null); setPassado(null); setFuturo(null); }
          }}>
            <label>Compromissos privados<br />
              <select value={privados ?? p.privados} onChange={(e) => { setPrivados(e.target.value as Parametros["privados"]); setMsg(null); }}>
                {PRIVADOS.map(([k, r]) => <option key={k} value={k}>{r}</option>)}
              </select></label>
            <label>Fuso<br /><input value={fuso ?? p.fuso} onChange={(e) => { setFuso(e.target.value); setMsg(null); }} /></label>
            <label>Dias para trás<br /><input inputMode="numeric" value={passado ?? String(p.janela_passado_dias)} onChange={(e) => { setPassado(e.target.value); setMsg(null); }} /></label>
            <label>Dias para frente<br /><input inputMode="numeric" value={futuro ?? String(p.janela_futuro_dias)} onChange={(e) => { setFuturo(e.target.value); setMsg(null); }} /></label>
            <button className="btn btn-primary" type="submit" disabled={ocupado}>Salvar ajustes</button>
            {msg && <p role="alert" style={{ margin: 0, flexBasis: "100%", color: "var(--danger)" }}>Erro: {msg}</p>}
          </form>
        </Bloco>
      )}
    </Painel>
  );
}

/** Cadastros › Agenda: quais contas e calendários a Gabi lê (só leitura). Títulos de compromisso nunca vão para o console. */
export function CadastrosAgenda() {
  const fontes = useApi<{ fontes: Fonte[] }>("/api/v1/agenda/fontes");
  const parametros = useApi<Parametros>("/api/v1/agenda/parametros");
  const acao = useAcao();
  if ([fontes, parametros].some((l) => l.estado === "erro" && l.erro?.status === 403)) return <Vazio frase="Só o dono configura a agenda." />;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <Fontes leitura={fontes} acao={acao} fuso={parametros.env?.dados.fuso} />
      <Ajustes leitura={parametros} acao={acao} />
    </div>
  );
}
