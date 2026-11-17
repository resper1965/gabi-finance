import { ClipboardList } from "lucide-react";
import { Achados } from "../../componentes/Achados";
import { Bloco } from "../../componentes/Bloco";
import { Etiqueta } from "../../componentes/Etiqueta";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { dataCurta, num } from "../../lib/formato";
import { useApi } from "../../lib/useApi";

interface Dia { dia: string; entradas: string; saidas: string; saldo: string }
interface Bloco_ { qtd: number; liquido: string }

/** Caixa › Previsão: saldo de hoje mais o que entra e sai dia a dia. Entrada só de nota a vencer e contrato recorrente; o que o Nibo
 *  mostra vencido e não baixado fica à parte (fila de conferência com o extrato) e nunca soma no saldo. */
export function Projecao() {
  const leitura = useApi<{ saldo_inicial: string; dias: Dia[]; menor_saldo: { dia: string; saldo: string }; aviso: string }>("/api/v1/caixa/projecao?dias=30");
  const previsao = useApi<{ a_confirmar: Bloco_; antigas: Bloco_ }>("/api/v1/cobrar/previsao");
  return (
    <Painel leitura={leitura} arquivo="previsão de caixa">
      {(d) => {
        const movimento = d.dias.filter((x, i) => i === 0 || Number(x.entradas) !== 0 || Number(x.saidas) !== 0);
        const fila = previsao.env?.dados;
        const fim = d.dias[d.dias.length - 1];
        const negativo = num(d.menor_saldo.saldo) < 0;
        return (
          <div className="pilha" style={{ gap: 32, maxWidth: 1120 }}>
            <Achados itens={[
              { codigo: "E-01", rotulo: "Saldo hoje", fonte: "open-finance", base: "saldo conferido de todas as contas do caixa único", valor: <Valor valor={d.saldo_inicial} />, prova: "ponto de partida da previsão" },
              { codigo: "E-02", rotulo: "Menor saldo", fonte: "open-finance", estado: "projecao", base: "o dia mais baixo da previsão", valor: <Valor valor={d.menor_saldo.saldo} />,
                prova: <>em <span className="mono">{dataCurta(d.menor_saldo.dia)}</span></>, carimbo: negativo ? { tipo: "erro", texto: "fica negativo" } : { tipo: "nota", texto: "projeção" } },
              { codigo: "E-03", rotulo: `Saldo em ${d.dias.length} dias`, fonte: "open-finance", estado: "projecao", base: "saldo de hoje + entradas previstas − saídas a pagar",
                valor: <Valor valor={fim?.saldo ?? d.saldo_inicial} />, prova: fim ? <>em <span className="mono">{dataCurta(fim.dia)}</span></> : undefined, carimbo: { tipo: "nota", texto: "projeção" } },
            ]} />
            <Bloco titulo="Saldo projetado por dia" nota="só os dias com entrada ou saída">
              <div className="tabela-rolagem">
                <table aria-label="Saldo projetado por dia" className="tabela">
                  <thead><tr><th scope="col">Dia</th><th scope="col" className="num">Entradas</th><th scope="col" className="num">Saídas</th><th scope="col" className="num">Saldo</th><th scope="col"><span className="sr-only">Marca</span></th></tr></thead>
                  <tbody>
                    {movimento.map((x) => {
                      const menor = x.dia === d.menor_saldo.dia;
                      return (
                        <tr key={x.dia}>
                          <td className="mono" style={{ color: "var(--tinta)" }}>{dataCurta(x.dia)}</td>
                          <td className="num" style={{ color: num(x.entradas) ? "var(--carimbo-verde)" : "var(--tinta-3)" }}><Valor valor={x.entradas} /></td>
                          <td className="num" style={{ color: num(x.saidas) ? undefined : "var(--tinta-3)" }}><Valor valor={x.saidas} /></td>
                          <td className="num forte" style={{ color: num(x.saldo) < 0 ? "var(--carimbo-vermelho)" : undefined }}><Valor valor={x.saldo} /></td>
                          <td style={{ width: 1 }}>{menor && <Etiqueta tipo={negativo ? "erro" : "nota"} texto="menor saldo" />}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Bloco>
            <section role="region" aria-label="Fila de conferência com o extrato" className="quadro" data-tom="conferir">
              <ClipboardList size={18} strokeWidth={1.7} aria-hidden="true" />
              <div className="pilha-curta" style={{ gap: 6 }}>
                <span className="fila"><strong>Fila de conferência com o extrato</strong><Etiqueta tipo="conferir" texto="fora da previsão" /></span>
                {fila ? (
                  <>
                    <span>{fila.a_confirmar.qtd} notas vencidas há até 60 dias e não baixadas no Nibo: <Valor valor={fila.a_confirmar.liquido} /></span>
                    <span>{fila.antigas.qtd} notas antigas (mais de 60 dias) sem baixa: <Valor valor={fila.antigas.liquido} /></span>
                  </>
                ) : <span className="esqueleto-linha" style={{ width: 280 }} />}
              </div>
            </section>
            <p className="miudo" style={{ maxWidth: "75ch" }}>{d.aviso}</p>
          </div>
        );
      }}
    </Painel>
  );
}
