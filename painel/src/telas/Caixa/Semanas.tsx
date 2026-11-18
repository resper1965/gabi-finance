import { useState } from "react";
import { Bloco } from "../../componentes/Bloco";
import { Achados } from "../../componentes/Achados";
import { Etiqueta } from "../../componentes/Etiqueta";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { BarrasSemanas, type Semana } from "../../graficos/BarrasSemanas";
import { dataCurta, num } from "../../lib/formato";
import { useOcultar } from "../../lib/ocultar";
import { FONTE } from "../../lib/proveniencia";
import { useApi } from "../../lib/useApi";

interface Lanc { id: number; data: string; estabelecimento: string; valor: string; conta: string; categoria: { nome: string | null } }

const soma = (l: { valor: string }[]) => l.reduce((s, i) => s + num(i.valor), 0);

export function Semanas() {
  const oculto = useOcultar();
  const leitura = useApi<{ semanas: Semana[] }>("/api/v1/caixa/semanas");
  const [inicio, setInicio] = useState<string | null>(null);
  const sem = leitura.env?.dados.semanas.find((s) => s.inicio === inicio);
  const lanc = useApi<{ itens: Lanc[] }>(sem && !sem.projecao ? `/api/v1/lancamentos?de=${sem.inicio}&ate=${sem.fim}&limite=200` : null);
  return (
    <Painel leitura={leitura} arquivo="extratos por semana">
      {(d) => {
        const reais = d.semanas.filter((s) => !s.projecao);
        const entradas = reais.reduce((s, w) => s + Math.abs(soma(w.entradas)), 0), saidas = reais.reduce((s, w) => s + Math.abs(soma(w.saidas)), 0);
        const ultima = d.semanas[d.semanas.length - 1];
        return (
          <div className="pilha" style={{ gap: 32, maxWidth: 1000 }}>
            <Achados itens={[
              { codigo: "SM-01", rotulo: "Entradas realizadas", fontes: [FONTE.extrato()], base: `créditos do extrato em ${reais.length} semanas`, valor: <Valor valor={entradas} /> },
              { codigo: "SM-02", rotulo: "Saídas realizadas", fontes: [FONTE.extrato()], base: `débitos do extrato em ${reais.length} semanas`, valor: <Valor valor={saidas} /> },
              { codigo: "SM-03", rotulo: "Líquido no período", fontes: [FONTE.extrato()], base: "entradas − saídas realizadas", valor: <Valor valor={entradas - saidas} />,
                carimbo: entradas - saidas < 0 ? { tipo: "erro", texto: "saiu mais" } : undefined },
              { codigo: "SM-04", rotulo: `Saldo projetado em ${d.semanas.filter((s) => s.projecao).length} semanas`, estado: "projecao", base: "saldo conferido + o que vence e o que deve entrar", fontes: [FONTE.extrato("saldo conferido de hoje"), FONTE.despesas(), FONTE.planilha("contas a pagar"), FONTE.notas("entradas previstas (notas a vencer)")],
                valor: ultima?.saldo ? <Valor valor={ultima.saldo} /> : <span className="suave">—</span> },
            ]} />
            <Bloco titulo="Entradas e saídas por semana" nota="clique numa semana (ou Enter sobre ela) para ver os lançamentos">
              <BarrasSemanas semanas={d.semanas} escolhida={inicio} aoEscolher={setInicio} oculto={oculto} />
            </Bloco>
            {sem && (
              <Bloco titulo={`Semana de ${dataCurta(sem.inicio)} a ${dataCurta(sem.fim)}`} acao={<button className="btn btn-sm" onClick={() => setInicio(null)}>Fechar</button>}
                nota={<>entradas <Valor valor={Math.abs(soma(sem.entradas))} /> · saídas <Valor valor={Math.abs(soma(sem.saidas))} /> · líquido <Valor valor={soma(sem.entradas) + soma(sem.saidas)} /></>}>
                {sem.projecao && <span className="fila miudo"><Etiqueta tipo="nota" texto="projeção" />semana futura: valores projetados, ainda não aconteceram</span>}
                <ul className="pauta">
                  {sem.projecao
                    ? [...sem.entradas, ...sem.saidas].map((i) => (
                        <li key={i.categoria + i.valor} className="linha-lanc">
                          <span /><span className="linha-titulo">{i.categoria}</span><span className="linha-valor"><Valor valor={i.valor} /></span>
                        </li>))
                    : (lanc.env?.dados.itens ?? []).map((l) => (
                        <li key={l.id} className="linha-lanc">
                          <span className="mono suave">{dataCurta(l.data)}</span>
                          <span style={{ minWidth: 0 }}><span className="linha-titulo">{l.estabelecimento}</span> <span className="miudo">· {l.categoria.nome ?? "sem categoria"} · {l.conta}</span></span>
                          <span className="linha-valor" style={{ color: num(l.valor) > 0 ? "var(--carimbo-verde)" : undefined }}><Valor valor={l.valor} /></span>
                        </li>))}
                </ul>
                {!sem.projecao && !lanc.env && <span className="esqueleto"><span className="esqueleto-linha" /><span className="esqueleto-linha" style={{ width: "70%" }} /></span>}
                {!sem.projecao && lanc.env && lanc.env.dados.itens.length === 0 && <p className="suave">Nenhum lançamento nesta semana.</p>}
              </Bloco>
            )}
          </div>
        );
      }}
    </Painel>
  );
}
