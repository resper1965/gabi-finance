import { ArrowRight } from "lucide-react";
import { Achados, type Achado } from "../../componentes/Achados";
import { Bloco } from "../../componentes/Bloco";
import { Vazio } from "../../componentes/Estados";
import { Etiqueta, type TipoEtiqueta } from "../../componentes/Etiqueta";
import { Evidencia, type InfoEvidencia } from "../../componentes/Evidencia";
import { formatarDadosAte, formatarHora } from "../../componentes/Faixa";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { LinhaSaldo, type Ponto } from "../../graficos/LinhaSaldo";
import { useFiltros } from "../../lib/filtros";
import { dataCurta, num } from "../../lib/formato";
import { useIr, useOcultar } from "../../lib/ocultar";
import { FONTE, useProveniencia } from "../../lib/proveniencia";
import { useApi } from "../../lib/useApi";
import { rotaParaTela } from "../../navegacao";

interface Resumo {
  kpis: { saldo: string; a_pagar_7_dias: string; a_receber: string | null; faturas_abertas: string; assinaturas_mes: string };
  detalhe: { saldo_por_conta: { apelido: string; saldo: string }[]; a_pagar_contas: number; a_pagar_vencidas: number; cartoes_abertos: number;
             proxima_fatura: string | null; assinaturas_ativas: number; assinaturas_a_conferir: number };
  serie_saldo: Ponto[];
  atencao: { tipo: string; quantidade: number; texto: string; rota: string }[];
}
interface Rodada { id: number; fonte: string; fim: string | null; conferida: boolean }

/** tipo de pendência → carimbo (no feminino: conta, sugestão) e a ação que a resolve */
const PENDENCIA: Record<string, [TipoEtiqueta, string, string]> = {
  atrasadas: ["erro", "atrasada", "Resolver em A pagar"], a_conferir: ["conferir", "a conferir", "Conferir em A pagar"],
  contas_a_decidir: ["conferir", "a decidir", "Decidir em Cadastros"], sugestoes_pendentes: ["nota", "a revisar", "Revisar em Regras"],
};
const plural = (n: number, um: string, varios: string) => `${n} ${n === 1 ? um : varios}`;

/** Linha de atestado sob a conclusão: qual rodada de extrato conferiu os números (do envelope e da lista de rodadas). */
function Atestado() {
  const prov = useProveniencia();
  const rodada = (useApi<{ itens: Rodada[] }>("/api/v1/rodadas?limite=20").env?.dados.itens ?? []).find((r) => r.fonte === "open-finance" && r.conferida);
  if (!prov?.dadosAte) return <p className="atestado">Nenhuma rodada conferida ainda: os números abaixo estão a conferir.</p>;
  return (
    <p className="atestado">
      {prov.desatualizado ? "Dados desatualizados" : "Conferido contra o extrato"}: {rodada ? <>rodada <span className="mono">#{rodada.id}</span>, </> : null}dados até <span className="mono">{formatarDadosAte(prov.dadosAte)}</span>
      {" "}· fontes {prov.fontes.map((f) => f.nome).join(", ")}{prov.proximaRodada ? <> · próxima rodada às {formatarHora(prov.proximaRodada)}</> : null}.
    </p>
  );
}

/** Caixa › Resumo: a folha de rosto do laudo. Conclusão numa frase, achados numerados com prova, pendências com a ação de cada uma
 *  e o saldo com o ponto mais baixo marcado. Os códigos RS- citam os itens das outras telas que cada número soma. */
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
        const evMenor: InfoEvidencia | null = menor && {
          codigo: "RS-06", rotulo: "Menor saldo projetado", estado: "projecao", cita: "PV-02",
          fontes: [FONTE.extrato("saldo conferido de hoje"), FONTE.despesas("saídas previstas"), FONTE.planilha("contas a pagar"), FONTE.notas("entradas previstas (notas a vencer)")],
          base: `o dia mais baixo até ${dataCurta(horizonte!)}`,
        };
        const achados: Achado[] = [
          { codigo: "RS-01", rotulo: "Saldo do caixa único", cita: "PV-01", fontes: [FONTE.extrato(`saldo de ${plural(contas.length, "conta liberada", "contas liberadas")}`)],
            valor: <Valor valor={d.kpis.saldo} />,
            prova: contas.map((c, i) => <span key={`${c.apelido}-${i}`}>{i ? " · " : ""}{c.apelido} <Valor valor={c.saldo} /></span>),
            carimbo: negativas.length ? { tipo: "erro", texto: plural(negativas.length, "conta negativa", "contas negativas") } : undefined },
          { codigo: "RS-02", rotulo: "A pagar em 7 dias", cita: "AP-01 + AP-02 + AP-03", fontes: [FONTE.planilha(), FONTE.extrato("conferência dos pagamentos")],
            valor: <Valor valor={d.kpis.a_pagar_7_dias} />, prova: `${plural(det.a_pagar_contas, "conta", "contas")} · inclui vencidas`,
            carimbo: det.a_pagar_vencidas ? { tipo: "erro", texto: plural(det.a_pagar_vencidas, "vencida", "vencidas") } : undefined,
            acao: { rotulo: "A pagar", fazer: () => ir("caixa", "contas") } },
          { codigo: "RS-03", rotulo: "A receber das empresas", cita: "NT-01", fontes: [FONTE.notas("notas a vencer, líquidas")],
            estado: d.kpis.a_receber === null ? "a_conferir" : undefined,
            valor: d.kpis.a_receber === null ? <span className="suave">—</span> : <Valor valor={d.kpis.a_receber} />,
            prova: d.kpis.a_receber === null ? "sem valor: aparece quando o Nibo estiver ligado" : "notas a vencer, líquidas",
            acao: { rotulo: "A receber", fazer: () => ir("cobrar", "areceber") } },
          { codigo: "RS-04", rotulo: "Fatura aberta · cartões", cita: "CT-01…", fontes: [FONTE.extrato("faturas abertas dos cartões liberados")], valor: <Valor valor={d.kpis.faturas_abertas} />,
            prova: `${plural(det.cartoes_abertos, "cartão", "cartões")}${det.proxima_fatura ? ` · a próxima vence em ${dataCurta(det.proxima_fatura)}` : ""}`,
            acao: { rotulo: "Cartões", fazer: () => ir("gastos", "cartao") } },
          { codigo: "RS-05", rotulo: "Assinaturas por mês", cita: "AS-01", fontes: [FONTE.extrato("débitos recorrentes detectados")], valor: <Valor valor={d.kpis.assinaturas_mes} />,
            prova: `${plural(det.assinaturas_ativas, "ativa", "ativas")} · ${det.assinaturas_a_conferir} a conferir`,
            acao: { rotulo: "Assinaturas", fazer: () => ir("gastos", "assin") } },
        ];
        if (menor && evMenor) achados.push({ ...evMenor, valor: <Valor valor={menor.valor} />,
          prova: `em ${dataCurta(menor.data)} · projeção até ${dataCurta(horizonte!)}`,
          carimbo: num(menor.valor) < 0 ? { tipo: "erro", texto: "fica negativo" } : undefined });

        const evConclusao = menor && evMenor && <Evidencia {...evMenor}><Valor valor={menor.valor} /></Evidencia>;
        return (
          <div className="resumo">
            <div className="resumo-conclusao">
              <p className="conclusao">
                <strong>Conclusão.</strong>{" "}
                {menor
                  ? num(menor.valor) < 0
                    ? <>Falta caixa: o saldo projetado fica negativo, {evConclusao}, em {dataCurta(menor.data)}.</>
                    : <>Há caixa até {dataCurta(horizonte!)}. O ponto mais baixo projetado é {evConclusao}, em {dataCurta(menor.data)}.</>
                  : num(d.kpis.saldo) < 0 ? <>O caixa está negativo hoje.</> : <>Há caixa hoje; não há projeção para os próximos dias.</>}
                {" "}<span className="conclusao-resto">{nPend > 0 ? `${plural(nPend, "pendência pede", "pendências pedem")} você.` : "Nada pede você agora."}</span>
              </p>
              <Atestado />
            </div>

            <div className="resumo-achados"><Achados itens={achados} /></div>

            <aside className="resumo-lateral">
              <div className="resumo-pendencias">
                <Bloco titulo="Pendências" nota={nPend ? plural(nPend, "item", "itens") : undefined}>
                  {d.atencao.length === 0 && <Vazio frase="Nada pede você agora. Eu aviso quando surgir." />}
                  {d.atencao.length > 0 && (
                    <ol className="pauta pendencias">
                      {d.atencao.map((a) => {
                        const [tipo, carimbo, acao] = PENDENCIA[a.tipo] ?? ["conferir", "a ver", "Abrir"];
                        const [area, aba] = rotaParaTela(a.rota);
                        return (
                          <li key={a.tipo} className="pilha-curta">
                            <span className="fila" style={{ gap: "4px 8px" }}><span className="linha-titulo">{a.texto}</span><Etiqueta tipo={tipo} texto={carimbo} /></span>
                            <span><button className="btn btn-primary btn-sm" onClick={() => ir(area, aba)}>{acao}<ArrowRight size={14} strokeWidth={1.8} aria-hidden="true" /></button></span>
                          </li>
                        );
                      })}
                    </ol>)}
                </Bloco>
              </div>

              <div className="resumo-grafico">
                <Bloco titulo="Saldo do caixa único" nota={`${d.serie_saldo.filter((p) => !p.projecao).length} dias · ${proj.length} projetado${proj.length === 1 ? "" : "s"}`}>
                  <LinhaSaldo pontos={d.serie_saldo} oculto={oculto} largura={380} altura={250} evidencia={evMenor ?? undefined} />
                  <div className="legenda">
                    <span><span className="amostra-traco" />realizado</span>
                    <span><span className="amostra-traco" style={{ borderTop: "2px dashed var(--acento)" }} />projeção</span>
                  </div>
                </Bloco>
              </div>
            </aside>

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
