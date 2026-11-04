import { useState } from "react";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { useCelular } from "../../lib/celular";
import { dataCurta } from "../../lib/formato";
import { urlSegura } from "../../lib/url";
import { useApi } from "../../lib/useApi";

interface Prioridade { tipo: string; titulo: string; motivo?: string; ref: number; sugestao?: string }
export interface Evento { id: number; titulo: string | null; inicio_local: string | null; fim_local: string | null; dia_local: string; dia_fim_local: string; dia_inteiro: boolean; link_reuniao: string | null; fonte: string; privado: boolean }
interface Email { id: number; conta: string; remetente: string | null; assunto: string | null; recebida_em: string; classe: string; motivo: string | null }
interface Dinheiro { saldo: string; atrasadas: { n: number; valor: string }; sai_hoje: string; pago_hoje: string }
interface Dados { prioridades: Prioridade[]; agenda: Evento[]; correio_importantes: Email[]; dinheiro: Dinheiro }

const hora = (iso: string) => iso.slice(11, 16);
/** Horário LOCAL do compromisso (o servidor já converteu); dia inteiro não tem horário. */
export const quando = (e: Evento) => (e.dia_inteiro || !e.inicio_local || !e.fim_local ? "dia inteiro" : `${hora(e.inicio_local)}–${hora(e.fim_local)}`);
const ABAS = ["Fazer", "Agenda", "Dinheiro", "E-mails"] as const;

/** Hoje: o que precisa de mim. Lê só de tabelas prontas. */
export function Hoje() {
  const [aba, setAba] = useState<(typeof ABAS)[number]>("Fazer");
  const celular = useCelular();
  const leitura = useApi<Dados>("/api/v1/hoje");
  return (
    <Painel leitura={leitura} arquivo="hoje">
      {(d) => {
        const frase = d.prioridades.length === 0 ? "Nada pede você agora." : `${d.prioridades.length} ${d.prioridades.length === 1 ? "coisa pede" : "coisas pedem"} você hoje.`;
        const blocos: Record<(typeof ABAS)[number], React.ReactNode> = {
          Fazer: <Bloco titulo="Fazer">{d.prioridades.length === 0 ? <Vazio t="Nada na fila." /> : d.prioridades.map((p, i) => (
            <li key={i} data-prioridade><strong>{p.titulo}</strong>{p.motivo && <small> · {p.motivo}</small>}{p.sugestao && <small> · a Gabi sugere {hora(p.sugestao)}</small>}</li>))}</Bloco>,
          Agenda: <Bloco titulo="Agenda">{d.agenda.length === 0 ? <Vazio t="Sem compromissos hoje." /> : d.agenda.map((e) => (
            <li key={e.id}><span style={{ fontVariantNumeric: "tabular-nums" }}>{quando(e)}</span> {e.titulo ?? "(sem título)"}{e.privado && <small> · privado</small>} <small style={{ color: "var(--ink2)" }}>· {e.fonte}</small>{urlSegura(e.link_reuniao) && <> · <a href={urlSegura(e.link_reuniao)!} target="_blank" rel="noopener noreferrer">entrar</a></>}</li>))}</Bloco>,
          Dinheiro: <Bloco titulo="Dinheiro">{<>
            <li>Caixa agora <Valor valor={d.dinheiro.saldo} /></li>
            <li>Em atraso: {d.dinheiro.atrasadas.n} · <Valor valor={d.dinheiro.atrasadas.valor} /></li>
            <li>Sai hoje <Valor valor={d.dinheiro.sai_hoje} /></li><li>Já pago hoje <Valor valor={d.dinheiro.pago_hoje} /></li></>}</Bloco>,
          "E-mails": <Bloco titulo="E-mails que importam">{d.correio_importantes.length === 0 ? <Vazio t="Nenhum e-mail pede resposta." /> : d.correio_importantes.map((m) => (
            <li key={m.id} data-email><strong>{m.assunto ?? "(sem assunto)"}</strong> · {m.remetente ?? "?"} · {dataCurta(m.recebida_em.slice(0, 10))}<br /><small>{m.motivo}</small></li>))}</Bloco>,
        };
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <h3 style={{ margin: 0, fontSize: 22 }}>Gabi: {frase}</h3>
            <div data-instrumentos style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(120px,1fr))", gap: 8 }}>
              <Celula n="Caixa agora" v={d.dinheiro.saldo} /><Celula n="Em atraso" v={String(d.dinheiro.atrasadas.n)} />
              <Celula n="Sai hoje" v={d.dinheiro.sai_hoje} /><Celula n="Agenda" v={String(d.agenda.length)} /><Celula n="E-mails" v={String(d.correio_importantes.length)} />
            </div>
            {celular ? (
              <>
                <div role="tablist" style={{ display: "flex", gap: 6 }}>
                  {ABAS.map((a) => <button key={a} role="tab" aria-selected={aba === a} onClick={() => setAba(a)} style={chip(aba === a)}>{a}</button>)}
                </div>
                {blocos[aba]}
              </>
            ) : <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 14 }}>{ABAS.map((a) => <div key={a}>{blocos[a]}</div>)}</div>}
          </div>
        );
      }}
    </Painel>
  );
}

const chip = (ativo: boolean) => ({ height: 32, padding: "0 12px", border: "1px solid var(--line3)", background: ativo ? "var(--sel-bg, var(--raised))" : "transparent", color: "var(--color-text)", font: "600 12.5px var(--font-body)", cursor: "pointer" }) as const;
const Celula = ({ n, v }: { n: string; v: string }) => <div style={{ border: "1px solid var(--color-divider)", padding: "8px 10px" }}><small>{n}</small><div style={{ font: "600 20px var(--font-heading)", fontVariantNumeric: "tabular-nums" }}>{v}</div></div>;
const Vazio = ({ t }: { t: string }) => <li style={{ color: "var(--ink2)", listStyle: "none" }}>{t}</li>;
export const Bloco = ({ titulo, children }: { titulo: string; children: React.ReactNode }) => (
  <section style={{ border: "1px solid var(--color-divider)", padding: "10px 12px" }}><h4 style={{ margin: "0 0 8px" }}>{titulo}</h4><ul style={{ margin: 0, paddingLeft: 16, display: "flex", flexDirection: "column", gap: 6 }}>{children}</ul></section>
);
