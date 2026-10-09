import { useState } from "react";
import { Etiqueta, type TipoEtiqueta } from "../../componentes/Etiqueta";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { api } from "../../lib/api";
import { dataCurta } from "../../lib/formato";
import { useIr } from "../../lib/ocultar";
import { useToast } from "../../lib/toast";
import { useApi } from "../../lib/useApi";

interface ItemR { lancamento_id: number; data: string; descricao: string | null; valor: string; em_aberto: string; comprovante: "confirmado" | "proposto" | "faltando" }
interface Credito { lancamento_id: number; data: string; descricao: string | null; valor: string; a_aplicar: string }
interface Empresa { empresa_id: string; nome: string; em_aberto: string; itens: ItemR[]; reembolsos: { id: number; estado: string; cobrado_em: string | null }[]; creditos?: Credito[] }
interface ItemLote { lancamento_id: number; data: string; descricao: string | null; valor: string }
interface Lote { id: number | null; texto_confirmacao: string; itens: ItemLote[] }
interface Dados { empresas: Empresa[]; lote: Lote }

const COMPROVANTE: Record<ItemR["comprovante"], [TipoEtiqueta, string]> = { confirmado: ["ok", "comprovante"], proposto: ["conferir", "confirme o vínculo"], faltando: ["atencao", "sem comprovante"] };
const ESTADO: Record<string, string> = { a_cobrar: "a cobrar", cobrado: "cobrado", parcialmente_recebido: "parcialmente recebido", quitado: "quitado" };

/** Cobrar › Reembolsos: quem me deve (ness, IONIC) e o lote diário "Lançar na PJ" da Bekaa. Só o lote grava fora, com confirmação textual. */
export function Reembolsos() {
  const leitura = useApi<Dados>("/api/v1/cobrar/reembolsos");
  const avisar = useToast();
  const ir = useIr();
  const [co, setCo] = useState<string>("");
  const [marcadas, setMarcadas] = useState<number[]>([]);
  const [confirmando, setConfirmando] = useState<{ id: number; texto: string } | null>(null);

  const preparar = async (empresaId: string) => {
    try {
      await api.post("/api/v1/cobrar/cobrancas", marcadas.length ? { empresa_id: empresaId, itens: marcadas } : { empresa_id: empresaId });
      avisar("Rascunho guardado. Nada foi enviado.");
      ir("cobrar", "email");
    } catch (e) { avisar((e as Error).message); }
  };
  const cobrado = async (empresaId: string) => {
    try {
      const rid = (await api.post<{ id: number }>("/api/v1/cobrar/reembolsos", marcadas.length ? { empresa_id: empresaId, itens: marcadas } : { empresa_id: empresaId })).dados.id;
      await api.post(`/api/v1/cobrar/reembolsos/${rid}/cobrado`);
      avisar("Anotado: reembolso cobrado. Agora aguardo o recebimento na conta PJ.");
      leitura.recarregar();
    } catch (e) { avisar((e as Error).message); }
  };
  const conciliar = async (empresaId: string, creditoId: number) => {
    try {
      const r = (await api.post<{ casados: number[]; sobra: string }>("/api/v1/cobrar/reembolsos/conciliar", { empresa_id: empresaId, credito_id: creditoId })).dados;
      avisar(`Baixado: ${r.casados.length} item(ns) quitado(s)${r.sobra !== "0.00" ? `, sobraram R$ ${r.sobra.replace(".", ",")} do crédito` : ""}.`);
      leitura.recarregar();
    } catch (e) { avisar((e as Error).message); }
  };
  const abrirLote = async () => {
    try {
      const l = (await api.post<Lote>("/api/v1/cobrar/lote/montar")).dados;
      if (l.id === null) { avisar("Nada para lançar no Nibo hoje."); return; }
      setConfirmando({ id: l.id, texto: l.texto_confirmacao });
    } catch (e) { avisar((e as Error).message); }
  };
  const gravar = async () => {
    if (!confirmando) return;
    try {
      const r = (await api.post<{ ok: number; erro: number }>(`/api/v1/cobrar/lote/${confirmando.id}/executar`, { confirmacao: confirmando.texto })).dados;
      avisar(`Gravado no Nibo: ${r.ok} lançamento(s)${r.erro ? `, ${r.erro} com erro (volta no próximo lote)` : ""}. Dá para estornar no próprio Nibo.`);
      setConfirmando(null); leitura.recarregar();
    } catch (e) { avisar((e as Error).message); setConfirmando(null); }
  };
  const marcar = (id: number, on: boolean) => setMarcadas(on ? [...marcadas, id] : marcadas.filter((x) => x !== id));

  return (
    <Painel leitura={leitura} arquivo="reembolsos">
      {(d) => {
        const atual = co || d.empresas[0]?.empresa_id || "bekaa";
        const empresa = d.empresas.find((e) => e.empresa_id === atual);
        const ehBekaa = atual === "bekaa";
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <div role="tablist" aria-label="Empresa" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {d.empresas.map((e) => <button key={e.empresa_id} role="tab" aria-selected={atual === e.empresa_id} className={atual === e.empresa_id ? "btn btn-primary" : "btn btn-secondary"} onClick={() => { setCo(e.empresa_id); setMarcadas([]); }}>{e.nome} · R$ {e.em_aberto.replace(".", ",")}</button>)}
              <button role="tab" aria-selected={ehBekaa} className={ehBekaa ? "btn btn-primary" : "btn btn-secondary"} onClick={() => { setCo("bekaa"); setMarcadas([]); }}>Bekaa · lote do Nibo</button>
            </div>
            {ehBekaa ? (
              <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <p style={{ margin: 0, color: "var(--ink2)" }}>Despesas da Bekaa pagas no PF. Não geram cobrança: vão num lote diário para o Nibo da Bekaa, a PJ passa a dever ao sócio.</p>
                {d.lote.itens.length === 0 && <div style={{ border: "1px dashed var(--line3)", padding: 18, color: "var(--ink2)" }}>Gabi: nada da Bekaa para lançar hoje.</div>}
                {d.lote.itens.map((i) => (
                  <div key={i.lancamento_id} style={{ display: "grid", gridTemplateColumns: "70px minmax(0,1fr) auto", gap: 10, padding: "9px 0", borderTop: "1px solid var(--line2)" }}>
                    <span style={{ font: "500 12.5px var(--mono)" }}>{dataCurta(i.data)}</span><span>{i.descricao}</span><span style={{ fontVariantNumeric: "tabular-nums" }}><Valor valor={i.valor} /></span>
                  </div>
                ))}
                <div><button className="btn btn-primary" disabled={d.lote.itens.length === 0} onClick={abrirLote}>Lote de hoje → Nibo…</button></div>
              </section>
            ) : (
              <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {empresa && empresa.reembolsos.length > 0 && (
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>{empresa.reembolsos.map((r) => <Etiqueta key={r.id} tipo={r.estado === "quitado" ? "ok" : "conferir"} texto={`cobrança ${r.id}: ${ESTADO[r.estado] ?? r.estado}`} />)}</div>
                )}
                {(empresa?.itens ?? []).length === 0 && <div style={{ border: "1px dashed var(--line3)", padding: 18, color: "var(--ink2)" }}>Gabi: nenhuma despesa em aberto para esta empresa.</div>}
                {(empresa?.itens ?? []).map((i) => (
                  <label key={i.lancamento_id} style={{ display: "grid", gridTemplateColumns: "auto 70px minmax(0,1fr) auto auto", gap: 10, padding: "9px 0", borderTop: "1px solid var(--line2)", alignItems: "center" }}>
                    <input type="checkbox" aria-label={`Selecionar ${i.descricao}`} checked={marcadas.includes(i.lancamento_id)} onChange={(e) => marcar(i.lancamento_id, e.target.checked)} />
                    <span style={{ font: "500 12.5px var(--mono)" }}>{dataCurta(i.data)}</span><span>{i.descricao}</span>
                    <Etiqueta tipo={COMPROVANTE[i.comprovante][0]} texto={COMPROVANTE[i.comprovante][1]} />
                    <span style={{ fontVariantNumeric: "tabular-nums" }}><Valor valor={i.em_aberto} /></span>
                  </label>
                ))}
                {(empresa?.creditos ?? []).length > 0 && (
                  <div style={{ border: "1px solid var(--color-divider)", padding: "8px 12px", display: "flex", flexDirection: "column", gap: 6 }}>
                    <span style={{ font: "600 10.5px var(--font-body)", letterSpacing: ".08em", textTransform: "uppercase", color: "var(--ink2)" }}>Recebido na PJ</span>
                    {(empresa?.creditos ?? []).map((c) => (
                      <span key={c.lancamento_id} style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                        <span style={{ font: "500 12.5px var(--mono)" }}>{dataCurta(c.data)}</span><span style={{ flex: 1 }}>{c.descricao}</span>
                        <span style={{ fontVariantNumeric: "tabular-nums" }}><Valor valor={c.a_aplicar} /></span>
                        <button className="btn btn-secondary" onClick={() => conciliar(atual, c.lancamento_id)}>Baixar nos itens cobrados</button>
                      </span>
                    ))}
                  </div>
                )}
                <div><button className="btn btn-primary" disabled={(empresa?.itens ?? []).length === 0} onClick={() => preparar(atual)}>{marcadas.length ? `Preparar e-mail de reembolso (${marcadas.length})` : "Preparar e-mail com todos os itens"}</button>
                  {" "}<button className="btn btn-secondary" disabled={(empresa?.itens ?? []).length === 0} onClick={() => cobrado(atual)}>{marcadas.length ? `Marcar como cobrado (${marcadas.length})` : "Marcar como cobrado"}</button></div>
              </section>
            )}
            {confirmando && (
              <div role="dialog" aria-modal="true" aria-label="Confirmar lote do Nibo" style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", display: "grid", placeItems: "center", zIndex: 40 }}>
                <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-divider)", padding: 20, maxWidth: 520, display: "flex", flexDirection: "column", gap: 12 }}>
                  <strong style={{ font: "600 20px var(--font-heading)" }}>Gravar no Nibo?</strong>
                  <span>{confirmando.texto}</span>
                  <span style={{ fontSize: 12.5, color: "var(--ink2)" }}>É a única coisa que o app grava fora daqui. Repetir é seguro: nada é duplicado.</span>
                  <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                    <button className="btn btn-secondary" onClick={() => setConfirmando(null)}>Cancelar</button>
                    <button className="btn btn-primary" onClick={gravar}>Confirmar e gravar no Nibo</button>
                  </div>
                </div>
              </div>
            )}
          </div>
        );
      }}
    </Painel>
  );
}
