import { Bloco } from "../../componentes/Bloco";
import { Estat, GradeKpi } from "../../componentes/Kpi";
import { Painel } from "../../componentes/Painel";
import { useApi } from "../../lib/useApi";

interface Sugestao { tipo: string; aprovadas: number; rejeitadas: number; pendentes: number; taxa_aceite: number | null }
interface Tarefa { tarefa: string; chamadas: number; total_usd: number; medio_usd: number }
interface Ferramenta { ferramenta: string; chamadas: number; erros: number; mediana_ms: number | null; p95_ms: number | null }
interface Dados {
  aceite: { janela_dias: number; sugestoes: Sugestao[]; taxa_aceite_geral: number | null; perguntas: { respondidas: number; expiradas: number; abertas: number } };
  custo: { janela_dias: number; tarefas: Tarefa[]; total_usd: number };
  latencia: { janela_dias: number; ferramentas: Ferramenta[] };
}

const pct = (t: number | null) => (t === null ? "—" : `${Math.round(t * 100)}%`);
const usd = (n: number) => `US$ ${n.toFixed(2).replace(".", ",")}`;
const ms = (n: number | null) => (n === null ? "—" : `${n} ms`);
const TIPO: Record<string, string> = { categoria: "Categoria", para_quem: "Para quem", empresa: "Empresa", regra: "Regra", tarefa: "Tarefa" };

/** "A Gabi acerta e responde rápido?": aceite das sugestões, custo por tarefa do modelo e latência por ferramenta. Só leitura. */
export function Qualidade() {
  const leitura = useApi<Dados>("/api/v1/gabi/qualidade");
  return (
    <Painel leitura={leitura} arquivo="qualidade da Gabi">
      {(d) => (
        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          <GradeKpi min={190}>
            <Estat rotulo={`Sugestões aceitas (${d.aceite.janela_dias} dias)`}>{pct(d.aceite.taxa_aceite_geral)}</Estat>
            <Estat rotulo="Perguntas respondidas">{d.aceite.perguntas.respondidas}</Estat>
            <Estat rotulo="Perguntas sem resposta">{d.aceite.perguntas.abertas + d.aceite.perguntas.expiradas}</Estat>
            <Estat rotulo={`Custo do modelo (${d.custo.janela_dias} dias)`}>{usd(d.custo.total_usd)}</Estat>
          </GradeKpi>
          <Bloco titulo="Aceite das sugestões" nota="aprovadas ÷ (aprovadas + rejeitadas); pendentes não contam">
            {d.aceite.sugestoes.length === 0 ? <p>Nenhuma sugestão no período.</p> : (
              <table className="table" style={{ fontSize: 13.5 }}>
                <thead><tr><th>Tipo</th><th style={{ textAlign: "right" }}>Aprovadas</th><th style={{ textAlign: "right" }}>Rejeitadas</th><th style={{ textAlign: "right" }}>Pendentes</th><th style={{ textAlign: "right" }}>Aceite</th></tr></thead>
                <tbody>{d.aceite.sugestoes.map((s) => (
                  <tr key={s.tipo}><td style={{ fontWeight: 600 }}>{TIPO[s.tipo] ?? s.tipo}</td><td style={{ textAlign: "right" }}>{s.aprovadas}</td><td style={{ textAlign: "right" }}>{s.rejeitadas}</td><td style={{ textAlign: "right" }}>{s.pendentes}</td><td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{pct(s.taxa_aceite)}</td></tr>
                ))}</tbody>
              </table>
            )}
          </Bloco>
          <Bloco titulo="Custo por tarefa" nota={`modelo, últimos ${d.custo.janela_dias} dias, do mais caro ao mais barato`}>
            {d.custo.tarefas.length === 0 ? <p>Nenhuma chamada ao modelo no período.</p> : (
              <table className="table" style={{ fontSize: 13.5 }}>
                <thead><tr><th>Tarefa</th><th style={{ textAlign: "right" }}>Chamadas</th><th style={{ textAlign: "right" }}>Total</th><th style={{ textAlign: "right" }}>Por chamada</th></tr></thead>
                <tbody>{d.custo.tarefas.map((t) => (
                  <tr key={t.tarefa}><td style={{ fontWeight: 600 }}>{t.tarefa}</td><td style={{ textAlign: "right" }}>{t.chamadas}</td><td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{usd(t.total_usd)}</td><td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{usd(t.medio_usd)}</td></tr>
                ))}</tbody>
              </table>
            )}
          </Bloco>
          <Bloco titulo="Latência das ferramentas" nota={`últimos ${d.latencia.janela_dias} dias; mediana e p95 em milissegundos`}>
            {d.latencia.ferramentas.length === 0 ? <p>Nenhuma chamada no período.</p> : (
              <table className="table" style={{ fontSize: 13.5 }}>
                <thead><tr><th>Ferramenta</th><th style={{ textAlign: "right" }}>Chamadas</th><th style={{ textAlign: "right" }}>Erros</th><th style={{ textAlign: "right" }}>Mediana</th><th style={{ textAlign: "right" }}>p95</th></tr></thead>
                <tbody>{d.latencia.ferramentas.map((f) => (
                  <tr key={f.ferramenta}><td style={{ fontWeight: 600 }}>{f.ferramenta}</td><td style={{ textAlign: "right" }}>{f.chamadas}</td><td style={{ textAlign: "right", color: f.erros ? "var(--warn)" : undefined }}>{f.erros}</td><td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{ms(f.mediana_ms)}</td><td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{ms(f.p95_ms)}</td></tr>
                ))}</tbody>
              </table>
            )}
          </Bloco>
        </div>
      )}
    </Painel>
  );
}
