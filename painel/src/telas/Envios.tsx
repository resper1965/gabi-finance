/** Envios: o que o Hermes propôs (evento na agenda, mensagem no Teams) e espera o seu OK para sair.
 * Consome: GET /api/v1/envios (pendente, decididas), POST /api/v1/envios/{id}/enviar e /recusar. */
import { useState, type ReactNode } from "react";
import { Bloco } from "../componentes/Bloco";
import { Painel } from "../componentes/Painel";
import { Vazio } from "../componentes/Estados";
import { api } from "../lib/api";
import { Aviso, useAcao } from "../lib/useAcao";
import { useApi } from "../lib/useApi";

interface Evento { conta: string; provedor: string; titulo: string; inicio_utc: string; fim_utc: string; fuso: string; convidados: string[]; descricao: string; online: boolean }
/** `tipo` só nas propostas novas (as antigas não o têm e ficam sem aviso). */
interface Chat { conta: string; chat_id: string; destino_nome: string; tipo?: "um_a_um" | "grupo"; texto: string }
interface Canal { conta: string; equipe_id: string; canal_id: string; equipe_nome: string; canal_nome: string; texto: string }
interface ConviteResposta { conta: string; titulo: string; inicio_utc: string; fim_utc: string; organizador_nome: string; resposta: "aceitar" | "talvez" | "recusar"; conflita_com: string[] }
interface Envio {
  id: number; tipo: "evento" | "teams_chat" | "teams_canal" | "convite_resposta"; conta: string; conteudo: Evento & Chat & Canal & ConviteResposta; hash: string;
  estado: string; motivo: string | null; criada_em: string; vence_em: string | null; decidida_em: string | null; enviada_em: string | null;
}
interface Fila { itens: Envio[]; escrita: "ligado" | "desligado" }
interface Convite { evento_id: number; conta: string; titulo: string; inicio_utc: string; fim_utc: string; organizador_nome: string; conflita_com: string[]; proposta_id: number | null }
type Resposta = "aceitar" | "talvez" | "recusar";
interface Resultado { id: number; estado: string; motivo?: string }

const ROTA = "/api/v1/envios";
const FUSO = "America/Sao_Paulo";
const suave = { color: "var(--ink2)" } as const;
const linha = { display: "flex", gap: 8, alignItems: "flex-start", flexWrap: "wrap", justifyContent: "space-between", borderTop: "1px solid var(--color-divider)", padding: "10px 0" } as const;
const lista = { listStyle: "none", margin: 0, padding: 0 } as const;
const TIPOS = { evento: "Evento na agenda", teams_chat: "Teams (conversa)", teams_canal: "Teams (canal)", convite_resposta: "Responder convite" } as const;

const f = (o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO, hour12: false, ...o });
const DIA = f({ weekday: "short", day: "2-digit", month: "2-digit" });
const HORA = f({ hour: "2-digit", minute: "2-digit" });
const partes = (fmt: Intl.DateTimeFormat, iso: string) => Object.fromEntries(fmt.formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
/** "qui 22/10" no horário de Brasília. */
const dia = (iso: string) => { const p = partes(DIA, iso); return `${p.weekday.replace(".", "")} ${p.day}/${p.month}`; };
const hora = (iso: string) => { const p = partes(HORA, iso); return `${p.hour}:${p.minute}`; };
/** "qui 22/10 15:00–16:00" (com as duas datas se o fim cair em outro dia). */
export function periodo(ini: string, fim: string): string {
  return dia(ini) === dia(fim) ? `${dia(ini)} ${hora(ini)}–${hora(fim)}` : `${dia(ini)} ${hora(ini)} – ${dia(fim)} ${hora(fim)}`;
}
const RESPOSTAS: Record<Resposta, string> = { aceitar: "Aceitar", talvez: "Talvez", recusar: "Recusar" };
const conflito = (l: string[]) => (l.length ? `Conflita com ${l.join(", ")}` : "Sem conflito");
const quando = (iso: string) => `${dia(iso)} ${hora(iso)}`;

function Corpo({ e }: { e: Envio }) {
  const c = e.conteudo;
  if (e.tipo === "evento") {
    return (
      <>
        <strong>{c.titulo}</strong><br />
        <span>{periodo(c.inicio_utc, c.fim_utc)}</span>{c.online && <span style={suave}> · online</span>}<br />
        <span style={suave}>Convidados:</span> <span>{c.convidados.join(", ")}</span>
        {c.descricao && <p style={{ margin: "4px 0 0", whiteSpace: "pre-wrap" }}>{c.descricao}</p>}
      </>);
  }
  if (e.tipo === "convite_resposta") {
    return (
      <>
        <strong>{c.titulo}</strong><br />
        <span>{periodo(c.inicio_utc, c.fim_utc)}</span>{c.organizador_nome && <span style={suave}> · de {c.organizador_nome}</span>}<br />
        <span style={suave}>Resposta:</span> <span>{RESPOSTAS[c.resposta]}</span><br />
        <span style={suave}>{conflito(c.conflita_com)}</span>
      </>);
  }
  // "chat com Fulano" pode ser um grupo (Fulano foi quem escreveu por último): o dono precisa ver isso antes de enviar
  const destino = e.tipo === "teams_chat" ? `${c.destino_nome}${c.tipo === "grupo" ? " (grupo)" : ""}` : `${c.equipe_nome} › ${c.canal_nome}`;
  return (
    <>
      <strong>{destino}</strong>
      <p style={{ margin: "4px 0 0", whiteSpace: "pre-wrap" }}>{c.texto}</p>
    </>);
}

function Cartao({ e, children }: { e: Envio; children?: ReactNode }) {
  return (
    <li style={linha}>
      <span style={{ flex: "1 1 320px", minWidth: 0 }}>
        <span style={suave}>{TIPOS[e.tipo]} · {e.conta}</span><br />
        <Corpo e={e} />
        {e.estado === "pendente"
          ? (e.vence_em && <><br /><span style={suave}>vence {quando(e.vence_em)}</span></>)
          : <><br /><span style={suave}>{e.estado}{e.motivo ? ` · ${e.motivo}` : ""}{e.decidida_em ? ` · ${quando(e.decidida_em)}` : ""}</span></>}
      </span>
      {children}
    </li>);
}

/** Convites de agenda recebidos: os botões só criam a proposta; quem manda é o Enviar de "Esperando seu OK". */
function Convites({ aoMudar }: { aoMudar: () => Promise<void> }) {
  const { ocupado, erros, agir } = useAcao();
  const lei = useApi<{ itens: Convite[] }>(`${ROTA}/convites`);
  const itens = lei.env?.dados.itens ?? [];
  if (itens.length === 0) return null;
  const propor = async (c: Convite, resposta: Resposta) => {
    const recarregar = async () => { await Promise.all([lei.recarregar(), aoMudar()]); };
    const ok = await agir(`convite${c.evento_id}`, () => api.post(`${ROTA}/convites/${c.evento_id}/propor`, { conta: c.conta, resposta }), "Proposta criada: falta o seu OK.", recarregar);
    if (!ok) await recarregar();
  };
  return (
    <Bloco titulo={`Convites recebidos · ${itens.length}`} nota="Responder só cria uma proposta; nada sai antes de você clicar em Enviar.">
      <ul style={lista}>
        {itens.map((c) => (
          <li key={`${c.conta}${c.evento_id}`} style={linha}>
            <span style={{ flex: "1 1 320px", minWidth: 0 }}>
              <strong>{c.titulo}</strong><br />
              <span>{periodo(c.inicio_utc, c.fim_utc)}</span>{c.organizador_nome && <span style={suave}> · de {c.organizador_nome}</span>}<br />
              <span style={suave}>{conflito(c.conflita_com)}</span>
            </span>
            {c.proposta_id !== null ? <span role="status" style={suave}>Proposta enviada para o OK</span> : (
              <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {(Object.keys(RESPOSTAS) as Resposta[]).map((r) => (
                  <button key={r} className={r === "aceitar" ? "btn btn-primary" : "btn btn-secondary"} disabled={ocupado} aria-label={`${RESPOSTAS[r]} convite ${c.titulo}`} onClick={() => propor(c, r)}>{RESPOSTAS[r]}</button>))}
              </span>)}
            <Aviso erro={erros[`convite${c.evento_id}`]} />
          </li>))}
      </ul>
    </Bloco>);
}

/** Área Envios: Enviar manda o hash que você viu (se o conteúdo mudou, o servidor recusa); Recusar descarta. */
export function Envios() {
  const { ocupado, erros, agir } = useAcao();
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const pend = useApi<Fila>(`${ROTA}?estado=pendente`);
  const decid = useApi<Fila>(`${ROTA}?estado=decididas`);
  const recarregar = async () => { await Promise.all([pend.recarregar(), decid.recarregar()]); };
  const executar = async (chave: string, fn: () => Promise<unknown>, ok: string) => {
    setResultado(null);
    if (!(await agir(chave, fn, ok, recarregar))) await recarregar(); // falhou (ex.: 409 vencida): relê para não mostrar fila velha
  };
  const enviar = (e: Envio) => executar(`envio${e.id}`, async () => {
    const r = await api.post<Resultado>(`${ROTA}/${e.id}/enviar`, { hash: e.hash });
    setResultado(r.dados);
  }, "Envio processado.");
  const recusar = (e: Envio) => executar(`envio${e.id}`, () => api.post(`${ROTA}/${e.id}/recusar`), "Envio recusado.");
  const feitas = decid.env?.dados.itens ?? [];
  return (
    <Painel leitura={pend} arquivo="envios">
      {(d) => (<>
        <Convites aoMudar={recarregar} />
        <Bloco titulo={`Esperando seu OK · ${d.itens.length}`} nota="Nada sai antes de você clicar em Enviar. Cada proposta vale por até 24 horas.">
          {d.escrita === "desligado" && <p role="status" style={{ margin: 0, ...suave }}>Envios desligados: enviar não manda nada ainda. Ligue em envios.escrita quando quiser.</p>}
          {resultado && <p role="status" style={{ margin: 0, ...suave }}>Proposta {resultado.id}: {resultado.estado}{resultado.motivo ? ` · ${resultado.motivo}` : ""}</p>}
          {d.itens.length === 0 ? <Vazio frase="Nada esperando seu OK." /> : (
            <ul style={lista}>
              {d.itens.map((e) => (
                <Cartao key={e.id} e={e}>
                  <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <button className="btn btn-primary" disabled={ocupado} aria-label={`Enviar proposta ${e.id}`} onClick={() => enviar(e)}>Enviar</button>
                    <button className="btn btn-secondary" disabled={ocupado} aria-label={`Recusar proposta ${e.id}`} onClick={() => recusar(e)}>Recusar</button>
                  </span>
                  <Aviso erro={erros[`envio${e.id}`]} />
                </Cartao>))}
            </ul>)}
          {feitas.length > 0 && (
            <>
              <h4 style={{ margin: "8px 0 0" }}>Decididas · {feitas.length}</h4>
              <ul style={lista}>{feitas.map((e) => <Cartao key={e.id} e={e} />)}</ul>
            </>)}
        </Bloco></>)}
    </Painel>
  );
}
