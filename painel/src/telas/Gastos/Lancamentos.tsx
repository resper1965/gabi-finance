import { useState } from "react";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { api } from "../../lib/api";
import { useFiltros } from "../../lib/filtros";
import { dataCurta, num, originalEmReais } from "../../lib/formato";
import { useToast } from "../../lib/toast";
import { useApi } from "../../lib/useApi";
import { useOcultar } from "../../lib/ocultar";

interface Campo { id: number | string | null; nome: string | null; origem: string | null }
interface Lanc { id: number; data: string; estabelecimento: string; valor: string; conta: string; categoria: Campo; para_quem: Campo; empresa: Campo; moeda?: string; valor_original?: string | null; convertido?: boolean; gasto?: { valor: boolean; origem: string | null }; gastador?: Campo; portadores?: string[] }
interface Sug { id: number; tipo: string; lancamento_id: number | null; payload: Record<string, number | string>; motivo: string }
interface Pessoa { id: number | string; nome: string; papel?: string | null; dados?: Record<string, unknown> }
interface ContaUso { apelido: string; usuarios?: string[] }

const ORIGEM: Record<string, string> = { banco: "banco", regra: "regra", gabi: "Gabi sugere", voce: "você", fonte: "padrão do cadastro" };
const POR_QUE: Record<string, string> = { fatura: "paga fatura de cartão", emissor: "boleto de fatura de cartão", propria: "transferência para empresa sua", investimento: "investimento", voce: "marcado por você" };

/** "De quem é cada gasto?": toque no chip; vale só para aquele lançamento. "sempre assim" cria regra (R1: só com o seu toque). */
export function Lancamentos() {
  const { conta } = useFiltros();
  const avisar = useToast();
  const oculto = useOcultar();
  const [filtro, setFiltro] = useState<"esperando" | "gastador" | "todos">("esperando");
  const url = `/api/v1/lancamentos?limite=100${filtro === "esperando" ? "&pendente=para_quem" : filtro === "gastador" ? "&pendente=gastador" : ""}${conta ? `&conta=${encodeURIComponent(conta)}` : ""}`;
  const leitura = useApi<{ itens: Lanc[]; total: number }>(url);
  const pessoas = useApi<{ itens: Pessoa[] }>("/api/v1/cadastros/pessoas").env?.dados.itens ?? [];
  const contas = useApi<{ itens: ContaUso[] }>("/api/v1/cadastros/contas").env?.dados.itens ?? [];
  const empresas = useApi<{ itens: { id: string; nome: string }[] }>("/api/v1/cadastros/empresas").env?.dados.itens ?? [];
  const sugestoes = useApi<{ itens: Sug[] }>("/api/v1/sugestoes");
  const sugParaQuem = (sugestoes.env?.dados.itens ?? []).filter((s) => s.tipo === "para_quem" && s.lancamento_id !== null);
  const recarregar = () => { leitura.recarregar(); sugestoes.recarregar(); };

  /** Quem aparece como opção: nunca quem só recebe pagamento (beneficiario=false); num cartão de 2+ usuários, só eles e os donos coletivos (Casa, Pets). */
  const opcoesPara = (l: Lanc) => {
    const usuarios = contas.find((c) => c.apelido.trim() === l.conta.trim())?.usuarios ?? [];
    return pessoas.filter((p) => p.id === l.para_quem.id || (p.dados?.beneficiario !== false &&
      (usuarios.length < 2 || usuarios.includes(String(p.id)) || p.papel === "coletivo")));
  };
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
  /** gasto: true/false é a sua marcação (vence as regras); null devolve a decisão à Gabi. */
  const marcarGasto = async (l: Lanc, gasto: boolean | null) => {
    try { await api.patch(`/api/v1/lancamentos/${l.id}`, { gasto }); avisar(gasto === null ? `${l.estabelecimento}: a Gabi volta a decidir.` : `Anotado: ${l.estabelecimento} ${gasto ? "é" : "não é"} gasto.`); recarregar(); }
    catch (e) { avisar((e as Error).message); }
  };
  /** Reembolso: a empresa que te devolve esta compra (entra em "Despesas por empresa"); continua sendo gasto seu. "" = pessoal. */
  const marcarReembolso = async (l: Lanc, empresa: string) => {
    const nome = empresas.find((c) => c.id === empresa)?.nome;
    try { await api.patch(`/api/v1/lancamentos/${l.id}`, { empresa_id: empresa || null }); avisar(nome ? `Anotado: ${l.estabelecimento} é reembolso ${nome}.` : `Anotado: ${l.estabelecimento} é pessoal, sem reembolso.`); recarregar(); }
    catch (e) { avisar((e as Error).message); }
  };
  /** Quem gastou (portador): só nos cartões com 2+ portadores; "sempre" grava a regra desta loja neste cartão. */
  const indicar = async (l: Lanc, pessoa: string, sempre = false) => {
    const nome = pessoas.find((p) => String(p.id) === pessoa)?.nome ?? pessoa;
    try {
      await api.post("/api/v1/lancamentos/lote", { ids: [l.id], mudancas: { gastador_id: pessoa }, criar_regra: sempre });
      avisar(sempre ? `Regra criada por você: ${l.estabelecimento} neste cartão é sempre de ${nome}.` : `Anotado: ${nome} gastou em ${l.estabelecimento}.`); recarregar();
    } catch (e) { avisar((e as Error).message); }
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
              {([["esperando", "Esperando você"], ["gastador", "Quem gastou: a indicar"], ["todos", "Todos"]] as const).map(([id, r]) => (
                <button key={id} className="seg-opt" aria-pressed={filtro === id} onClick={() => setFiltro(id)}
                  style={{ whiteSpace: "nowrap", border: 0, borderLeft: "1px solid var(--color-divider)", marginLeft: -1, background: filtro === id ? "var(--color-accent)" : "transparent", color: filtro === id ? "var(--color-bg)" : "var(--color-text)" }}>{r}</button>
              ))}
            </div>
            {sugParaQuem.length > 0 && <button className="btn btn-secondary" onClick={confirmarTodas}>Confirmar as {sugParaQuem.length} sugestões da Gabi</button>}
          </div>
          {d.itens.length === 0 && <div style={{ border: "1px dashed var(--line3)", padding: 18, color: "var(--ok)", fontWeight: 600 }}>{filtro === "gastador" ? "✓ Nenhuma compra de cartão compartilhado esperando você indicar quem gastou." : "✓ Nada esperando você. Todos os lançamentos têm dono."}</div>}
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
                    <span style={{ font: "600 16px var(--font-heading)", fontVariantNumeric: "tabular-nums", textAlign: "right" }}>
                      <Valor valor={l.valor} />
                      {!oculto && originalEmReais(l) && <span style={{ display: "block", font: "500 11.5px var(--font-body)", color: "var(--ink2)" }}>{originalEmReais(l)}</span>}
                    </span>
                  </div>
                  {(l.portadores?.length ?? 0) >= 2 && (
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", fontSize: 12, color: "var(--ink2)" }}>
                      <span>Quem gastou:</span>
                      <span role="group" aria-label={`Quem gastou: ${l.estabelecimento}`} style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {l.portadores!.map((pid) => {
                          const marcado = l.gastador?.id === pid;
                          return <button key={pid} aria-pressed={marcado} onClick={() => indicar(l, pid)}
                            style={{ minHeight: 32, padding: "0 10px", border: `1px solid ${marcado ? "var(--color-accent)" : "var(--line3)"}`, background: marcado ? "var(--color-accent)" : "transparent", color: marcado ? "var(--color-bg)" : "var(--color-text)", cursor: "pointer", font: "600 12.5px var(--font-body)" }}>{pessoas.find((p) => String(p.id) === pid)?.nome ?? pid}</button>;
                        })}
                      </span>
                      {l.gastador?.id && l.gastador.origem === "voce" && <button onClick={() => indicar(l, String(l.gastador!.id), true)} style={{ padding: 0, border: 0, background: "transparent", color: "var(--color-accent-700)", fontSize: 12, cursor: "pointer", textDecoration: "underline" }}>sempre {l.gastador.nome} em {l.estabelecimento} neste cartão</button>}
                      {l.gastador?.origem === "regra" && <span>(regra desta loja)</span>}
                    </div>
                  )}
                  <div role="group" aria-label={`Para quem: ${l.estabelecimento}`} style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {opcoesPara(l).map((p) => {
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
                    {l.gasto && num(l.valor) < 0 && <>
                      <span aria-hidden="true">·</span>
                      <span>{l.gasto.valor ? "é gasto" : `não é gasto${l.gasto.origem ? ` (${POR_QUE[l.gasto.origem] ?? l.gasto.origem})` : ""}`}</span>
                      <button onClick={() => marcarGasto(l, !l.gasto!.valor)} style={{ padding: 0, border: 0, background: "transparent", color: "var(--color-accent-700)", fontSize: 12, cursor: "pointer", textDecoration: "underline" }}>{l.gasto.valor ? "não é gasto" : "é gasto"}</button>
                      {l.gasto.origem === "voce" && <button onClick={() => marcarGasto(l, null)} style={{ padding: 0, border: 0, background: "transparent", color: "var(--color-accent-700)", fontSize: 12, cursor: "pointer", textDecoration: "underline" }}>deixar a Gabi decidir</button>}
                    </>}
                    {num(l.valor) < 0 && empresas.length > 0 && <>
                      <span aria-hidden="true">·</span>
                      <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>Reembolso:
                        <select aria-label={`Reembolso: ${l.estabelecimento}`} value={l.empresa.id == null ? "" : String(l.empresa.id)} onChange={(e) => marcarReembolso(l, e.target.value)}
                          style={{ minHeight: 28, font: "500 12px var(--font-body)", color: "var(--color-text)", background: "transparent", border: "1px solid var(--line3)" }}>
                          <option value="">pessoal</option>
                          {empresas.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
                        </select>
                      </label>
                    </>}
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
