import { Bloco } from "../../componentes/Bloco";
import { Etiqueta, type TipoEtiqueta } from "../../componentes/Etiqueta";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { dataCurta } from "../../lib/formato";
import { useApi } from "../../lib/useApi";

interface Item { pagador: string; situacao: string; esperado: string; recebido: string | null; recebido_em: string | null; dia_esperado?: string; vencimento?: string; numero?: string; dias_atraso?: number; extrato?: { descricao: string | null; conta?: string } | null }
interface Totais { esperado: string; recebido: string; falta: string; atrasado: string }
interface Dados { mes: string; recorrentes: Item[]; notas: Item[]; totais: { recorrentes: Totais; notas: Totais } }

const SITUACAO: Record<string, [TipoEtiqueta, string]> = {
  recebido: ["ok", "Já entrou"], a_receber: ["parado", "Ainda não venceu"], atrasado: ["erro", "Atrasado"], nibo_diz_pago: ["conferir", "Nibo diz pago: conferir no extrato"], credito_provavel: ["conferir", "Crédito provável no extrato: confirme em Notas a receber"],
};

function Tabela({ itens, ref_ }: { itens: Item[]; ref_: "dia" | "nota" }) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <thead><tr style={{ textAlign: "left", color: "var(--ink2)", fontSize: 12.5 }}><th>Quem</th><th>{ref_ === "dia" ? "Dia costumeiro" : "Vence"}</th><th>Esperado</th><th>Entrou no extrato</th><th>Situação</th></tr></thead>
      <tbody>
        {itens.map((i, k) => {
          const [tipo, texto] = SITUACAO[i.situacao] ?? ["conferir", i.situacao];
          const dia = ref_ === "dia" ? i.dia_esperado : i.vencimento;
          return (
            <tr key={k} style={{ borderTop: "1px solid var(--line2)" }}>
              <td>{i.pagador}{i.numero ? ` · nota ${i.numero}` : ""}</td><td>{dia ? dataCurta(dia) : "—"}</td><td><Valor valor={i.esperado} /></td>
              <td>{i.recebido ? <><Valor valor={i.recebido} />{i.recebido_em ? ` em ${dataCurta(i.recebido_em)}` : ""}
                {i.extrato?.descricao && <small style={{ display: "block", color: "var(--ink2)" }}>{i.extrato.descricao}{i.extrato.conta ? ` · ${i.extrato.conta}` : ""}</small>}</> : "—"}</td>
              <td><Etiqueta tipo={tipo} texto={i.situacao === "atrasado" && i.dias_atraso ? `${texto} · ${i.dias_atraso} dia(s)` : texto} /></td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

const resumo = (t: Totais) => `esperado ${Number(t.esperado).toLocaleString("pt-BR", { minimumFractionDigits: 2 })} · entrou ${Number(t.recebido).toLocaleString("pt-BR", { minimumFractionDigits: 2 })} · falta ${Number(t.falta).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`;

/** Cobrar › A receber: o que se espera receber no mês e se já entrou. Dois blocos, não somar (o pagador de uma nota pode ser também um recorrente do extrato). */
export function AReceber() {
  const leitura = useApi<Dados>("/api/v1/cobrar/a-receber");
  return (
    <Painel leitura={leitura} arquivo="a receber">
      {(d) => (
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <Bloco titulo="Quem costuma pagar todo mês" nota={resumo(d.totais.recorrentes)}>
            <section role="region" aria-label="Recebimentos recorrentes">
              {d.recorrentes.length ? <Tabela itens={d.recorrentes} ref_="dia" /> : <span>Nenhum pagador regular identificado no extrato.</span>}
            </section>
          </Bloco>
          <Bloco titulo="Notas fiscais do mês" nota={resumo(d.totais.notas)}>
            <section role="region" aria-label="Notas do mês">
              {d.notas.length ? <Tabela itens={d.notas} ref_="nota" /> : <span>Nenhuma nota com vencimento neste mês.</span>}
            </section>
          </Bloco>
          <span style={{ fontSize: 12.5, color: "var(--ink2)" }}>"Já entrou" = crédito visto no extrato (recorrentes) ou confirmado por você (notas). O Nibo é defasado: "pago" lá não conta como recebido.</span>
        </div>
      )}
    </Painel>
  );
}
