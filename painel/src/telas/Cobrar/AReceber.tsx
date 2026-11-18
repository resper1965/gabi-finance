import { Bloco } from "../../componentes/Bloco";
import { Etiqueta, type TipoEtiqueta } from "../../componentes/Etiqueta";
import { Vazio } from "../../componentes/Estados";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { api } from "../../lib/api";
import { dataCurta } from "../../lib/formato";
import { useToast } from "../../lib/toast";
import { useApi } from "../../lib/useApi";

interface PropostaManual { id: number; confianca: number; motivo: string; data: string; descricao: string | null; valor: string }
interface Item { pagador: string; situacao: string; esperado: string; recebido: string | null; recebido_em: string | null; dia_esperado?: string; vencimento?: string; numero?: string; dias_atraso?: number; extrato?: { descricao: string | null; conta?: string } | null; id?: number; conta?: string | null; observacao?: string | null; proposta?: PropostaManual | null }
interface Totais { esperado: string; recebido: string; falta: string; atrasado: string }
interface Dados { mes: string; recorrentes: Item[]; notas: Item[]; manuais: Item[]; totais: { recorrentes: Totais; notas: Totais; manuais: Totais } }

const SITUACAO: Record<string, [TipoEtiqueta, string]> = {
  recebido: ["ok", "Já entrou"], a_receber: ["parado", "Ainda não venceu"], atrasado: ["erro", "Atrasado"], nibo_diz_pago: ["conferir", "Nibo diz pago: conferir no extrato"], credito_provavel: ["conferir", "Crédito provável no extrato: confirme em Notas a receber"],
};

function Tabela({ itens, ref_ }: { itens: Item[]; ref_: "dia" | "nota" }) {
  return (
    <div className="tabela-rolagem"><table className="tabela">
      <thead><tr><th>Quem</th><th>{ref_ === "dia" ? "Dia costumeiro" : "Vence"}</th><th className="num">Esperado</th><th>Entrou no extrato</th><th>Situação</th></tr></thead>
      <tbody>
        {itens.map((i, k) => {
          const [tipo, texto] = SITUACAO[i.situacao] ?? ["conferir", i.situacao];
          const dia = ref_ === "dia" ? i.dia_esperado : i.vencimento;
          return (
            <tr key={k}>
              <td><span className="forte">{i.pagador}</span>{i.numero && <span className="celula-sub">nota <span className="mono">{i.numero}</span></span>}</td>
              <td className="mono">{dia ? dataCurta(dia) : "—"}</td><td className="num forte"><Valor valor={i.esperado} /></td>
              <td>{i.recebido ? <><Valor valor={i.recebido} />{i.recebido_em ? <> em <span className="mono">{dataCurta(i.recebido_em)}</span></> : ""}
                {i.extrato?.descricao && <span className="celula-sub">{i.extrato.descricao}{i.extrato.conta ? ` · ${i.extrato.conta}` : ""}</span>}</> : <span className="suave">—</span>}</td>
              <td><Etiqueta tipo={tipo} texto={i.situacao === "atrasado" && i.dias_atraso ? `${texto} · ${i.dias_atraso} dia(s)` : texto} /></td>
            </tr>
          );
        })}
      </tbody>
    </table></div>
  );
}

function TabelaManuais({ itens, recarregar }: { itens: Item[]; recarregar: () => void }) {
  const avisar = useToast();
  const enviar = async (req: () => Promise<unknown>, msg: string) => {
    try { await req(); avisar(msg); recarregar(); } catch (e) { avisar((e as Error).message); }
  };
  return (
    <div className="tabela-rolagem"><table className="tabela">
      <thead><tr><th>Quem</th><th>Vence</th><th className="num">Esperado</th><th>Entrou no extrato</th><th>Situação</th><th className="direita">Ação</th></tr></thead>
      <tbody>
        {itens.map((i) => {
          const [tipo, texto] = i.situacao === "credito_provavel" ? ["conferir", "Crédito provável: confirme aqui"] as [TipoEtiqueta, string] : SITUACAO[i.situacao] ?? ["conferir", i.situacao];
          const p = i.proposta;
          return (
            <tr key={i.id}>
              <td><span className="forte">{i.pagador}</span>{i.conta && <span className="celula-sub">{i.conta}</span>}{i.observacao && <span className="celula-sub">{i.observacao}</span>}</td>
              <td className="mono">{i.vencimento ? dataCurta(i.vencimento) : "—"}</td><td className="num forte"><Valor valor={i.esperado} /></td>
              <td>{i.recebido ? <><Valor valor={i.recebido} />{i.recebido_em ? <> em <span className="mono">{dataCurta(i.recebido_em)}</span></> : ""}
                {(i.extrato?.descricao ?? p?.descricao) && <span className="celula-sub">{i.extrato?.descricao ?? p?.descricao}{i.extrato?.conta ? ` · ${i.extrato.conta}` : ""}</span>}
                {p && <span className="celula-sub">{p.motivo} · confiança {Math.round(p.confianca * 100)}%</span>}</> : <span className="suave">—</span>}</td>
              <td><Etiqueta tipo={tipo} texto={texto} /></td>
              <td className="direita"><span className="fila" style={{ justifyContent: "flex-end", flexWrap: "nowrap" }}>
                {p && <>
                  <button className="btn btn-primary btn-sm" aria-label={`Confirmar crédito de ${i.pagador}`} onClick={() => enviar(() => api.post(`/api/v1/cobrar/a-receber-manual/propostas/${p.id}/confirmar`, {}), `Crédito de ${i.pagador} confirmado por você.`)}>Confirmar</button>
                  <button className="btn btn-sm" aria-label={`Rejeitar crédito de ${i.pagador}`} onClick={() => enviar(() => api.post(`/api/v1/cobrar/a-receber-manual/propostas/${p.id}/rejeitar`, {}), `Proposta de ${i.pagador} rejeitada.`)}>Rejeitar</button>
                </>}
                {i.situacao !== "recebido" && <button className="btn btn-ghost btn-sm" aria-label={`Cancelar a receber de ${i.pagador}`} onClick={() => enviar(() => api.post(`/api/v1/cobrar/a-receber-manual/${i.id}/cancelar`, {}), `A receber de ${i.pagador} cancelado.`)}>Cancelar</button>}
              </span></td>
            </tr>
          );
        })}
      </tbody>
    </table></div>
  );
}

const resumo = (t: Totais) => <>esperado <Valor valor={t.esperado} /> · entrou <Valor valor={t.recebido} /> · falta <Valor valor={t.falta} /></>;

/** Cobrar › A receber: o que se espera receber no mês e se já entrou. Dois blocos, não somar (o pagador de uma nota pode ser também um recorrente do extrato). */
export function AReceber() {
  const leitura = useApi<Dados>("/api/v1/cobrar/a-receber");
  return (
    <Painel leitura={leitura} arquivo="a receber">
      {(d) => (
        <div className="pilha" style={{ gap: 32, maxWidth: 1120 }}>
          <Bloco titulo="Quem costuma pagar todo mês" nota={resumo(d.totais.recorrentes)}>
            <section role="region" aria-label="Recebimentos recorrentes">
              {d.recorrentes.length ? <Tabela itens={d.recorrentes} ref_="dia" /> : <Vazio frase="Nenhum pagador regular identificado no extrato." />}
            </section>
          </Bloco>
          <Bloco titulo="Notas fiscais do mês" nota={resumo(d.totais.notas)}>
            <section role="region" aria-label="Notas do mês">
              {d.notas.length ? <Tabela itens={d.notas} ref_="nota" /> : <Vazio frase="Nenhuma nota com vencimento neste mês." />}
            </section>
          </Bloco>
          <Bloco titulo="Lançados por você" nota={resumo(d.totais.manuais)}>
            <section role="region" aria-label="Lançados por você">
              {d.manuais.length ? <TabelaManuais itens={d.manuais} recarregar={leitura.recarregar} /> : <Vazio frase="Nada lançado por você para este mês." />}
            </section>
          </Bloco>
          <p className="miudo" style={{ maxWidth: "75ch" }}>Valor negativo nos lançados por você é desconto ou adiantamento: abate o esperado. </p>
          <p className="miudo" style={{ maxWidth: "75ch" }}>"Já entrou" = crédito visto no extrato (recorrentes) ou confirmado por você (notas). O Nibo é defasado: "pago" lá não conta como recebido.</p>
        </div>
      )}
    </Painel>
  );
}
