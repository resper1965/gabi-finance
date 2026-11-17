import { ArrowRight } from "lucide-react";
import { Achados, type Achado } from "../../componentes/Achados";
import { Bloco } from "../../componentes/Bloco";
import { Vazio } from "../../componentes/Estados";
import { Etiqueta, type TipoEtiqueta } from "../../componentes/Etiqueta";
import { Evidencia } from "../../componentes/Evidencia";
import { Painel } from "../../componentes/Painel";
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

/** tipo de pendência → carimbo e a ação que a resolve */
const PENDENCIA: Record<string, [TipoEtiqueta, string, string]> = {
  atrasadas: ["erro", "atrasada", "Resolver em A pagar"], a_conferir: ["conferir", "a conferir", "Conferir em A pagar"],
  contas_a_decidir: ["conferir", "decidir", "Decidir em Cadastros"], sugestoes_pendentes: ["nota", "sugestão", "Revisar em Regras"],
};
const plural = (n: number, um: string, varios: string) => `${n} ${n === 1 ? um : varios}`;

/** Caixa › Resumo: a folha de rosto do laudo. Conclusão numa frase, achados numerados com prova, pendências com a ação de cada uma
 *  e o saldo com o ponto mais baixo marcado. */
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
        const horizonte = proj.length ? proj[proj.length - 1].data : null;
        const nPend = d.atencao.reduce((s, a) => s + a.quantidade, 0);
        const det = d.detalhe;
        const contas = det.saldo_por_conta;
        const negativas = contas.filter((c) => num(c.saldo) < 0);
        const fontesSaldo = `${plural(contas.length, "conta liberada", "contas liberadas")} no caixa único`;
        const evMenor = menor && (
          <Evidencia codigo="E-06" rotulo="Menor saldo projetado" fonte="open-finance" estado="projecao" base={`saldo conferido + contas a pagar e entradas previstas até ${dataCurta(horizonte!)}`}>
            <Valor valor={menor.valor} />
          </Evidencia>);
        const achados: Achado[] = [
          { codigo: "E-01", rotulo: "Saldo do caixa único", fonte: "open-finance", base: fontesSaldo, valor: <Valor valor={d.kpis.saldo} />,
            prova: contas.map((c, i) => <span key={`${c.apelido}-${i}`}>{i ? " · " : ""}{c.apelido} <Valor valor={c.saldo} /></span>),
            carimbo: negativas.length ? { tipo: "erro", texto: `${plural(negativas.length, "conta negativa", "contas negativas")}` } : undefined },
          { codigo: "E-02", rotulo: "A pagar em 7 dias", fonte: "open-finance", base: "planilha de compromissos, conferida com o extrato", valor: <Valor valor={d.kpis.a_pagar_7_dias} />,
            prova: `${plural(det.a_pagar_contas, "conta", "contas")} · inclui vencidas`,
            carimbo: det.a_pagar_vencidas ? { tipo: "erro", texto: plural(det.a_pagar_vencidas, "vencida", "vencidas") } : undefined,
            acao: { rotulo: "A pagar", fazer: () => ir("caixa", "contas") } },
          { codigo: "E-03", rotulo: "A receber das empresas", fonte: "notas-nibo", base: "notas fiscais do Nibo", estado: d.kpis.a_receber === null ? "a_conferir" : undefined,
            valor: d.kpis.a_receber === null ? <span className="suave">—</span> : <Valor valor={d.kpis.a_receber} />,
            prova: d.kpis.a_receber === null ? "aparece quando o Nibo estiver ligado" : "notas a vencer, líquidas",
            carimbo: d.kpis.a_receber === null ? { tipo: "parado", texto: "sem fonte" } : undefined,
            acao: { rotulo: "A receber", fazer: () => ir("cobrar", "areceber") } },
          { codigo: "E-04", rotulo: "Fatura aberta · cartões", fonte: "open-finance", base: "faturas abertas dos cartões liberados", valor: <Valor valor={d.kpis.faturas_abertas} />,
            prova: `${plural(det.cartoes_abertos, "cartão", "cartões")}${det.proxima_fatura ? ` · a próxima vence em ${dataCurta(det.proxima_fatura)}` : ""}`,
            acao: { rotulo: "Cartões", fazer: () => ir("gastos", "cartao") } },
          { codigo: "E-05", rotulo: "Assinaturas por mês", fonte: "open-finance", base: "débitos recorrentes detectados no extrato", valor: <Valor valor={d.kpis.assinaturas_mes} />,
            prova: `${plural(det.assinaturas_ativas, "ativa", "ativas")} · ${det.assinaturas_a_conferir} a conferir`,
            carimbo: det.assinaturas_a_conferir ? { tipo: "conferir", texto: `${det.assinaturas_a_conferir} a conferir` } : undefined,
            acao: { rotulo: "Assinaturas", fazer: () => ir("gastos", "assin") } },
        ];
        if (menor) achados.push({ codigo: "E-06", rotulo: "Menor saldo projetado", fonte: "open-finance", estado: "projecao",
          base: `saldo conferido + contas a pagar e entradas previstas até ${dataCurta(horizonte!)}`, valor: <Valor valor={menor.valor} />,
          prova: `em ${dataCurta(menor.data)} · projeção até ${dataCurta(horizonte!)}`,
          carimbo: num(menor.valor) < 0 ? { tipo: "erro", texto: "fica negativo" } : { tipo: "nota", texto: "projeção" } });

        return (
          <div className="resumo">
            <div className="resumo-conclusao">
              <p className="conclusao">
                <strong>Conclusão.</strong>{" "}
                {menor
                  ? num(menor.valor) < 0
                    ? <>Falta caixa: o saldo projetado fica negativo, {evMenor}, em {dataCurta(menor.data)}.</>
                    : <>Há caixa até {dataCurta(horizonte!)}. O ponto mais baixo projetado é {evMenor}, em {dataCurta(menor.data)}.</>
                  : num(d.kpis.saldo) < 0 ? <>O caixa está negativo hoje.</> : <>Há caixa hoje; não há projeção para os próximos dias.</>}
                {" "}<span className="conclusao-resto">{nPend > 0 ? `${plural(nPend, "pendência pede", "pendências pedem")} você.` : "Nada pede você agora."}</span>
              </p>
            </div>

            <aside className="resumo-lateral">
            <div className="resumo-pendencias">
              <Bloco titulo="Pendências" nota={nPend ? plural(nPend, "item", "itens") : undefined}>
                {d.atencao.length === 0 && <Vazio frase="Nada pede você agora. Eu aviso quando surgir." />}
                {d.atencao.length > 0 && (
                  <ol className="pauta pendencias">
                    {d.atencao.map((a) => {
                      const [tipo, carimbo, acao] = PENDENCIA[a.tipo] ?? ["conferir", "ver", "Abrir"];
                      const [area, aba] = rotaParaTela(a.rota);
                      return (
                        <li key={a.tipo} className="pilha-curta">
                          <span className="fila"><Etiqueta tipo={tipo} texto={carimbo} /></span>
                          <span className="linha-titulo">{a.texto}</span>
                          <span><button className="btn btn-primary btn-sm" onClick={() => ir(area, aba)}>{acao}<ArrowRight size={14} strokeWidth={1.8} aria-hidden="true" /></button></span>
                        </li>
                      );
                    })}
                  </ol>)}
              </Bloco>
            </div>

            <div className="resumo-grafico">
              <Bloco titulo="Saldo do caixa único" nota={`${d.serie_saldo.filter((p) => !p.projecao).length} dias · ${proj.length} projetado${proj.length === 1 ? "" : "s"}`}>
                <LinhaSaldo pontos={d.serie_saldo} oculto={oculto} largura={380} altura={240} />
                <div className="legenda">
                  <span><span className="amostra-traco" />realizado</span>
                  <span><span className="amostra-traco" style={{ borderTop: "2px dashed var(--acento)" }} />projeção</span>
                </div>
              </Bloco>
            </div>
            </aside>

            <div className="resumo-achados"><Achados itens={achados} /></div>

            <div className="resumo-bancos">
              <Bloco titulo="Saldo por banco" nota="cada conta separada: o total pode esconder uma conta negativa">
                <table className="tabela">
                  <thead><tr><th scope="col">Conta</th><th scope="col"><span className="sr-only">Estado</span></th><th scope="col" className="num">Saldo</th></tr></thead>
                  <tbody>
                    {[...contas].sort((a, b) => num(b.saldo) - num(a.saldo)).map((c, i) => (
                      <tr key={`${c.apelido}-${i}`}>
                        <td className="forte">{c.apelido}</td>
                        <td>{num(c.saldo) < 0 && <Etiqueta tipo="erro" texto="negativo" />}</td>
                        <td className="num forte" style={{ color: num(c.saldo) < 0 ? "var(--carimbo-vermelho)" : undefined }}><Valor valor={c.saldo} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Bloco>
            </div>
          </div>
        );
      }}
    </Painel>
  );
}
