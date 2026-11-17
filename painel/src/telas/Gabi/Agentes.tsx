/** Gabi › Agentes: as chaves do MCP (ADR-036). Lista, emite, troca escopos, revoga, rotaciona e mostra as últimas chamadas.
 * A chave (segredo) aparece uma única vez, ao emitir ou rotacionar; fechar o aviso a descarta, e as receitas voltam a usar <SUA_CHAVE>.
 * Consome: GET/POST /api/v1/agentes, GET /agentes/conexao, PATCH /agentes/{id}/escopos, POST /agentes/{id}/revogar e /rotacionar, GET /agentes/{id}/chamadas. */
import { useState } from "react";
import { Bloco } from "../../componentes/Bloco";
import { Etiqueta } from "../../componentes/Etiqueta";
import { Vazio } from "../../componentes/Estados";
import { Painel } from "../../componentes/Painel";
import { api } from "../../lib/api";
import { dataCurta, horaDe } from "../../lib/formato";
import { Aviso, useAcao } from "../../lib/useAcao";
import { useApi } from "../../lib/useApi";
import { ReceitasAgentes } from "./ReceitasAgentes";

interface Agente { id: number; nome: string; escopos: string[]; criado_em: string; revogado_em: string | null; ativo: boolean; ultimo_uso: string | null; chamadas_7d: number }
interface Conexao { url: string; escopos_padrao: string[]; escopos_validos: string[] }
interface Chamada { quando: string; ferramenta: string; status: string }
interface Emitida { id: number; nome: string; escopos: string[]; chave: string }
type Agir = ReturnType<typeof useAcao>["agir"];
const ROTA = "/api/v1/agentes";
const ehHermes = (a: Agente) => a.nome.trim().toLowerCase() === "hermes";
const quando = (iso: string) => `${dataCurta(iso)}${horaDe(iso) ? ` ${horaDe(iso)}` : ""}`;

function Escopos({ validos, marcados, onChange }: { validos: string[]; marcados: string[]; onChange: (e: string[]) => void }) {
  return (
    <span className="fila" style={{ gap: "8px 16px" }}>
      {validos.map((e) => (
        <label key={e} className="opcao mono" style={{ fontSize: "var(--t-1)" }}>
          <input type="checkbox" checked={marcados.includes(e)} onChange={(ev) => onChange(ev.target.checked ? [...marcados, e] : marcados.filter((x) => x !== e))} />{e}</label>))}
    </span>
  );
}

function ChaveNova({ chave, fechar }: { chave: Emitida; fechar: () => void }) {
  const [copiada, setCopiada] = useState(false);
  const [falhou, setFalhou] = useState(false);
  const copiar = async () => { try { await navigator.clipboard.writeText(chave.chave); setCopiada(true); setFalhou(false); } catch { setFalhou(true); } };
  return (
    <div role="status" className="quadro" data-tom="conferir" style={{ flexDirection: "column", gap: 8 }}>
      <span className="fila"><Etiqueta tipo="conferir" texto="uma vez só" /><strong>Chave de "{chave.nome}"</strong></span>
      <p className="suave">Guarde agora: esta chave não aparece de novo.</p>
      <code className="chave">{chave.chave}</code>
      <span className="fila">
        <button className="btn btn-primary btn-sm" aria-label="Copiar chave" onClick={() => void copiar()}>{copiada ? "Copiada" : "Copiar"}</button>
        <button className="btn btn-sm" onClick={fechar}>Fechar</button>
      </span>
      {falhou && <span className="suave">Não consegui copiar; selecione o texto.</span>}
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
    <form onSubmit={(e) => { e.preventDefault(); void emitir(); }} className="folha pilha-curta" style={{ gap: 12 }}>
      <label className="campo" style={{ maxWidth: 320 }}>Nome do agente
        <input value={nome} maxLength={60} onChange={(e) => setNome(e.target.value)} /></label>
      <fieldset>
        <legend>Escopos da nova chave</legend>
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
  const [erroChamadas, setErroChamadas] = useState<string | null>(null);
  const chave = String(a.id);
  const hermes = ehHermes(a);
  const alternar = (qual: NonNullable<typeof aberto>) => setAberto(aberto === qual ? null : qual);
  const ver = async () => {
    if (aberto === "chamadas") return setAberto(null);
    setAberto("chamadas");
    setErroChamadas(null);
    try { setChamadas((await api.get<{ itens: Chamada[] }>(`${ROTA}/${a.id}/chamadas`)).dados.itens); }
    catch { setErroChamadas("Não consegui carregar as chamadas."); }
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
    <li className="linha-item" style={{ opacity: a.ativo ? 1 : 0.55 }}>
        <span className="pilha-curta" style={{ gap: 3 }}>
          <span className="fila"><strong className="linha-titulo">{a.nome}{!a.ativo && " (revogada)"}</strong>{hermes && a.ativo && <Etiqueta tipo="nota" texto="Telegram e WhatsApp" />}</span>
          <span className="miudo mono">{a.escopos.join(", ") || "sem escopos"}</span>
          <span className="miudo">
            {a.ultimo_uso ? `Último uso ${quando(a.ultimo_uso)}` : "nunca usada"} · {a.chamadas_7d} chamadas em 7 dias</span>
        </span>
        <span className="linha-acoes">
          <button className="btn btn-sm btn-ghost" aria-label={`Ver chamadas de ${a.nome}`} onClick={() => void ver()}>Ver chamadas</button>
          {a.ativo && <>
            <button className="btn btn-sm" aria-label={`Editar escopos de ${a.nome}`} disabled={ocupado} onClick={() => alternar("escopos")}>Editar escopos</button>
            <button className="btn btn-sm" aria-label={`Rotacionar ${a.nome}`} disabled={ocupado} onClick={() => alternar("rotacionar")}>Rotacionar</button>
            <button className="btn btn-sm btn-ghost btn-perigo" aria-label={`Revogar ${a.nome}`} disabled={ocupado} onClick={() => alternar("revogar")}>Revogar</button>
          </>}
        </span>
      {aberto === "escopos" && (
        <span className="linha-painel">
          <Escopos validos={conexao.escopos_validos} marcados={novos} onChange={setNovos} />
          <span className="fila">
            <button className="btn btn-primary btn-sm" disabled={ocupado} aria-label={`Salvar escopos de ${a.nome}`}
              onClick={() => agir(chave, () => api.patch(`${ROTA}/${a.id}/escopos`, { escopos: novos }), "Escopos salvos.", recarregar).then((ok) => ok && setAberto(null))}>Salvar escopos</button>
            <button className="btn btn-sm" onClick={() => { setNovos(a.escopos); setAberto(null); }}>Cancelar</button>
          </span>
        </span>)}
      {aberto === "revogar" && (
        <div role="alert" className="linha-painel">
          <p>{aviso("revogar")} Não há como desfazer; para voltar, emita outra chave.</p>
          <span className="fila">
            <button className="btn btn-primary btn-sm" disabled={ocupado} aria-label={`Confirmar revogar ${a.nome}`}
              onClick={() => agir(chave, () => api.post(`${ROTA}/${a.id}/revogar`), "Chave revogada.", recarregar).then((ok) => ok && setAberto(null))}>Confirmar</button>
            <button className="btn btn-sm" onClick={() => setAberto(null)}>Cancelar</button>
          </span>
        </div>)}
      {aberto === "rotacionar" && (
        <div role="alert" className="linha-painel">
          <p>{aviso("rotacionar")} A chave antiga é revogada na hora e a nova aparece uma só vez.</p>
          <span className="fila">
            <button className="btn btn-primary btn-sm" disabled={ocupado} aria-label={`Confirmar rotacionar ${a.nome}`} onClick={() => void rotacionar()}>Confirmar</button>
            <button className="btn btn-sm" onClick={() => setAberto(null)}>Cancelar</button>
          </span>
        </div>)}
      {aberto === "chamadas" && erroChamadas && <span role="alert" className="erro-linha" style={{ gridColumn: "1 / -1" }}>{erroChamadas}</span>}
      {aberto === "chamadas" && !chamadas && !erroChamadas && <span className="esqueleto" style={{ gridColumn: "1 / -1" }}><span className="esqueleto-linha" style={{ width: "50%" }} /></span>}
      {aberto === "chamadas" && chamadas && <div style={{ gridColumn: "1 / -1" }}>{chamadas.length === 0 ? <Vazio frase="Nenhuma chamada ainda." /> : (
        <ul className="chamadas">
          {chamadas.map((c, i) => <li key={i} className="mono">{quando(c.quando)} · {c.ferramenta} · {c.status}</li>)}
        </ul>)}</div>}
      {erro && <span style={{ gridColumn: "1 / -1" }}><Aviso erro={erro} /></span>}
    </li>
  );
}

export function Agentes() {
  const leitura = useApi<{ itens: Agente[] }>(ROTA);
  const conexao = useApi<Conexao>(`${ROTA}/conexao`);
  const { ocupado, erros, agir } = useAcao();
  const [nova, setNova] = useState<Emitida | null>(null); // única fonte da chave recente: some ao fechar o aviso
  const emitida = (e: Emitida) => { setNova(e); void leitura.recarregar(); };
  const fechar = () => setNova(null);
  const bruto = conexao.env?.dados;
  const cx = bruto && Array.isArray(bruto.escopos_validos) ? bruto : undefined; // resposta incompleta não derruba a tela
  return (
    <Painel leitura={leitura} arquivo="agentes">
      {(dados) => (
        <div className="pilha" style={{ gap: 40, maxWidth: 1040 }}>
          <Bloco titulo="Chaves dos agentes" nota="Chaves com que os seus agentes (Hermes e outros) acessam a Gabi pelo MCP.">
            {nova && <ChaveNova key={nova.id} chave={nova} fechar={fechar} />}
            {!dados.itens?.length ? <Vazio frase="Nenhuma chave emitida. Emita a primeira abaixo." /> : (
              <ul className="pauta">
                {cx && dados.itens.map((a) => <Linha key={a.id} a={a} conexao={cx} agir={agir} ocupado={ocupado} erro={erros[String(a.id)]} recarregar={leitura.recarregar} emitida={emitida} />)}
              </ul>)}
          </Bloco>
          {cx && <Bloco titulo="Nova chave" nota="a chave aparece uma única vez, logo depois de emitida"><Nova conexao={cx} agir={agir} ocupado={ocupado} erro={erros.nova} emitida={emitida} /></Bloco>}
          {cx && <ReceitasAgentes url={cx.url} chave={nova?.chave ?? null} />}
        </div>)}
    </Painel>
  );
}
