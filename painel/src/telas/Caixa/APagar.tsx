import type { ReactNode } from "react";
import { Etiqueta } from "../../componentes/Etiqueta";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { api } from "../../lib/api";
import { dataCurta, num } from "../../lib/formato";
import { useToast } from "../../lib/toast";
import { useApi } from "../../lib/useApi";

interface Item {
  id: string; nome: string; vencimento: string; vencimento_util: string; valor: string | null; estado: string; forma: string;
  dias_atraso?: number; pago_em?: string | null; diferenca?: string | null; motivo?: string | null;
}
type Grupos = Record<"atrasadas" | "hoje" | "proximas" | "adiante" | "debito_automatico" | "a_conferir" | "pagas", Item[]>;

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

export function APagar() {
  const leitura = useApi<Grupos>("/api/v1/contas-pagar");
  const avisar = useToast();
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
            {vazio && <p style={{ margin: 0, color: "var(--ink2)" }}>Gabi: nenhum compromisso no mês. Cadastre as linhas em Cadastros.</p>}
            {GRUPOS.filter(([g]) => d[g].length > 0).map(([g, titulo, cor, sub]) => (
              <section key={g} data-grupo={g} style={{ display: "flex", flexDirection: "column" }}>
                <Cabecalho cor={cor} titulo={titulo} sub={`${sub} · ${d[g].length}`}
                  direita={<span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700 }}><Valor valor={d[g].reduce((s, i) => s + num(i.valor), 0)} /></span>} />
                {d[g].map((b) => (
                  <div key={b.id} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: "6px 14px", padding: "11px 0", borderBottom: "1px solid var(--line2)", alignItems: "center" }}>
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
                    </div>
                  </div>
                ))}
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
          </div>
        );
      }}
    </Painel>
  );
}
