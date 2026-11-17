import { useState } from "react";
import { X } from "lucide-react";
import { Bloco } from "../../componentes/Bloco";
import { Evidencia } from "../../componentes/Evidencia";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { Vazio } from "../../componentes/Estados";
import { corDestino, type Fluxo, type No } from "../../graficos/fluxo";
import { useFiltros } from "../../lib/filtros";
import { dataCurta, num } from "../../lib/formato";
import { useApi } from "../../lib/useApi";

interface Destino {
  periodo: { de: string; ate: string }; nos: No[]; fluxos: Fluxo[]; total: string;
  comparacao: { categoria: string; atual: string; anterior: string; variacao: string }[];
}
interface Agrupado { itens: { nome: string; valor: string; pct: number; variacao: string }[]; total: string }
type Vista = "categoria" | "fornecedor" | "gastador" | "pessoa";
const ROTULO: Record<Vista, string> = { categoria: "Categorias", fornecedor: "Fornecedores", gastador: "Quem gastou", pessoa: "Para quem foi" };
const NOTA: Record<Vista, string> = {
  categoria: "para onde foi o dinheiro, por categoria", fornecedor: "maiores fornecedores do período",
  gastador: "quem passou o cartão (o portador); nos cartões compartilhados é você quem indica", pessoa: "categoria diz o quê, \"para quem\" diz de quem é o gasto",
};
const MES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
const ROTULO_PERIODO: Record<string, string> = { semana: "Nos últimos 7 dias", "12m": "Nos últimos 12 meses" };
const pct = (a: number, b: number) => (b ? `${Math.round((a / b) * 100)}%` : "0%");

export function ParaOndeVai() {
  const { periodo } = useFiltros();
  const [vista, setVista] = useState<Vista>("categoria");
  const [escolhido, setEscolhido] = useState<{ nome: string; tipo: string } | null>(null);
  const destino = useApi<Destino>(`/api/v1/destino?periodo=${periodo}`);
  const agrupado = useApi<Agrupado>(`/api/v1/destino/agrupado?periodo=${periodo}&por=${vista}`);
  const categorias = useApi<{ itens: { id: number; nome: string }[] }>("/api/v1/cadastros/categorias").env?.dados.itens ?? [];
  const empresas = useApi<{ itens: { id: string | number; nome: string }[] }>("/api/v1/cadastros/empresas").env?.dados.itens ?? [];
  const pessoas = useApi<{ itens: { id: string | number; nome: string }[] }>("/api/v1/cadastros/pessoas").env?.dados.itens ?? [];
  let filtro: string | null = null;
  if (escolhido) {
    const emp = empresas.find((e) => escolhido.nome === `A receber: ${e.nome}`);
    const cat = categorias.find((c) => c.nome === escolhido.nome);
    const pes = escolhido.tipo === "pessoa" ? pessoas.find((x) => x.nome === escolhido.nome) : undefined;
    const gas = escolhido.tipo === "gastador" ? pessoas.find((x) => x.nome === escolhido.nome) : undefined;
    filtro = escolhido.tipo === "gastador" ? (gas ? `gastador=${gas.id}` : escolhido.nome === "(a indicar)" ? "pendente=gastador" : null) : escolhido.tipo === "origem" ? `conta=${encodeURIComponent(escolhido.nome)}` : pes ? `para_quem=${pes.id}` : emp ? `empresa=${emp.id}` : cat ? `categoria=${cat.id}` : `texto=${encodeURIComponent(escolhido.nome)}`;
  }
  const lanc = useApi<{ itens: { id: number; data: string; estabelecimento: string; valor: string; conta: string; categoria: { nome: string | null } }[] }>(
    filtro && destino.env ? `/api/v1/lancamentos?${filtro}&de=${destino.env.dados.periodo.de}&ate=${destino.env.dados.periodo.ate}&limite=50` : null);

  return (
    <Painel leitura={destino} arquivo="custos do período">
      {(d) => {
        const total = num(d.total);
        const destinos = d.nos.filter((n) => n.tipo === "destino").map((n) => ({ nome: n.nome, valor: d.fluxos.filter((f) => f.para === n.nome).reduce((s, f) => s + num(f.valor), 0) })).sort((a, b) => b.valor - a.valor);
        const pessoal = destinos.find((x) => x.nome === "Consumo pessoal")?.valor ?? 0;
        const quando = periodo === "mes" ? `Em ${MES[Number(d.periodo.de.slice(5, 7)) - 1]}` : ROTULO_PERIODO[periodo];
        const sobe = d.comparacao.filter((c) => num(c.variacao) > 0).sort((a, b) => num(b.variacao) - num(a.variacao));
        const cai = d.comparacao.filter((c) => num(c.variacao) < 0).sort((a, b) => num(a.variacao) - num(b.variacao));
        const itens = agrupado.env?.dados.itens ?? [];
        const linha = (c: Destino["comparacao"][number], cor: string) => (
          <tr key={c.categoria}>
            <td><span className="forte">{c.categoria}</span><span className="celula-sub"><Valor valor={c.anterior} /> antes, <Valor valor={c.atual} /> agora</span></td>
            <td className="num"><Valor valor={c.variacao} /></td>
            <td className="num mono" style={{ color: cor, width: 64 }}>{num(c.anterior) ? `${num(c.variacao) > 0 ? "+" : ""}${Math.round((num(c.variacao) / num(c.anterior)) * 100)}%` : "novo"}</td>
          </tr>
        );
        return (
          <div className="pilha" style={{ gap: 32, maxWidth: 1120 }}>
            <div className="fila-entre" style={{ alignItems: "flex-end", gap: 20 }}>
              <p className="sentenca" style={{ maxWidth: "36em" }}>
                {quando} saiu <Evidencia codigo="E-01" rotulo="Total que saiu" fonte="open-finance" base={`débitos de ${dataCurta(d.periodo.de)} a ${dataCurta(d.periodo.ate)}`}><Valor valor={d.total} /></Evidencia>.{" "}
                {pct(pessoal, total)} é consumo seu (<Evidencia codigo="E-02" rotulo="Consumo pessoal" fonte="open-finance" base="gastos sem empresa de reembolso"><Valor valor={pessoal} /></Evidencia>); o resto, <Valor valor={total - pessoal} />, é das empresas e volta como reembolso.
              </p>
              <div role="group" aria-label="Visualização" className="seg">
                {(Object.keys(ROTULO) as Vista[]).map((v) => (
                  <button key={v} className="seg-opt" aria-pressed={vista === v} onClick={() => { setVista(v); setEscolhido(null); }}>{ROTULO[v]}</button>
                ))}
              </div>
            </div>

            <Bloco titulo="Para quem vai" nota="consumo seu e o que cada empresa devolve; escolha uma linha para ver os lançamentos">
              <div className="barra-composta" aria-hidden="true">
                {destinos.map((x) => <span key={x.nome} style={{ flexGrow: x.valor, background: corDestino(x.nome) }} title={x.nome} />)}
              </div>
              <table className="tabela">
                <thead><tr><th scope="col">Destino</th><th scope="col" className="num">Valor</th><th scope="col" className="num">Parte</th></tr></thead>
                <tbody>
                  {destinos.map((x) => (
                    <tr key={x.nome} data-marcado={escolhido?.nome === x.nome}>
                      <td><button className="link-linha" onClick={() => setEscolhido({ nome: x.nome, tipo: "destino" })}><span className="amostra-cor" style={{ background: corDestino(x.nome) }} />{x.nome}</button></td>
                      <td className="num forte"><Valor valor={x.valor} /></td>
                      <td className="num mono suave">{pct(x.valor, total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Bloco>

            <Bloco titulo={ROTULO[vista]} nota={<>{NOTA[vista]} · escolha uma linha para ver os lançamentos</>}>
              {!agrupado.env && <div className="esqueleto"><span className="esqueleto-linha" /><span className="esqueleto-linha" style={{ width: "80%" }} /><span className="esqueleto-linha" style={{ width: "60%" }} /></div>}
              {agrupado.env && itens.length === 0 && <Vazio frase="Nada saiu neste período." />}
              {agrupado.env && itens.length > 0 && (
                <ol className="pauta ranking">
                  {itens.map((r, i) => (
                    <li key={r.nome} data-marcado={escolhido?.nome === r.nome}>
                      <button className="ranking-linha" onClick={() => setEscolhido({ nome: r.nome, tipo: vista === "categoria" ? "categoria" : vista === "fornecedor" ? "texto" : vista })}>
                        <span className="mono suave">{String(i + 1).padStart(2, "0")}</span>
                        <span className="pilha-curta" style={{ gap: 6 }}>
                          <span className="linha-titulo">{r.nome}</span>
                          <span className="barra-fina"><span style={{ width: `${Math.min(100, r.pct)}%` }} /></span>
                        </span>
                        <span className="linha-valor"><Valor valor={r.valor} /><span className="celula-sub mono">{r.pct.toLocaleString("pt-BR")}%</span></span>
                      </button>
                    </li>
                  ))}
                </ol>)}
            </Bloco>

            {escolhido && (
              <Bloco titulo={escolhido.nome} nota={lanc.env ? `${lanc.env.dados.itens.length} lançamentos · maiores primeiro` : "lendo os lançamentos…"}
                acao={<button className="btn btn-sm" onClick={() => setEscolhido(null)}><X size={14} strokeWidth={1.8} aria-hidden="true" />Limpar seleção</button>}>
                {!lanc.env && <div className="esqueleto"><span className="esqueleto-linha" /><span className="esqueleto-linha" style={{ width: "70%" }} /></div>}
                {lanc.env && lanc.env.dados.itens.length === 0 && <Vazio frase="Nenhum lançamento com esse filtro no período." />}
                {lanc.env && (
                  <ul className="pauta">
                    {[...lanc.env.dados.itens].sort((a, b) => Math.abs(num(b.valor)) - Math.abs(num(a.valor))).map((i) => (
                      <li key={i.id} className="linha-lanc">
                        <span className="mono suave">{dataCurta(i.data)}</span>
                        <span style={{ minWidth: 0 }}><span className="linha-titulo">{i.estabelecimento}</span> <span className="miudo">· {i.categoria.nome ?? "sem categoria"} · {i.conta}</span></span>
                        <span className="linha-valor"><Valor valor={i.valor} /></span>
                      </li>
                    ))}
                  </ul>)}
              </Bloco>
            )}

            <div className="grade-2">
              <Bloco titulo="Subiu em relação ao período anterior">
                {sobe.length ? <table className="tabela"><tbody>{sobe.map((c) => linha(c, "var(--carimbo-vermelho)"))}</tbody></table> : <p className="suave">Nenhuma categoria subiu.</p>}
              </Bloco>
              <Bloco titulo="Caiu">
                {cai.length ? <table className="tabela"><tbody>{cai.map((c) => linha(c, "var(--carimbo-verde)"))}</tbody></table> : <p className="suave">Nenhuma categoria caiu.</p>}
              </Bloco>
            </div>
          </div>
        );
      }}
    </Painel>
  );
}
