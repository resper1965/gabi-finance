/** Gabi › Agentes: as chaves do MCP (ADR-036). Lista, emite, troca escopos, revoga, rotaciona e mostra as últimas chamadas.
 * A chave (segredo) aparece uma única vez, ao emitir ou rotacionar; fechar o aviso a descarta (`chaveRecente`, que a Task 4 usa nas receitas).
 * Consome: GET/POST /api/v1/agentes, GET /agentes/conexao, PATCH /agentes/{id}/escopos, POST /agentes/{id}/revogar e /rotacionar, GET /agentes/{id}/chamadas. */
import { useState } from "react";
import { Bloco } from "../../componentes/Bloco";
import { Vazio } from "../../componentes/Estados";
import { Painel } from "../../componentes/Painel";
import { api } from "../../lib/api";
import { dataCurta, horaDe } from "../../lib/formato";
import { Aviso, useAcao } from "../../lib/useAcao";
import { useApi } from "../../lib/useApi";

interface Agente { id: number; nome: string; escopos: string[]; criado_em: string; revogado_em: string | null; ativo: boolean; ultimo_uso: string | null; chamadas_7d: number }
interface Conexao { url: string; escopos_padrao: string[]; escopos_validos: string[] }
interface Chamada { quando: string; ferramenta: string; status: string }
interface Emitida { id: number; nome: string; escopos: string[]; chave: string }
export interface ChaveRecente { id: number; valor: string }
type Agir = ReturnType<typeof useAcao>["agir"];
const ROTA = "/api/v1/agentes";
const suave = { color: "var(--ink2)" } as const;
const ehHermes = (a: Agente) => a.nome.trim().toLowerCase() === "hermes";
const quando = (iso: string) => `${dataCurta(iso)}${horaDe(iso) ? ` ${horaDe(iso)}` : ""}`;

function Escopos({ validos, marcados, onChange }: { validos: string[]; marcados: string[]; onChange: (e: string[]) => void }) {
  return (
    <span style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
      {validos.map((e) => (
        <label key={e} style={{ display: "flex", gap: 4, alignItems: "center", fontSize: 13 }}>
          <input type="checkbox" checked={marcados.includes(e)} onChange={(ev) => onChange(ev.target.checked ? [...marcados, e] : marcados.filter((x) => x !== e))} />{e}</label>))}
    </span>
  );
}

function ChaveNova({ chave, fechar }: { chave: Emitida; fechar: () => void }) {
  const [copiada, setCopiada] = useState(false);
  const copiar = async () => { try { await navigator.clipboard.writeText(chave.chave); setCopiada(true); } catch { /* o texto segue selecionável */ } };
  return (
    <div role="status" style={{ display: "flex", flexDirection: "column", gap: 8, border: "1px solid var(--color-divider)", padding: 12 }}>
      <strong>Chave de "{chave.nome}"</strong>
      <p style={{ margin: 0, ...suave }}>Guarde agora: esta chave não aparece de novo.</p>
      <code style={{ userSelect: "all", wordBreak: "break-all" }}>{chave.chave}</code>
      <span style={{ display: "flex", gap: 8 }}>
        <button className="btn btn-primary" onClick={() => void copiar()}>{copiada ? "Copiada" : "Copiar"}</button>
        <button className="btn btn-secondary" onClick={fechar}>Fechar</button>
      </span>
    </div>
  );
}

function Nova({ conexao, agir, ocupado, erro, emitida }: { conexao: Conexao; agir: Agir; ocupado: boolean; erro?: string; emitida: (e: Emitida) => void }) {
  const [nome, setNome] = useState("");
  const [escopos, setEscopos] = useState<string[]>(conexao.escopos_padrao);
  const emitir = async () => {
    if (!nome.trim()) return;
    let nova: Emitida | null = null;
    const ok = await agir("nova", async () => { nova = (await api.post<Emitida>(ROTA, { nome: nome.trim(), escopos })).dados; }, "Chave emitida.");
    if (ok && nova) { emitida(nova); setNome(""); setEscopos(conexao.escopos_padrao); }
  };
  return (
    <form onSubmit={(e) => { e.preventDefault(); void emitir(); }} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <label style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 13, maxWidth: 320 }}>Nome do agente
        <input value={nome} maxLength={60} onChange={(e) => setNome(e.target.value)} /></label>
      <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
        <legend style={{ fontSize: 13, ...suave }}>Escopos da nova chave</legend>
        <Escopos validos={conexao.escopos_validos} marcados={escopos} onChange={setEscopos} />
      </fieldset>
      <span><button type="submit" className="btn btn-primary" disabled={ocupado || !nome.trim()}>Emitir chave</button></span>
      <Aviso erro={erro} />
    </form>
  );
}

function Linha({ a, conexao, agir, ocupado, erro, recarregar, emitida }: { a: Agente; conexao: Conexao; agir: Agir; ocupado: boolean; erro?: string; recarregar: () => Promise<void>; emitida: (e: Emitida) => void }) {
  const [aberto, setAberto] = useState<"escopos" | "revogar" | "rotacionar" | "chamadas" | null>(null);
  const [novos, setNovos] = useState<string[]>(a.escopos);
  const [chamadas, setChamadas] = useState<Chamada[] | null>(null);
  const chave = String(a.id);
  const hermes = ehHermes(a);
  const alternar = (qual: NonNullable<typeof aberto>) => setAberto(aberto === qual ? null : qual);
  const ver = async () => {
    if (aberto === "chamadas") return setAberto(null);
    setAberto("chamadas");
    await agir(chave, async () => { setChamadas((await api.get<{ itens: Chamada[] }>(`${ROTA}/${a.id}/chamadas`)).dados.itens); }, "Chamadas carregadas.");
  };
  const rotacionar = async () => {
    let nova: Emitida | null = null;
    const ok = await agir(chave, async () => { nova = (await api.post<Emitida>(`${ROTA}/${a.id}/rotacionar`)).dados; }, "Chave rotacionada.", recarregar);
    if (ok && nova) { emitida(nova); setAberto(null); }
  };
  const aviso = (acao: string) => hermes
    ? `Atenção: esta é a chave do Hermes. Ele a usa no Telegram e no WhatsApp; ao ${acao}, os dois param de funcionar até a chave nova ser colocada no Hermes.`
    : `Ao ${acao} "${a.nome}", quem usa a chave atual perde o acesso.`;
  return (
    <li style={{ display: "flex", flexDirection: "column", gap: 6, borderTop: "1px solid var(--color-divider)", padding: "10px 0", opacity: a.ativo ? 1 : 0.55 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", justifyContent: "space-between" }}>
        <span style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 0 }}>
          <strong>{a.nome}{!a.ativo && " (revogada)"}</strong>
          <span style={{ fontSize: 12.5, ...suave }}>{a.escopos.join(", ") || "sem escopos"}</span>
          <span style={{ fontSize: 12.5, ...suave }}>
            {a.ultimo_uso ? `Último uso ${quando(a.ultimo_uso)}` : "nunca usada"} · {a.chamadas_7d} chamadas em 7 dias</span>
        </span>
        <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="btn btn-secondary" style={{ minHeight: 32 }} aria-label={`Ver chamadas de ${a.nome}`} disabled={ocupado} onClick={() => void ver()}>Ver chamadas</button>
          {a.ativo && <>
            <button className="btn btn-secondary" style={{ minHeight: 32 }} aria-label={`Editar escopos de ${a.nome}`} disabled={ocupado} onClick={() => alternar("escopos")}>Editar escopos</button>
            <button className="btn btn-secondary" style={{ minHeight: 32 }} aria-label={`Rotacionar ${a.nome}`} disabled={ocupado} onClick={() => alternar("rotacionar")}>Rotacionar</button>
            <button className="btn btn-secondary" style={{ minHeight: 32 }} aria-label={`Revogar ${a.nome}`} disabled={ocupado} onClick={() => alternar("revogar")}>Revogar</button>
          </>}
        </span>
      </div>
      {aberto === "escopos" && (
        <span style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <Escopos validos={conexao.escopos_validos} marcados={novos} onChange={setNovos} />
          <span style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary" disabled={ocupado} aria-label={`Salvar escopos de ${a.nome}`}
              onClick={() => agir(chave, () => api.patch(`${ROTA}/${a.id}/escopos`, { escopos: novos }), "Escopos salvos.", recarregar).then((ok) => ok && setAberto(null))}>Salvar escopos</button>
            <button className="btn btn-secondary" onClick={() => setAberto(null)}>Cancelar</button>
          </span>
        </span>)}
      {aberto === "revogar" && (
        <div role="alert" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <p style={{ margin: 0 }}>{aviso("revogar")} Não há como desfazer; para voltar, emita outra chave.</p>
          <span style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary" disabled={ocupado} aria-label={`Confirmar revogar ${a.nome}`}
              onClick={() => agir(chave, () => api.post(`${ROTA}/${a.id}/revogar`), "Chave revogada.", recarregar).then((ok) => ok && setAberto(null))}>Confirmar</button>
            <button className="btn btn-secondary" onClick={() => setAberto(null)}>Cancelar</button>
          </span>
        </div>)}
      {aberto === "rotacionar" && (
        <div role="alert" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <p style={{ margin: 0 }}>{aviso("rotacionar")} A chave antiga é revogada na hora e a nova aparece uma só vez.</p>
          <span style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary" disabled={ocupado} aria-label={`Confirmar rotacionar ${a.nome}`} onClick={() => void rotacionar()}>Confirmar</button>
            <button className="btn btn-secondary" onClick={() => setAberto(null)}>Cancelar</button>
          </span>
        </div>)}
      {aberto === "chamadas" && chamadas && (chamadas.length === 0 ? <Vazio frase="Nenhuma chamada ainda." /> : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0, fontSize: 13 }}>
          {chamadas.map((c, i) => <li key={i}>{quando(c.quando)} · {c.ferramenta} · {c.status}</li>)}
        </ul>))}
      <Aviso erro={erro} />
    </li>
  );
}

/** `aoMudarChave` recebe a chave recém-emitida (ou null ao fechar o aviso): é o ponto de entrada das receitas de conexão (Task 4). */
export function Agentes({ aoMudarChave }: { aoMudarChave?: (c: ChaveRecente | null) => void } = {}) {
  const leitura = useApi<{ itens: Agente[] }>(ROTA);
  const conexao = useApi<Conexao>(`${ROTA}/conexao`);
  const { ocupado, erros, agir } = useAcao();
  const [nova, setNova] = useState<Emitida | null>(null);
  const [chaveRecente, setChaveRecente] = useState<ChaveRecente | null>(null);
  const mudar = (c: ChaveRecente | null) => { setChaveRecente(c); aoMudarChave?.(c); };
  const emitida = (e: Emitida) => { setNova(e); mudar({ id: e.id, valor: e.chave }); void leitura.recarregar(); };
  const fechar = () => { setNova(null); mudar(null); };
  void chaveRecente;
  const cx = conexao.env?.dados;
  return (
    <Painel leitura={leitura} arquivo="agentes">
      {(dados) => (
        <Bloco titulo="Agentes" nota="Chaves com que os seus agentes (Hermes e outros) acessam a Gabi pelo MCP.">
          {nova && <ChaveNova chave={nova} fechar={fechar} />}
          {cx && <Nova conexao={cx} agir={agir} ocupado={ocupado} erro={erros.nova} emitida={emitida} />}
          {dados.itens.length === 0 ? <Vazio frase="Nenhuma chave emitida." /> : (
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {cx && dados.itens.map((a) => <Linha key={a.id} a={a} conexao={cx} agir={agir} ocupado={ocupado} erro={erros[String(a.id)]} recarregar={leitura.recarregar} emitida={emitida} />)}
            </ul>)}
        </Bloco>)}
    </Painel>
  );
}
