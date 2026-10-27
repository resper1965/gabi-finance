import { useState, type ReactNode } from "react";
import { Etiqueta } from "../../componentes/Etiqueta";
import { formatarDadosAte } from "../../componentes/Faixa";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { api } from "../../lib/api";
import { dataCurta, mesCurto, num } from "../../lib/formato";
import { useToast } from "../../lib/toast";
import { useApi } from "../../lib/useApi";
import { DespesaForm, type DespesaAlvo, type ModoDespesa } from "./DespesaForm";

interface Item {
  id: string; nome: string; vencimento: string; vencimento_util: string; valor: string | null; estado: string; forma: string;
  dias_atraso?: number; pago_em?: string | null; diferenca?: string | null; motivo?: string | null;
  linha_id?: string | null; mes?: string | null; tipo?: string | null; // a despesa do cadastro; null em fatura e documento avulso
}
type Grupos = Record<"atrasadas" | "hoje" | "proximas" | "adiante" | "debito_automatico" | "a_conferir" | "pagas", Item[]>;

interface Rodada { id: number; fonte: string; fim: string | null; status: string; lidos: number; novos: number; conferida: boolean; reprovadas: { conta: string; tipo: string; detalhe: string }[] }
const TIPO_CONFERENCIA: Record<string, string> = { saldo_final: "saldo", dias_sem_buraco: "dias sem movimento", volume_proximo: "volume" };

/** Últimas rodadas de extrato (06h e 14h) com o que foi lido e se a conferência fechou; se não, quais contas reprovaram e por quê. */
function Rodadas() {
  const itens = (useApi<{ itens: Rodada[] }>("/api/v1/rodadas?limite=20").env?.dados.itens ?? []).filter((r) => r.fonte === "open-finance").slice(0, 2);
  if (itens.length === 0) return null;
  return (
    <section role="region" aria-label="Rodadas" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <h3 style={{ margin: 0, fontSize: 20 }}>Rodadas <span style={{ font: "500 12px var(--mono)", color: "var(--ink2)" }}>· extratos às 6h e 14h</span></h3>
      <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column" }}>
        {itens.map((r) => (
          <li key={r.id} style={{ padding: "8px 0", borderTop: "1px solid var(--line2)", display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", fontSize: 13 }}>
              <span style={{ font: "500 12.5px var(--mono)" }}>{r.fim ? formatarDadosAte(r.fim) : "em andamento"}</span>
              <span data-estado={r.conferida ? "conferida" : "nao-conferida"} style={{ fontWeight: 600, color: r.conferida ? "var(--ok)" : "var(--warn)" }}>{r.conferida ? "conferida" : "não conferida"}</span>
              <span style={{ color: "var(--ink2)" }}>{r.lidos} lidos · {r.novos} novos</span>
            </span>
            {r.reprovadas.map((x, i) => <span key={i} style={{ fontSize: 12.5, color: "var(--ink2)" }}>▲ {x.conta}: {TIPO_CONFERENCIA[x.tipo] ?? x.tipo} — {x.detalhe}</span>)}
          </li>
        ))}
      </ul>
    </section>
  );
}

const GRUPOS: [keyof Grupos, string, string, string][] = [
  ["atrasadas", "Atrasadas", "var(--danger)", "já venceram"], ["hoje", "Vencem hoje", "var(--warn)", "pague hoje"],
  ["proximas", "Próximos 7 dias", "var(--color-text)", "até a próxima semana"], ["adiante", "Mais adiante", "var(--ink2)", "depois disso"],
  ["a_conferir", "A conferir", "var(--warn)", "valor ou documento incerto"], ["debito_automatico", "Débito automático", "var(--ink2)", "só aviso"],
];
const FORMA: Record<string, string> = { pix: "Pix", boleto: "boleto", debito_automatico: "débito automático", fatura: "fatura do cartão", "": "" };

function Cabecalho({ cor, titulo, sub, direita }: { cor: string; titulo: string; sub: string; direita?: ReactNode }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "baseline", paddingBottom: 6, borderBottom: `1px solid ${cor}` }}>
      <h3 style={{ margin: 0, fontSize: 20, color: cor }}>{titulo} <span style={{ font: "500 12px var(--mono)", color: "var(--ink2)" }}>· {sub}</span></h3>
      {direita}
    </div>
  );
}

const alvo = (b: Item): DespesaAlvo => ({ linha_id: b.linha_id!, nome: b.nome, valor: b.valor, mes: b.mes, vencimento: b.vencimento });
const MENU: [ModoDespesa | "dispensar" | "encerrar", string][] = [["mes", "Editar este mês"], ["dispensar", "Dispensar este mês"], ["daqui", "Mudar daqui em diante"], ["encerrar", "Encerrar"]];

/** Linha de A Pagar. Despesa (item com `linha_id`; fatura e documento avulso não têm) ganha o menu Ações: dispensar tem "Desfazer" no toast;
 *  encerrar pede confirmação e o desfazer fica em Cadastros › Despesas (não há rota para reabrir); editar o mês e mudar daqui em diante abrem o formulário na linha. */
function Linha({ g, b, paga, recarregar }: { g: keyof Grupos; b: Item; paga: (i: Item) => void; recarregar: () => Promise<void> }) {
  const avisar = useToast();
  const [menu, setMenu] = useState(false);
  const [aberto, setAberto] = useState<ModoDespesa | "encerrar" | null>(null);
  const id = encodeURIComponent(b.linha_id ?? "");
  const tentar = async (fn: () => Promise<void>) => { try { await fn(); } catch (e) { avisar((e as Error).message); } };
  const desfazer = () => tentar(async () => {
    await api.delete(`/api/v1/despesas/${id}/mes/${b.mes}/dispensar`);
    avisar(`Dispensa desfeita: ${b.nome} volta para A Pagar.`);
    await recarregar();
  });
  const dispensar = () => tentar(async () => {
    await api.post(`/api/v1/despesas/${id}/mes/${b.mes}/dispensar`);
    avisar(`${b.nome}: ${mesCurto(b.mes!)} dispensado.`, { rotulo: "Desfazer", fazer: desfazer });
    await recarregar();
  });
  const encerrar = () => tentar(async () => {
    await api.post(`/api/v1/despesas/${id}/encerrar`);
    setAberto(null);
    avisar(`${b.nome} encerrada: o que não foi pago saiu de A Pagar.`, { rotulo: "Desfazer", fazer: () => avisar("Para desfazer o encerramento, use Cadastros › Despesas.") });
    await recarregar();
  });
  const escolher = (k: (typeof MENU)[number][0]) => { setMenu(false); if (k === "dispensar") void dispensar(); else setAberto(k); };
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: "6px 14px", padding: "11px 0", borderBottom: "1px solid var(--line2)", alignItems: "center" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 0 }}>
        <span style={{ fontWeight: 600 }}>{b.nome}</span>
        <span style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", fontSize: 12.5, color: "var(--ink2)" }}>
          <span style={{ fontFamily: "var(--mono)", color: g === "atrasadas" ? "var(--danger)" : undefined }}>vence {dataCurta(b.vencimento_util)}</span>
          {FORMA[b.forma] && <span>· {FORMA[b.forma]}</span>}
          {g === "atrasadas" && <Etiqueta tipo="erro" texto={`${b.dias_atraso} ${b.dias_atraso === 1 ? "dia" : "dias"} de atraso`} />}
          {g === "debito_automatico" && <span style={{ display: "inline-flex", gap: 3, padding: "0 6px", border: "1px solid var(--line3)", font: "600 11px/1.6 var(--font-body)" }}>↻ débito automático · só aviso</span>}
          {g === "a_conferir" && b.motivo && <span>{b.motivo}</span>}
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, justifyContent: "flex-end", flexWrap: "wrap" }}>
        <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700, whiteSpace: "nowrap" }}>{b.valor === null ? "valor a conferir" : <Valor valor={b.valor} />}</span>
        {g !== "debito_automatico" && g !== "a_conferir" && <button className="btn btn-secondary" style={{ minHeight: 32 }} onClick={() => paga(b)}>Já paguei</button>}
        {b.linha_id && (
          <span style={{ position: "relative" }}>
            <button className="btn btn-secondary" style={{ minHeight: 32 }} aria-label={`Ações de ${b.nome}`} aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu(!menu)}>Ações ▾</button>
            {menu && (
              <div role="menu" aria-label={`Ações de ${b.nome}`} style={{ position: "absolute", right: 0, top: "100%", zIndex: 5, display: "flex", flexDirection: "column", minWidth: 200, background: "var(--color-surface)", border: "1px solid var(--line3)", boxShadow: "var(--shadow-md)" }}>
                {MENU.map(([k, r]) => <button key={k} role="menuitem" className="btn btn-secondary" style={{ border: 0, justifyContent: "flex-start", textAlign: "left" }} onClick={() => escolher(k)}>{r}</button>)}
              </div>)}
          </span>)}
      </div>
      {aberto === "encerrar" && (
        <div role="alert" style={{ gridColumn: "1 / -1", display: "flex", flexDirection: "column", gap: 8 }}>
          <p style={{ margin: 0 }}>Encerrar {b.nome}? O que não foi pago sai de A Pagar; o que já foi pago fica no histórico.</p>
          <span style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary" aria-label={`Confirmar encerrar ${b.nome}`} onClick={encerrar}>Confirmar</button>
            <button className="btn btn-secondary" onClick={() => setAberto(null)}>Cancelar</button>
          </span>
        </div>)}
      {(aberto === "mes" || aberto === "daqui") && (
        <div style={{ gridColumn: "1 / -1" }}>
          <DespesaForm modo={aberto} item={alvo(b)} aoCancelar={() => setAberto(null)} aoSalvar={() => { setAberto(null); void recarregar(); }} />
        </div>)}
    </div>
  );
}

export function APagar() {
  const leitura = useApi<Grupos>("/api/v1/contas-pagar");
  const avisar = useToast();
  const [nova, setNova] = useState(false);
  const paga = async (i: Item) => {
    try {
      await api.post(`/api/v1/contas-pagar/${encodeURIComponent(i.id)}/paga`);
      avisar(`Anotado: ${i.nome} paga. A próxima rodada confere com o extrato.`);
      leitura.recarregar();
    } catch (e) { avisar((e as Error).message); }
  };
  return (
    <Painel leitura={leitura} arquivo="planilha de compromissos">
      {(d) => {
        const vazio = (Object.keys(d) as (keyof Grupos)[]).every((g) => d[g].length === 0);
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
              {!nova && <button className="btn btn-secondary" style={{ minHeight: 32 }} onClick={() => setNova(true)}>+ despesa</button>}
              {nova && <div style={{ alignSelf: "stretch" }}><DespesaForm modo="nova" aoCancelar={() => setNova(false)} aoSalvar={() => { setNova(false); leitura.recarregar(); }} /></div>}
            </div>
            {vazio && <p style={{ margin: 0, color: "var(--ink2)" }}>Gabi: nenhum compromisso no mês. Cadastre as linhas em Cadastros.</p>}
            {GRUPOS.filter(([g]) => d[g].length > 0).map(([g, titulo, cor, sub]) => (
              <section key={g} data-grupo={g} style={{ display: "flex", flexDirection: "column" }}>
                <Cabecalho cor={cor} titulo={titulo} sub={`${sub} · ${d[g].length}`}
                  direita={<span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700 }}><Valor valor={d[g].reduce((s, i) => s + num(i.valor), 0)} /></span>} />
                {d[g].map((b) => <Linha key={b.id} g={g} b={b} paga={paga} recarregar={leitura.recarregar} />)}
              </section>
            ))}
            {d.pagas.length > 0 && (
              <section data-grupo="pagas" style={{ display: "flex", flexDirection: "column" }}>
                <Cabecalho cor="var(--ok)" titulo="Pagas" sub="conciliadas com o extrato" />
                {d.pagas.map((p) => {
                  const diff = p.diferenca && num(p.diferenca) !== 0;
                  return (
                    <div key={p.id} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: "6px 14px", padding: "11px 0", borderBottom: "1px solid var(--line2)", alignItems: "center" }}>
                      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                        <span style={{ fontWeight: 600 }}>{p.nome}</span>
                        <span style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", fontSize: 12.5, color: "var(--ink2)" }}>
                          <Etiqueta tipo="ok" texto="pago" />
                          <span>venc. {dataCurta(p.vencimento_util)}{p.pago_em ? ` ↔ extrato em ${dataCurta(p.pago_em)}` : ""}</span>
                        </span>
                        {diff && <span style={{ fontSize: 12.5, color: "var(--warn)" }}>≈ diferença de <Valor valor={p.diferenca!} /></span>}
                      </div>
                      <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700, whiteSpace: "nowrap" }}>{p.valor === null ? "" : <Valor valor={p.valor} />}</span>
                    </div>
                  );
                })}
              </section>
            )}
            <Rodadas />
          </div>
        );
      }}
    </Painel>
  );
}
