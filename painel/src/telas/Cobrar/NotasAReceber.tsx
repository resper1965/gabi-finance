import { Bloco } from "../../componentes/Bloco";
import { Etiqueta, type TipoEtiqueta } from "../../componentes/Etiqueta";
import { Evidencia } from "../../componentes/Evidencia";
import { Vazio } from "../../componentes/Estados";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { api } from "../../lib/api";
import { dataCurta } from "../../lib/formato";
import { useToast } from "../../lib/toast";
import { useApi } from "../../lib/useApi";

interface Nota { numero: string; tomador: string; emissao: string; vencimento: string | null; bruto: string; liquido: string; situacao: string; nibo_pago: boolean; pdf: boolean; xml: boolean }
interface Proposta { id: number; confianca: number; motivo: string; nota: { numero: string; tomador: string; vencimento: string | null; liquido: string }; lancamento: { id: number; data: string; descricao: string | null; valor: string } }
interface Totais { a_vencer: string; a_confirmar: string; antigas: string; nibo_diz_pago: string; recebidas: string }

const GRUPOS: [string, string, keyof Totais, [TipoEtiqueta, string] | null][] = [
  ["a_vencer", "A receber (notas a vencer)", "a_vencer", null],
  ["a_confirmar", "Vencidas: confirmar pelo extrato", "a_confirmar", ["conferir", "a conferir"]],
  ["antiga", "Antigas (mais de 60 dias, provável baixa que faltou no Nibo)", "antigas", ["erro", "atrasada"]],
  ["nibo_diz_pago", "O Nibo diz pago (não é prova de recebimento)", "nibo_diz_pago", null],
  ["recebida", "Recebidas (confirmadas por você no extrato)", "recebidas", ["ok", "recebida"]],
];

/** Cobrar › Notas a receber: as NFS-e do Nibo. O Nibo é defasado: "pago" lá não vira "recebido" aqui; o recebimento real é o crédito no extrato. */
export function NotasAReceber() {
  const leitura = useApi<{ itens: Nota[]; totais: Totais }>("/api/v1/cobrar/notas");
  const propostas = useApi<{ itens: Proposta[] }>("/api/v1/cobrar/recebimentos");
  const avisar = useToast();
  const decidir = async (p: Proposta, acao: "confirmar" | "rejeitar") => {
    try {
      await api.post(acao === "confirmar" ? `/api/v1/cobrar/recebimentos/${p.id}/confirmar` : `/api/v1/cobrar/recebimentos/${p.id}/rejeitar`, {});
      avisar(acao === "confirmar" ? `Recebimento da nota ${p.nota.numero} confirmado por você.` : `Proposta da nota ${p.nota.numero} rejeitada.`);
      propostas.recarregar(); leitura.recarregar();
    } catch (e) { avisar((e as Error).message); }
  };
  const lista = propostas.env?.dados.itens ?? [];
  return (
    <Painel leitura={leitura} arquivo="notas a receber">
      {(d) => (
        <div className="pilha" style={{ gap: 32, maxWidth: 1120 }}>
          {lista.length > 0 && (
            <section role="region" aria-label="Recebimentos propostos" className="secao">
              <div className="secao-cab"><span className="fila" style={{ gap: 10 }}><h2>Recebimentos propostos</h2><Etiqueta tipo="conferir" texto={`${lista.length} a conferir`} /></span>
                <span className="secao-nota">crédito no extrato que bate com uma nota; só vira recebido com o seu clique</span></div>
              <ul className="pauta">
                {lista.map((p) => (
                  <li key={p.id} className="linha-item">
                    <span className="pilha-curta" style={{ gap: 3 }}>
                      <span><span className="forte">Nota <span className="mono">{p.nota.numero}</span> · {p.nota.tomador}</span> · líquido <Valor valor={p.nota.liquido} /></span>
                      <span className="miudo">no extrato: {p.lancamento.descricao} em <span className="mono">{dataCurta(p.lancamento.data)}</span> (<Valor valor={p.lancamento.valor} />)</span>
                      <span className="miudo">{p.motivo} · confiança {Math.round(p.confianca * 100)}%</span>
                    </span>
                    <span className="fila">
                      <button className="btn btn-primary btn-sm" aria-label={`Confirmar recebimento da nota ${p.nota.numero}`} onClick={() => decidir(p, "confirmar")}>Confirmar</button>
                      <button className="btn btn-sm" aria-label={`Rejeitar recebimento da nota ${p.nota.numero}`} onClick={() => decidir(p, "rejeitar")}>Rejeitar</button>
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {!GRUPOS.some(([sit]) => d.itens.some((n) => n.situacao === sit)) && <Vazio frase="Nenhuma nota a receber. As NFS-e do Nibo aparecem aqui assim que a rodada de notas rodar." />}
          {GRUPOS.map(([sit, titulo, chave, carimbo], k) => {
            const itens = d.itens.filter((n) => n.situacao === sit);
            if (itens.length === 0) return null;
            return (
              <Bloco key={sit} titulo={titulo} nota={<>{itens.length} {itens.length === 1 ? "nota" : "notas"} · líquido <Evidencia codigo={`E-${String(k + 1).padStart(2, "0")}`} rotulo={titulo} fonte="notas-nibo" base="soma do líquido das notas do grupo" estado={sit === "recebida" ? "conferido" : sit === "a_vencer" ? undefined : "a_conferir"}><Valor valor={d.totais[chave]} /></Evidencia></>}>
                <section role="region" aria-label={sit === "a_vencer" ? "A receber" : titulo} className="tabela-rolagem">
                  <table className="tabela">
                    <thead><tr><th>Nota</th><th>Tomador</th><th>Vence</th><th className="num">Bruto</th><th className="num">Líquido</th><th><span className="sr-only">Estado</span></th></tr></thead>
                    <tbody>
                      {itens.map((n) => (
                        <tr key={n.numero + n.tomador}>
                          <td className="mono" style={{ color: "var(--tinta)" }}>{n.numero}</td><td className="forte">{n.tomador}</td><td className="mono">{n.vencimento ? dataCurta(n.vencimento) : "—"}</td>
                          <td className="num suave"><Valor valor={n.bruto} /></td><td className="num forte"><Valor valor={n.liquido} /></td>
                          <td>{n.nibo_pago && <Etiqueta tipo="conferir" texto="Nibo diz pago" />}{carimbo && !n.nibo_pago && <Etiqueta tipo={carimbo[0]} texto={carimbo[1]} />}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </section>
              </Bloco>
            );
          })}
          <p className="miudo" style={{ maxWidth: "75ch" }}>Valores líquidos, depois das retenções. Recebimento de verdade = crédito no extrato do banco; a conciliação por valor chega com o extrato conferido.</p>
        </div>
      )}
    </Painel>
  );
}
