import { Bloco } from "../../componentes/Bloco";
import { Etiqueta, type TipoEtiqueta } from "../../componentes/Etiqueta";
import { GradeKpi, Kpi } from "../../componentes/Kpi";
import { Painel } from "../../componentes/Painel";
import { Marca } from "../../componentes/Shell";
import { Valor } from "../../componentes/Valor";
import { LinhaSaldo, type Ponto } from "../../graficos/LinhaSaldo";
import { useFiltros } from "../../lib/filtros";
import { dataCurta, num } from "../../lib/formato";
import { useIr, useOcultar } from "../../lib/ocultar";
import { useApi } from "../../lib/useApi";
import { rotaParaTela } from "../../navegacao";

interface Resumo {
  kpis: { saldo: string; a_pagar_7_dias: string; a_receber: string | null; faturas_abertas: string; assinaturas_mes: string };
  detalhe: { saldo_por_conta: { apelido: string; saldo: string }[]; a_pagar_contas: number; a_pagar_vencidas: number; cartoes_abertos: number;
             proxima_fatura: string | null; assinaturas_ativas: number; assinaturas_a_conferir: number };
  serie_saldo: Ponto[];
  atencao: { tipo: string; quantidade: number; texto: string; rota: string }[];
}

const TIPO: Record<string, [TipoEtiqueta, string, string]> = {
  atrasadas: ["erro", "Vencido", "Contas a pagar"], a_conferir: ["conferir", "Conferir", "Contas a pagar"],
  contas_a_decidir: ["conferir", "Decidir", "Cadastros"], sugestoes_pendentes: ["regra", "Regra", "Regras"],
};
const saudacao = (h: number) => (h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite");
const plural = (n: number, um: string, varios: string) => `${n} ${n === 1 ? um : varios}`;

export function Resumo() {
  const { periodo, conta } = useFiltros();
  const ir = useIr();
  const oculto = useOcultar();
  const leitura = useApi<Resumo>(`/api/v1/caixa/resumo?periodo=${periodo}${conta ? `&conta=${encodeURIComponent(conta)}` : ""}`);
  return (
    <Painel leitura={leitura} arquivo="saldos e extratos (open-finance)">
      {(d) => {
        const proj = d.serie_saldo.filter((p) => p.projecao);
        const menor = proj.length ? proj.reduce((a, b) => (num(b.valor) < num(a.valor) ? b : a)) : null;
        const hora = Number(new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", hour12: false }).format(new Date()));
        const nAtencao = d.atencao.reduce((s, a) => s + a.quantidade, 0);
        const det = d.detalhe;
        return (
          <>
            <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
              <Marca />
              <p style={{ margin: 0, fontSize: 15.5, lineHeight: 1.5, textWrap: "pretty" }}>
                {saudacao(hora)}.{" "}
                {menor && proj.length > 0 && <>O caixa vai até {dataCurta(proj[proj.length - 1].data)} com o ponto mais baixo projetado em <Valor valor={menor.valor} /> em {dataCurta(menor.data)}. </>}
                {nAtencao > 0 ? `Separei ${plural(nAtencao, "coisa", "coisas")} para você ver hoje.` : "Nada pede você agora."}
              </p>
            </div>
            <GradeKpi>
              <Kpi rotulo="Saldo do caixa único" nota={det.saldo_por_conta.map((c, i) => <span key={c.apelido}>{i ? " · " : ""}{c.apelido} <Valor valor={c.saldo} /></span>)}><Valor valor={d.kpis.saldo} /></Kpi>
              <Kpi rotulo="A pagar em 7 dias" nota={`${plural(det.a_pagar_contas, "conta", "contas")} · inclui vencidas`}
                   sinal={det.a_pagar_vencidas ? { tipo: "erro", texto: `${plural(det.a_pagar_vencidas, "vencida", "vencidas")}` } : undefined} aoClicar={() => ir("caixa", "contas")}><Valor valor={d.kpis.a_pagar_7_dias} /></Kpi>
              <Kpi rotulo="A receber das empresas" nota="aparece quando o Nibo estiver ligado">{d.kpis.a_receber === null ? "—" : <Valor valor={d.kpis.a_receber} />}</Kpi>
              <Kpi rotulo="Fatura aberta · cartões" nota={`${plural(det.cartoes_abertos, "cartão", "cartões")}${det.proxima_fatura ? ` · a próxima vence em ${dataCurta(det.proxima_fatura)}` : ""}`} aoClicar={() => ir("gastos", "cartao")}><Valor valor={d.kpis.faturas_abertas} /></Kpi>
              <Kpi rotulo="Assinaturas por mês" nota={`${plural(det.assinaturas_ativas, "ativa", "ativas")} · ${det.assinaturas_a_conferir} a conferir`} aoClicar={() => ir("gastos", "assin")}><Valor valor={d.kpis.assinaturas_mes} /></Kpi>
            </GradeKpi>
            <Bloco titulo="Saldo por banco" nota="cada conta liberada, separada: o total pode esconder uma conta negativa">
              {[...det.saldo_por_conta].sort((a, b) => num(b.saldo) - num(a.saldo)).map((c, i) => (
                <div key={`${c.apelido}-${i}`} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto auto", gap: 10, padding: "9px 0", borderTop: "1px solid var(--line2)", alignItems: "baseline" }}>
                  <span style={{ fontWeight: 600 }}>{c.apelido}</span>
                  <span>{num(c.saldo) < 0 && <Etiqueta tipo="erro" texto="negativo" />}</span>
                  <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700, color: num(c.saldo) < 0 ? "var(--danger)" : undefined }}><Valor valor={c.saldo} /></span>
                </div>
              ))}
            </Bloco>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,420px),1fr))", gap: 22, alignItems: "start" }}>
              <Bloco titulo="Saldo do caixa único" nota={`${d.serie_saldo.filter((p) => !p.projecao).length} dias realizados · ${proj.length} projetados`}>
                <LinhaSaldo pontos={d.serie_saldo} oculto={oculto} />
                <div style={{ display: "flex", gap: 16, flexWrap: "wrap", fontSize: 12, color: "var(--ink2)" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ width: 18, height: 2, background: "var(--color-accent-700)" }} />realizado</span>
                  <span style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ width: 18, borderTop: "2px dashed var(--color-accent)" }} />projeção (contas a pagar e entradas previstas)</span>
                  {menor && <span>menor saldo projetado: <strong style={{ color: "var(--color-text)" }}><Valor valor={menor.valor} /></strong> em {dataCurta(menor.data)}</span>}
                </div>
              </Bloco>
              <Bloco style={{ gap: 4 }}>
                <h3 style={{ margin: "0 0 8px", fontSize: 20 }}>Precisa da sua atenção</h3>
                {d.atencao.length === 0 && <p style={{ color: "var(--ink2)", margin: 0 }}>Nada pede você agora. Eu aviso quando surgir.</p>}
                {d.atencao.map((a) => {
                  const [tipo, rotulo, dest] = TIPO[a.tipo] ?? ["conferir", "Ver", "Abrir"];
                  const [area, aba] = rotaParaTela(a.rota);
                  return (
                    <button key={a.tipo} onClick={() => ir(area, aba)} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: "4px 10px", alignItems: "start", width: "100%", padding: "11px 4px", border: 0, borderTop: "1px solid var(--line2)", background: "transparent", color: "inherit", textAlign: "left", cursor: "pointer", font: "inherit" }}>
                      <span style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
                        <span style={{ alignSelf: "flex-start" }}><Etiqueta tipo={tipo} texto={rotulo} /></span>
                        <span style={{ fontWeight: 600, lineHeight: 1.3 }}>{a.texto}</span>
                      </span>
                      <span style={{ fontSize: 12, color: "var(--color-accent-700)", whiteSpace: "nowrap", paddingTop: 2 }}>{dest} →</span>
                    </button>
                  );
                })}
              </Bloco>
            </div>
          </>
        );
      }}
    </Painel>
  );
}
