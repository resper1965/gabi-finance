import { useState } from "react";
import { Etiqueta, type TipoEtiqueta } from "../../componentes/Etiqueta";
import { Painel } from "../../componentes/Painel";
import { useCelular } from "../../componentes/Shell";
import { Valor } from "../../componentes/Valor";
import { api } from "../../lib/api";
import { dataCurta, mesCurto, num } from "../../lib/formato";
import { useToast } from "../../lib/toast";
import { useApi } from "../../lib/useApi";

interface Ass {
  id: number; nome: string; mensal: string; anual: string; meses_vistos: number; status: string; no_rol?: boolean; lembrar_ate_cancelar: boolean; ativa?: boolean;
  serie_12m: { mes: string; total: string }[]; desde: string | null; ultimo: string | null; total_12m: string;
  sinais: { nova: boolean; reajustou: { antes: string; agora: string } | null; cobrada_depois_de_cancelar: boolean };
}
const STATUS: [string, string, string][] = [["a_conferir", "? a conferir", "var(--warn)"], ["manter", "✓ manter", "var(--ok)"], ["cancelar", "× cancelar", "var(--danger)"], ["nao_assinatura", "– não é assinatura", "var(--ink2)"], ["encerrada", "■ encerrada", "var(--ink2)"]];
const cor = (s: string) => STATUS.find(([v]) => v === s)?.[2] ?? "var(--ink2)";
const selecao = { height: 32, border: "1px solid var(--line3)", background: "var(--raised)", color: "var(--color-text)", font: "600 12.5px var(--font-body)", padding: "0 4px" } as const;

function Barras({ serie, largura }: { serie: Ass["serie_12m"]; largura: number }) {
  const topo = Math.max(1, ...serie.map((m) => num(m.total)));
  return (
    <span style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 24 }}>
      {serie.map((m) => <span key={m.mes} title={`${mesCurto(m.mes)}: ${m.total}`} style={{ width: largura, height: Math.max(1, (num(m.total) / topo) * 22), background: num(m.total) ? "var(--color-accent)" : "var(--line2)" }} />)}
    </span>
  );
}

export function Assinaturas() {
  const celular = useCelular();
  const leitura = useApi<{ itens: Ass[]; total_mensal: string; alerta_forte: boolean }>("/api/v1/assinaturas");
  const avisar = useToast();
  const [filtro, setFiltro] = useState("rol");
  const [marcadas, setMarcadas] = useState<number[]>([]);
  const [novo, setNovo] = useState("");
  const mudar = async (ids: number[], corpo: Record<string, unknown>, texto: string) => {
    try { for (const id of ids) await api.patch(`/api/v1/assinaturas/${id}`, corpo); avisar(texto); setMarcadas([]); setNovo(""); leitura.recarregar(); }
    catch (e) { avisar((e as Error).message); }
  };
  return (
    <Painel leitura={leitura} arquivo="assinaturas detectadas">
      {(d) => {
        // "não é assinatura" e "encerrada" saem do rol: somem da lista padrão, dos totais e dos alertas (ficam no filtro do próprio status, para desfazer)
        const rol = d.itens.filter((a) => a.no_rol !== false);
        const linhas = filtro === "rol" ? rol : d.itens.filter((a) => a.status === filtro);
        const total12 = rol.reduce((s, a) => s + num(a.total_12m), 0);
        const aConferir = d.itens.filter((a) => a.status === "a_conferir").length;
        const flags = (a: Ass) => (
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
            {a.ativa === false && <Etiqueta tipo="conferir" texto="parou de cobrar" />}
            {a.sinais.nova && <Etiqueta tipo="atencao" texto="nova" />}
            {a.sinais.reajustou && <Etiqueta tipo="atencao" texto={`reajustou ${a.sinais.reajustou.antes} → ${a.sinais.reajustou.agora}`} />}
            {a.sinais.cobrada_depois_de_cancelar && <Etiqueta tipo="erro" texto="cobrada depois de cancelar" />}
          </div>
        );
        const status = (a: Ass, alto: number) => (
          <select aria-label={`Status de ${a.nome}`} value={a.status} onChange={(e) => mudar([a.id], { status: e.target.value }, `Anotado: ${a.nome} marcada por você.`)}
            style={{ height: alto, padding: "0 6px", border: `1px solid ${cor(a.status)}`, background: "var(--raised)", color: cor(a.status), font: `600 ${alto > 40 ? 14 : 12.5}px var(--font-body)`, cursor: "pointer" }}>
            {STATUS.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
          </select>
        );
        const lembrar = (a: Ass) => a.status === "cancelar" && (
          <button className={celular ? "btn btn-secondary" : "btn btn-ghost"} style={celular ? { minHeight: 44 } : { fontSize: 12.5, padding: "2px 4px" }} onClick={() => mudar([a.id], { lembrar_ate_cancelar: !a.lembrar_ate_cancelar }, a.lembrar_ate_cancelar ? "Anotado: parei de lembrar." : "Anotado: eu lembro você até cancelar.")}>
            {a.lembrar_ate_cancelar ? "✓ Gabi lembra até cancelar" : "Pedir à Gabi para lembrar até cancelar"}
          </button>
        );
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,190px),1fr))", gap: 14 }}>
              {[["Recorrente por mês", <Valor key="m" valor={d.total_mensal} />, `${rol.filter((a) => a.ativa !== false).length} assinaturas ativas`], ["Em 12 meses", <Valor key="a" valor={total12} />, "débitos dos últimos 12 meses"]].map(([r, v, n]) => (
                <div key={String(r)} className="blueprint" style={{ padding: 14, display: "flex", flexDirection: "column", gap: 4 }}>
                  <i className="corner tl" /><i className="corner tr" /><i className="corner bl" /><i className="corner br" />
                  <span style={{ font: "600 10.5px var(--font-body)", letterSpacing: ".08em", textTransform: "uppercase", color: "var(--ink2)" }}>{r}</span>
                  <span style={{ font: "600 27px/1.05 var(--font-heading)", fontVariantNumeric: "tabular-nums" }}>{v}</span>
                  <span style={{ fontSize: 12, color: "var(--ink2)" }}>{n}</span>
                </div>
              ))}
              <div className="blueprint" style={{ padding: 14, display: "flex", flexDirection: "column", gap: 4 }}>
                <i className="corner tl" /><i className="corner tr" /><i className="corner bl" /><i className="corner br" />
                <span style={{ font: "600 10.5px var(--font-body)", letterSpacing: ".08em", textTransform: "uppercase", color: "var(--ink2)" }}>A conferir</span>
                <span style={{ font: "600 27px/1.05 var(--font-heading)", color: "var(--warn)" }}>{aConferir}</span>
                <span style={{ fontSize: 12, color: "var(--ink2)" }}>{rol.filter((a) => a.sinais.nova).length} novas</span>
              </div>
            </div>
            {rol.filter((a) => a.sinais.cobrada_depois_de_cancelar).map((a) => (
              <div key={a.id} role="alert" style={{ border: "2px solid var(--danger)", background: "var(--danger-bg)", padding: "14px 16px", display: "flex", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}>
                <span aria-hidden="true" style={{ width: 24, height: 24, flex: "none", display: "grid", placeItems: "center", background: "var(--danger)", color: "var(--color-bg)", font: "700 14px var(--mono)" }}>!</span>
                <div style={{ flex: "1 1 260px", display: "flex", flexDirection: "column", gap: 2 }}>
                  <strong style={{ color: "var(--danger)" }}>Cobrada depois de marcada para cancelar</strong>
                  <span>{a.nome} debitou <Valor valor={a.mensal} />{a.ultimo ? ` em ${dataCurta(a.ultimo)}` : ""}. Você marcou "cancelar", então o cancelamento não chegou ao fornecedor.</span>
                </div>
                {lembrar(a)}
              </div>
            ))}
            <div style={{ overflowX: "auto" }}>
              <div role="group" aria-label="Filtrar por status" className="seg">
                {([["rol", "No rol"], ...STATUS.map(([v, r]) => [v, r.replace(/^[^ ]+ /, "")] as const)] as const).map(([v, r]) => (
                  <button key={v} className="seg-opt" aria-pressed={filtro === v} onClick={() => setFiltro(v)}
                    style={{ whiteSpace: "nowrap", border: 0, borderLeft: "1px solid var(--color-divider)", marginLeft: -1, background: filtro === v ? "var(--color-accent)" : "transparent", color: filtro === v ? "var(--color-bg)" : "var(--color-text)" }}>{r}</button>
                ))}
              </div>
            </div>
            <div role="group" aria-label="Edição em lote" style={{ position: "sticky", top: 0, zIndex: 2, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", padding: "8px 12px", border: `1px solid ${marcadas.length ? "var(--color-accent)" : "var(--color-divider)"}`, background: "var(--color-bg)" }}>
              {marcadas.length === 0 && <span style={{ fontSize: 12.5, color: "var(--ink2)" }}>Marque várias assinaturas para mudar o status de uma vez.</span>}
              {marcadas.length > 0 && <>
                <strong style={{ fontSize: 13 }}>{marcadas.length} selecionadas</strong>
                <select aria-label="Novo status" value={novo} onChange={(e) => setNovo(e.target.value)} style={selecao}><option value="">Novo status…</option>{STATUS.map(([v, r]) => <option key={v} value={v}>{r}</option>)}</select>
                <span style={{ flex: 1 }} />
                <button className="btn btn-ghost" onClick={() => setMarcadas([])}>Limpar</button>
                <button className="btn btn-primary" disabled={!novo} onClick={() => mudar(marcadas, { status: novo }, `${marcadas.length} assinaturas marcadas por você.`)}>Aplicar</button>
              </>}
            </div>
            {!celular ? (
              <table className="table" style={{ fontSize: 13.5 }}>
                <thead><tr><th style={{ width: 32 }} /><th>Assinatura</th><th style={{ textAlign: "right" }}>Valor atual</th><th>Desde · último</th><th>Débitos (12 meses)</th><th style={{ textAlign: "right" }}>12 meses</th><th>Status</th></tr></thead>
                <tbody>{linhas.map((a) => (
                  <tr key={a.id} data-assinatura={a.id} style={{ background: marcadas.includes(a.id) ? "var(--sel)" : undefined }}>
                    <td><input type="checkbox" aria-label={`Selecionar ${a.nome}`} checked={marcadas.includes(a.id)} onChange={(e) => setMarcadas(e.target.checked ? [...marcadas, a.id] : marcadas.filter((x) => x !== a.id))} style={{ width: 17, height: 17 }} /></td>
                    <td style={{ maxWidth: 300 }}><div style={{ fontWeight: 600 }}>{a.nome}</div>{flags(a)}</td>
                    <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: 600, whiteSpace: "nowrap" }}><Valor valor={a.mensal} /></td>
                    <td style={{ font: "500 12px var(--mono)", color: "var(--ink2)", whiteSpace: "nowrap" }}>{a.desde ? dataCurta(a.desde) : "—"}<br />{a.ultimo ? dataCurta(a.ultimo) : "—"}</td>
                    <td><Barras serie={a.serie_12m} largura={7} /></td>
                    <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}><Valor valor={a.total_12m} /></td>
                    <td><div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-start" }}>{status(a, 30)}{lembrar(a)}</div></td>
                  </tr>))}</tbody>
              </table>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>{linhas.map((a) => (
                <div key={a.id} data-assinatura={a.id} style={{ border: "1px solid var(--color-divider)", background: marcadas.includes(a.id) ? "var(--sel)" : undefined, padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                    <label style={{ display: "inline-flex", alignItems: "center", gap: 8, fontWeight: 600, cursor: "pointer" }}>
                      <input type="checkbox" checked={marcadas.includes(a.id)} onChange={(e) => setMarcadas(e.target.checked ? [...marcadas, a.id] : marcadas.filter((x) => x !== a.id))} style={{ width: 20, height: 20 }} />{a.nome}
                    </label>
                    <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700, whiteSpace: "nowrap" }}><Valor valor={a.mensal} /></span>
                  </div>
                  {flags(a)}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 10 }}><Barras serie={a.serie_12m} largura={8} /><span style={{ fontSize: 12, color: "var(--ink2)" }}>12 meses <strong style={{ color: "var(--color-text)" }}><Valor valor={a.total_12m} /></strong></span></div>
                  {status(a, 44)}{lembrar(a)}
                </div>))}
              </div>
            )}
            <span style={{ fontSize: 12, color: "var(--ink2)" }}>Barras: o total debitado em cada um dos últimos 12 meses. O status é seu; a Gabi só detecta a recorrência.</span>
          </div>
        );
      }}
    </Painel>
  );
}
