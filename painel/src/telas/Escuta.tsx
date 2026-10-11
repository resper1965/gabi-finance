import { useEffect, useRef, useState } from "react";
import { Bloco } from "../componentes/Bloco";
import { Painel } from "../componentes/Painel";
import { Vazio } from "../componentes/Estados";
import { api } from "../lib/api";
import { useToast } from "../lib/toast";
import { useApi, type Leitura } from "../lib/useApi";

interface Remetente { numero: string; nome: string | null; qtd: number }
interface Aprovado { pessoa_id: string; nome: string; numero: string | null; papel: string | null }
interface Grupo { id_grupo: string; nome: string; aprovado: boolean }
interface Parametros { modo: "registro" | "ativo"; palavras_risco: string[]; horas_sem_receber: number; anexo_max_mb: number }

const PAPEIS: [string, string][] = [["familia", "Família"], ["prestador", "Prestador"], ["cobranca", "Cobrança"]];
const rotuloPapel = (p: string | null) => PAPEIS.find(([k]) => k === p)?.[1] ?? "—";
const suave = { color: "var(--ink2)" } as const;
const linha = { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", justifyContent: "space-between", borderTop: "1px solid var(--color-divider)", padding: "8px 0" } as const;
const lista = { listStyle: "none", margin: 0, padding: 0 } as const;

type Acao = ReturnType<typeof useAcao>;

/** Executa uma ação sob trava (uma por vez na tela), avisa o resultado e espera a releitura; em erro mantém a tela como está e guarda a mensagem na chave (linha) que falhou. */
function useAcao() {
  const avisar = useToast();
  const trava = useRef(false);
  const [ocupado, setOcupado] = useState(false);
  const [erros, setErros] = useState<Record<string, string>>({});
  const agir = async (chave: string, fn: () => Promise<unknown>, ok: string, recarregar?: () => Promise<void>) => {
    if (trava.current) return false;
    trava.current = true; setOcupado(true);
    setErros((e) => { const { [chave]: _, ...resto } = e; return resto; });
    try { await fn(); avisar(ok); await recarregar?.(); return true; }
    catch (e) { const m = (e as Error).message; setErros((x) => ({ ...x, [chave]: m })); avisar(m); return false; }
    finally { trava.current = false; setOcupado(false); }
  };
  return { ocupado, erros, agir };
}
const Aviso = ({ erro, id }: { erro?: string; id?: string }) => (erro ? <p role="alert" id={id} style={{ margin: 0, color: "var(--danger)", flexBasis: "100%" }}>Erro: {erro}</p> : null);

function Fila({ leitura, acao }: { leitura: Leitura<{ fila: Remetente[]; aprovados: Aprovado[] }>; acao: Acao }) {
  const { ocupado, erros, agir } = acao;
  const [escolhendo, setEscolhendo] = useState<string | null>(null);
  const primeiro = useRef<HTMLButtonElement>(null);
  const aprovarRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const voltar = useRef<string | null>(null);
  useEffect(() => {
    if (escolhendo) primeiro.current?.focus();
    else if (voltar.current) { aprovarRefs.current[voltar.current]?.focus(); voltar.current = null; }
  }, [escolhendo]);
  return (
    <Painel leitura={leitura} arquivo="escuta-remetentes">
      {(d) => (
        <>
          <Bloco titulo={`Novos remetentes · ${d.fila.length}`} nota="Quem escreveu e a Gabi ainda não conhece.">
            {d.fila.length === 0 ? <Vazio frase="Nenhum remetente novo na fila." /> : (
              <ul style={lista}>
                {d.fila.map((r) => {
                  const quem = r.nome ?? r.numero;
                  return (
                    <li key={r.numero} style={linha}>
                      <span><strong>{r.nome ?? r.numero}</strong>{r.nome && <span style={suave}> · {r.numero}</span>} <span style={suave}>· {r.qtd} {r.qtd === 1 ? "mensagem" : "mensagens"}</span></span>
                      <span style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                        {escolhendo === r.numero ? (
                          <>
                            <span style={suave}>Aprovar como:</span>
                            {PAPEIS.map(([papel, rotulo], i) => (
                              <button key={papel} ref={i === 0 ? primeiro : undefined} className="btn btn-primary" disabled={ocupado} aria-label={`Aprovar como ${rotulo}: ${quem}`}
                                onClick={async () => { if (await agir(r.numero, () => api.post(`/api/v1/escuta/remetentes/${encodeURIComponent(r.numero)}/aprovar`, { papel }), "Remetente aprovado.", leitura.recarregar)) setEscolhendo(null); }}>{rotulo}</button>))}
                            <button className="btn btn-secondary" disabled={ocupado} onClick={() => { voltar.current = r.numero; setEscolhendo(null); }}>Cancelar</button>
                          </>
                        ) : (
                          <>
                            <button ref={(el) => { aprovarRefs.current[r.numero] = el; }} className="btn btn-primary" disabled={ocupado} aria-label={`Aprovar ${quem}`} onClick={() => setEscolhendo(r.numero)}>Aprovar</button>
                            <button className="btn btn-secondary" disabled={ocupado} aria-label={`Ignorar ${quem}`} onClick={() => agir(r.numero, () => api.post(`/api/v1/escuta/remetentes/${encodeURIComponent(r.numero)}/ignorar`), "Remetente ignorado.", leitura.recarregar)}>Ignorar</button>
                            <button className="btn btn-secondary" disabled={ocupado} aria-label={`Bloquear ${quem}`} onClick={() => agir(r.numero, () => api.post(`/api/v1/escuta/remetentes/${encodeURIComponent(r.numero)}/bloquear`), "Remetente bloqueado.", leitura.recarregar)}>Bloquear</button>
                          </>
                        )}
                      </span>
                      <Aviso erro={erros[r.numero]} />
                    </li>);
                })}
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

function Grupos({ leitura, acao }: { leitura: Leitura<{ grupos: Grupo[] }>; acao: Acao }) {
  const { ocupado, erros, agir } = acao;
  return (
    <Painel leitura={leitura} arquivo="escuta-grupos">
      {(d) => (
        <Bloco titulo="Grupos">
          {d.grupos.length === 0 ? <Vazio frase="Nenhum grupo visto ainda." /> : (
            <ul style={lista}>
              {d.grupos.map((g) => (
                <li key={g.id_grupo} style={linha}>
                  <strong>{g.nome}</strong>
                  {g.aprovado ? <span style={suave}>Aprovado</span>
                    : <button className="btn btn-primary" disabled={ocupado} aria-label={`Aprovar grupo ${g.nome}`} onClick={() => agir(`g:${g.id_grupo}`, () => api.post(`/api/v1/escuta/grupos/${encodeURIComponent(g.id_grupo)}/aprovar`), "Grupo aprovado.", leitura.recarregar)}>Aprovar</button>}
                  <Aviso erro={erros[`g:${g.id_grupo}`]} />
                </li>))}
            </ul>)}
        </Bloco>
      )}
    </Painel>
  );
}

/** Regras da palavra de risco, iguais às do servidor: aparar, não vazia, até 60 caracteres, até 200 itens, sem repetir (maiúsculas não contam). */
function validarPalavra(lista: string[], texto: string): { palavra: string } | { erro: string } {
  const palavra = texto.trim();
  if (!palavra) return { erro: "A palavra está vazia." };
  if (palavra.length > 60) return { erro: "No máximo 60 caracteres." };
  if (lista.some((w) => w.toLowerCase() === palavra.toLowerCase())) return { erro: "Essa palavra já existe." };
  if (lista.length >= 200) return { erro: "Limite de 200 palavras." };
  return { palavra };
}
const inteiro = (v: string, min: number, max: number) => (/^\d+$/.test(v.trim()) && Number(v) >= min && Number(v) <= max ? Number(v) : null);

function Ajustes({ leitura, acao }: { leitura: Leitura<Parametros>; acao: Acao }) {
  const { ocupado, erros, agir } = acao;
  const [salvo, setSalvo] = useState<Parametros | null>(null); // resposta do último PUT: a lista mais recente do servidor
  const [confirmando, setConfirmando] = useState(false);
  const [nova, setNova] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [horas, setHoras] = useState<string | null>(null);
  const [mb, setMb] = useState<string | null>(null);
  const [msgLimites, setMsgLimites] = useState<string | null>(null);
  const confirmar = useRef<HTMLButtonElement>(null);
  const ativo = useRef<HTMLButtonElement>(null);
  const voltar = useRef(false);
  useEffect(() => {
    if (confirmando) confirmar.current?.focus();
    else if (voltar.current) { ativo.current?.focus(); voltar.current = false; }
  }, [confirmando]);
  const gravar = async (corpo: Partial<Parametros>, ok: string) => {
    const deu = await agir("geral", async () => { setSalvo((await api.put<Parametros>("/api/v1/escuta/parametros", corpo)).dados); }, ok, leitura.recarregar);
    if (deu) setSalvo(null); // a releitura terminou: o servidor prevalece sobre a resposta do PUT
    return deu;
  };
  return (
    <Painel leitura={leitura} arquivo="escuta-parametros">
      {(servidor) => {
        const p = salvo ?? servidor;
        return (
          <Bloco titulo="Ajustes da escuta">
            <Aviso erro={erros.geral} />
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }} role="group" aria-label="Modo">
              <span>Modo:</span>
              {(["registro", "ativo"] as const).map((m) => (
                <button key={m} ref={m === "ativo" ? ativo : undefined} className={`btn ${p.modo === m ? "btn-primary" : "btn-secondary"}`} aria-pressed={p.modo === m} disabled={ocupado}
                  onClick={() => { if (m === p.modo) setConfirmando(false); else if (m === "ativo") setConfirmando(true); else { setConfirmando(false); gravar({ modo: "registro" }, "Modo registro."); } }}>{m === "registro" ? "Registro" : "Ativo"}</button>))}
            </div>
            {confirmando && (
              <div role="alert" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <p style={{ margin: 0 }}>Atenção: em registro a escuta só registra; em ativo ela cria pedidos e avisa.</p>
                <span style={{ display: "flex", gap: 8 }}>
                  <button ref={confirmar} className="btn btn-primary" disabled={ocupado} onClick={async () => { if (await gravar({ modo: "ativo" }, "Modo ativo ligado.")) setConfirmando(false); }}>Confirmar modo ativo</button>
                  <button className="btn btn-secondary" disabled={ocupado} onClick={() => { voltar.current = true; setConfirmando(false); }}>Cancelar</button>
                </span>
              </div>)}
            <div>
              <div style={{ marginBottom: 6 }}>Palavras de risco</div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
                {p.palavras_risco.length === 0 && <span style={suave}>Nenhuma palavra ainda.</span>}
                {p.palavras_risco.map((w) => (
                  <span key={w} style={{ border: "1px solid var(--color-divider)", padding: "2px 8px", display: "inline-flex", gap: 6, alignItems: "center" }}>
                    {w}<button className="btn btn-secondary" disabled={ocupado} aria-label={`Remover ${w}`} style={{ padding: "0 6px" }} onClick={() => gravar({ palavras_risco: p.palavras_risco.filter((x) => x !== w) }, "Palavra removida.")}>×</button>
                  </span>))}
              </div>
              <form style={{ display: "flex", gap: 8, flexWrap: "wrap" }} onSubmit={async (e) => {
                e.preventDefault();
                if (ocupado) return;
                const r = validarPalavra(p.palavras_risco, nova);
                if ("erro" in r) { setMsg(r.erro); return; }
                setMsg(null);
                if (await gravar({ palavras_risco: [...p.palavras_risco, r.palavra] }, "Palavra adicionada.")) setNova("");
              }}>
                <input aria-label="Nova palavra de risco" value={nova} onChange={(e) => { setNova(e.target.value); setMsg(null); }} />
                <button className="btn btn-secondary" type="submit" disabled={ocupado} aria-label="Adicionar palavra">Adicionar</button>
                {msg && <p role="alert" style={{ margin: 0, flexBasis: "100%", color: "var(--danger)" }}>Erro: {msg}</p>}
              </form>
            </div>
            <form style={{ display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }} onSubmit={async (e) => {
              e.preventDefault();
              if (ocupado) return;
              const corpo: Partial<Parametros> = {};
              if (horas !== null) {
                const h = inteiro(horas, 1, 168);
                if (h === null) { setMsgLimites("Horas sem receber: informe um inteiro de 1 a 168."); return; }
                corpo.horas_sem_receber = h;
              }
              if (mb !== null) {
                const m = inteiro(mb, 1, 100);
                if (m === null) { setMsgLimites("Tamanho de anexo: informe um inteiro de 1 a 100."); return; }
                corpo.anexo_max_mb = m;
              }
              setMsgLimites(null);
              if (Object.keys(corpo).length && await gravar(corpo, "Limites salvos.")) { setHoras(null); setMb(null); }
            }}>
              <label>Horas sem receber<br /><input inputMode="numeric" value={horas ?? String(p.horas_sem_receber)} onChange={(e) => { setHoras(e.target.value); setMsgLimites(null); }} /></label>
              <label>Tamanho máximo de anexo (MB)<br /><input inputMode="numeric" value={mb ?? String(p.anexo_max_mb)} onChange={(e) => { setMb(e.target.value); setMsgLimites(null); }} /></label>
              <button className="btn btn-primary" type="submit" disabled={ocupado}>Salvar limites</button>
              {msgLimites && <p role="alert" style={{ margin: 0, flexBasis: "100%", color: "var(--danger)" }}>Erro: {msgLimites}</p>}
            </form>
          </Bloco>
        );
      }}
    </Painel>
  );
}

/** Escuta: quem a Gabi escuta no WhatsApp. Número, nome e palavras de risco são dados do servidor; nada vai para o console. */
export function Escuta() {
  const remetentes = useApi<{ fila: Remetente[]; aprovados: Aprovado[] }>("/api/v1/escuta/remetentes");
  const grupos = useApi<{ grupos: Grupo[] }>("/api/v1/escuta/grupos");
  const parametros = useApi<Parametros>("/api/v1/escuta/parametros");
  const acao = useAcao();
  if ([remetentes, grupos, parametros].some((l) => l.estado === "erro" && l.erro?.status === 403)) return <Vazio frase="Só o dono acessa a escuta." />;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <Fila leitura={remetentes} acao={acao} />
      <Grupos leitura={grupos} acao={acao} />
      <Ajustes leitura={parametros} acao={acao} />
    </div>
  );
}
