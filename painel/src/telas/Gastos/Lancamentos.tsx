import { useState } from "react";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { api } from "../../lib/api";
import { useFiltros } from "../../lib/filtros";
import { dataCurta } from "../../lib/formato";
import { useToast } from "../../lib/toast";
import { useApi } from "../../lib/useApi";

interface Campo { id: number | string | null; nome: string | null; origem: string | null }
interface Lanc { id: number; data: string; estabelecimento: string; valor: string; conta: string; categoria: Campo; para_quem: Campo; empresa: Campo }
interface Sug { id: number; tipo: string; lancamento_id: number | null; payload: Record<string, number | string>; motivo: string }
interface Pessoa { id: number | string; nome: string }

const ORIGEM: Record<string, string> = { banco: "banco", regra: "regra", gabi: "Gabi sugere", voce: "você", fonte: "fonte" };

/** "De quem é cada gasto?": toque no chip; vale só para aquele lançamento. "sempre assim" cria regra (R1: só com o seu toque). */
export function Lancamentos() {
  const { conta } = useFiltros();
  const avisar = useToast();
  const [filtro, setFiltro] = useState<"esperando" | "todos">("esperando");
  const url = `/api/v1/lancamentos?limite=100${filtro === "esperando" ? "&pendente=para_quem" : ""}${conta ? `&conta=${encodeURIComponent(conta)}` : ""}`;
  const leitura = useApi<{ itens: Lanc[]; total: number }>(url);
  const pessoas = useApi<{ itens: Pessoa[] }>("/api/v1/cadastros/pessoas").env?.dados.itens ?? [];
  const sugestoes = useApi<{ itens: Sug[] }>("/api/v1/sugestoes");
  const sugParaQuem = (sugestoes.env?.dados.itens ?? []).filter((s) => s.tipo === "para_quem" && s.lancamento_id !== null);
  const recarregar = () => { leitura.recarregar(); sugestoes.recarregar(); };

  const escolher = async (l: Lanc, p: Pessoa) => {
    try { await api.patch(`/api/v1/lancamentos/${l.id}`, { beneficiario_id: p.id }); avisar(`Anotado: ${l.estabelecimento} é de ${p.nome}, só este lançamento.`); recarregar(); }
    catch (e) { avisar((e as Error).message); }
  };
  const confirmar = async (s: Sug, l: Lanc) => {
    try { await api.post(`/api/v1/sugestoes/${s.id}/aprovar`); avisar(`Confirmado por você: ${l.estabelecimento}.`); recarregar(); }
    catch (e) { avisar((e as Error).message); }
  };
  const confirmarTodas = async () => {
    for (const s of sugParaQuem) await api.post(`/api/v1/sugestoes/${s.id}/aprovar`).catch(() => null);
    avisar(`${sugParaQuem.length} sugestões confirmadas por você.`);
    recarregar();
  };
  const sempreAssim = async (l: Lanc) => {
    try { await api.post("/api/v1/lancamentos/lote", { ids: [l.id], mudancas: { beneficiario_id: l.para_quem.id }, criar_regra: true }); avisar(`Regra criada por você: os próximos de ${l.estabelecimento} seguem igual.`); recarregar(); }
    catch (e) { avisar((e as Error).message); }
  };

  return (
    <Painel leitura={leitura} arquivo="lançamentos do extrato">
      {(d) => (
        <div style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: 1000 }}>
          <p style={{ margin: 0, fontSize: 13.5, color: "var(--ink2)", textWrap: "pretty" }}>
            Toque em quem é o gasto. A escolha vale <strong style={{ color: "var(--color-text)" }}>só para aquele lançamento</strong>; se quiser que todos os próximos do mesmo estabelecimento sigam igual, use "sempre assim", que vira regra. Cartões e contas aparecem juntos.
          </p>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <div role="group" aria-label="Filtro" className="seg">
              {([["esperando", "Esperando você"], ["todos", "Todos"]] as const).map(([id, r]) => (
                <button key={id} className="seg-opt" aria-pressed={filtro === id} onClick={() => setFiltro(id)}
                  style={{ whiteSpace: "nowrap", border: 0, borderLeft: "1px solid var(--color-divider)", marginLeft: -1, background: filtro === id ? "var(--color-accent)" : "transparent", color: filtro === id ? "var(--color-bg)" : "var(--color-text)" }}>{r}</button>
              ))}
            </div>
            {sugParaQuem.length > 0 && <button className="btn btn-secondary" onClick={confirmarTodas}>Confirmar as {sugParaQuem.length} sugestões da Gabi</button>}
          </div>
          {d.itens.length === 0 && <div style={{ border: "1px dashed var(--line3)", padding: 18, color: "var(--ok)", fontWeight: 600 }}>✓ Nada esperando você. Todos os lançamentos têm dono.</div>}
          <div style={{ display: "flex", flexDirection: "column" }}>
            {d.itens.map((l) => {
              const sug = sugParaQuem.find((s) => s.lancamento_id === l.id);
              return (
                <div key={l.id} data-lancamento={l.id} style={{ display: "flex", flexDirection: "column", gap: 8, padding: "12px 0", borderBottom: "1px solid var(--line2)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
                    <span style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap", minWidth: 0 }}>
                      <span style={{ font: "500 12px var(--mono)", color: "var(--ink2)" }}>{dataCurta(l.data)}</span>
                      <strong style={{ fontSize: 14.5 }}>{l.estabelecimento}</strong>
                      <span style={{ fontSize: 12, color: "var(--ink2)" }}>{l.conta} · {l.categoria.nome ?? "sem categoria"}{l.empresa.nome ? ` · reembolso ${l.empresa.nome}` : ""}</span>
                    </span>
                    <span style={{ font: "600 16px var(--font-heading)", fontVariantNumeric: "tabular-nums" }}><Valor valor={l.valor} /></span>
                  </div>
                  <div role="group" aria-label={`Para quem: ${l.estabelecimento}`} style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {pessoas.map((p) => {
                      const marcado = l.para_quem.id === p.id, sugerido = sug?.payload.para_quem_id === p.id;
                      return (
                        <button key={p.id} aria-pressed={marcado} onClick={() => escolher(l, p)}
                          style={{ minHeight: 32, padding: "0 10px", border: `1px ${sugerido && !marcado ? "dashed" : "solid"} ${marcado ? "var(--color-accent)" : sugerido ? "var(--warn)" : "var(--line3)"}`, background: marcado ? "var(--color-accent)" : sugerido ? "var(--warn-bg)" : "transparent", color: marcado ? "var(--color-bg)" : "var(--color-text)", cursor: "pointer", font: "600 12.5px var(--font-body)" }}>{p.nome}</button>
                      );
                    })}
                  </div>
                  <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", fontSize: 12, color: "var(--ink2)" }}>
                    <span>{sug ? `Gabi sugere: ${pessoas.find((p) => p.id === sug.payload.para_quem_id)?.nome ?? "?"} · ${sug.motivo}` : l.para_quem.origem ? `${l.para_quem.nome} · ${ORIGEM[l.para_quem.origem] ?? l.para_quem.origem}` : "sem dono ainda"}</span>
                    {sug && <button className="btn-link" onClick={() => confirmar(sug, l)} style={{ padding: 0, border: 0, background: "transparent", color: "var(--color-accent-700)", fontSize: 12, cursor: "pointer", textDecoration: "underline" }}>confirmar</button>}
                    {l.para_quem.origem === "voce" && <button onClick={() => sempreAssim(l)} style={{ padding: 0, border: 0, background: "transparent", color: "var(--color-accent-700)", fontSize: 12, cursor: "pointer", textDecoration: "underline" }}>sempre assim para {l.estabelecimento}</button>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Painel>
  );
}
