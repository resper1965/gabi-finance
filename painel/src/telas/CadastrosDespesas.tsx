import { useState } from "react";
import { Plus } from "lucide-react";
import { Bloco } from "../componentes/Bloco";
import { Etiqueta } from "../componentes/Etiqueta";
import { Vazio } from "../componentes/Estados";
import { Painel } from "../componentes/Painel";
import { Valor } from "../componentes/Valor";
import { api } from "../lib/api";
import { dataCurta, mesCurto } from "../lib/formato";
import { useToast } from "../lib/toast";
import { useApi } from "../lib/useApi";
import { Aviso } from "../lib/useAcao";
import { DespesaForm } from "./Caixa/DespesaForm";

interface Versao { id: string; valido_de: string; valido_ate: string | null; valor: string | null; vencimento: string }
interface Despesa {
  id: string; versao_id: string; nome: string; tipo: "fixa" | "avulsa"; valor: string | null; vencimento: string; forma: string;
  valido_de: string; valido_ate: string | null; situacao: "ativa" | "encerrada"; proximo_vencimento: string | null; versoes: Versao[];
}
type Aba = "fixas" | "avulsas" | "encerradas";
const ABAS: [Aba, string, (d: Despesa) => boolean][] = [
  ["fixas", "Fixas", (d) => d.situacao === "ativa" && d.tipo === "fixa"],
  ["avulsas", "Avulsas", (d) => d.situacao === "ativa" && d.tipo === "avulsa"],
  ["encerradas", "Encerradas", (d) => d.situacao === "encerrada"],
];
const VAZIO: Record<Aba, string> = { fixas: "Nenhuma despesa fixa ativa.", avulsas: "Nenhuma despesa avulsa por vir.", encerradas: "Nenhuma despesa encerrada." };
const FORMA: Record<string, string> = { pix: "Pix", boleto: "boleto", debito_automatico: "débito automático" };

/** "dia:5" → "dia 5"; outra regra sai como veio. Avulsa: dia + mês → "18/11/26". */
const quando = (d: { vencimento: string; valido_de: string }, avulsa: boolean) => {
  const dia = d.vencimento.startsWith("dia:") ? d.vencimento.slice(4) : null;
  if (avulsa && dia) return `${dataCurta(`${d.valido_de}-${dia.padStart(2, "0")}`)}/${d.valido_de.slice(2, 4)}`;
  return dia ? `dia ${dia}` : d.vencimento;
};
const periodo = (v: { valido_de: string; valido_ate: string | null }) => `${mesCurto(v.valido_de)} → ${v.valido_ate ? mesCurto(v.valido_ate) : "hoje"}`;

/** Uma despesa da lista. Ativa: Editar (daqui em diante), Encerrar e Excluir, os dois últimos com confirmação na linha.
 *  Encerrada: só leitura (não há reabrir; para voltar a pagar, cria-se uma despesa nova). Histórico de versões em <details>. */
function Linha({ d, recarregar }: { d: Despesa; recarregar: () => Promise<void> }) {
  const avisar = useToast();
  const [aberto, setAberto] = useState<"editar" | "encerrar" | "excluir" | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | undefined>();
  const id = encodeURIComponent(d.id);
  const avulsa = d.tipo === "avulsa";
  const ativa = d.situacao === "ativa";
  const rodar = async (fn: () => Promise<string>) => {
    if (ocupado) return;
    setOcupado(true); setErro(undefined);
    try { avisar(await fn()); setAberto(null); await recarregar(); }
    catch (e) { const m = (e as Error).message; setErro(m); avisar(m); }
    finally { setOcupado(false); }
  };
  const encerrar = () => rodar(async () => { await api.post(`/api/v1/despesas/${id}/encerrar`); return `${d.nome} encerrada: o que não foi pago saiu de A Pagar.`; });
  const excluir = () => rodar(async () => {
    const r = await api.delete<{ encerrada?: boolean }>(`/api/v1/despesas/${id}`);
    return r.dados?.encerrada ? "Já teve pagamento: foi encerrada, não excluída." : `${d.nome} excluída.`;
  });
  return (
    <li className="linha-item">
        <span className="pilha-curta" style={{ gap: 3 }}>
          <span className="linha-titulo">{d.nome}</span>
          <span className="linha-meta">
            {quando(d, avulsa)}{FORMA[d.forma] ? ` · ${FORMA[d.forma]}` : ""}
            {ativa && d.proximo_vencimento ? ` · próximo ${dataCurta(d.proximo_vencimento)}` : ""}
            {d.valido_ate && !avulsa ? ` · ${ativa ? "termina" : "encerrada"} em ${mesCurto(d.valido_ate)}` : ""}
          </span>
        </span>
        <span className="linha-acoes">
          <span className="linha-valor">{d.valor === null ? <Etiqueta tipo="conferir" texto="sem valor" /> : <Valor valor={d.valor} />}</span>
          {ativa && <>
            <button className="btn btn-sm" disabled={ocupado} aria-label={`Editar ${d.nome}`} onClick={() => setAberto("editar")}>Editar</button>
            <button className="btn btn-sm" disabled={ocupado} aria-label={`Encerrar ${d.nome}`} onClick={() => setAberto("encerrar")}>Encerrar</button>
            <button className="btn btn-sm btn-ghost btn-perigo" disabled={ocupado} aria-label={`Excluir ${d.nome}`} onClick={() => setAberto("excluir")}>Excluir</button>
          </>}
        </span>
      {aberto === "encerrar" && (
        <div role="alert" className="linha-painel">
          <p>Encerrar {d.nome}? O que não foi pago sai de A Pagar; o que já foi pago fica no histórico.</p>
          <span className="fila">
            <button className="btn btn-primary btn-sm" disabled={ocupado} aria-label={`Confirmar encerrar ${d.nome}`} onClick={encerrar}>Confirmar</button>
            <button className="btn btn-sm" disabled={ocupado} onClick={() => setAberto(null)}>Cancelar</button>
          </span>
        </div>)}
      {aberto === "excluir" && (
        <div role="alert" className="linha-painel">
          <p>Excluir {d.nome}? Use só para cadastro errado. Se já teve pagamento, ela é encerrada em vez de excluída.</p>
          <span className="fila">
            <button className="btn btn-primary btn-sm" disabled={ocupado} aria-label={`Confirmar excluir ${d.nome}`} onClick={excluir}>Confirmar</button>
            <button className="btn btn-sm" disabled={ocupado} onClick={() => setAberto(null)}>Cancelar</button>
          </span>
        </div>)}
      {aberto === "editar" && (
        <div className="linha-painel">
          <DespesaForm modo="daqui" item={{ linha_id: d.id, nome: d.nome, valor: d.valor, vencimento: d.vencimento }}
            aoCancelar={() => setAberto(null)} aoSalvar={() => { setAberto(null); void recarregar(); }} />
        </div>)}
      {erro && <span style={{ gridColumn: "1 / -1" }}><Aviso erro={erro} /></span>}
      <details className="historico">
        <summary>Histórico · {d.versoes.length} {d.versoes.length === 1 ? "versão" : "versões"}</summary>
        <table className="tabela" style={{ marginTop: 6 }}>
          <tbody>
            {d.versoes.map((v) => (
              <tr key={v.id}><td className="mono">{periodo(v)}</td><td className="num">{v.valor === null ? "sem valor" : <Valor valor={v.valor} />}</td><td className="suave">{quando(v, avulsa)}</td></tr>))}
          </tbody>
        </table>
      </details>
    </li>
  );
}

/** Cadastros › Despesas: a lista completa (A Pagar só mostra o mês em curso e o seguinte). Abas Fixas, Avulsas e Encerradas; "+ despesa" cria fixa ou avulsa.
 *  Encerradas são só histórico: não há reabrir; para voltar a pagar, cria-se uma despesa nova. */
export function CadastrosDespesas() {
  const leitura = useApi<{ itens: Despesa[] }>("/api/v1/despesas");
  const [aba, setAba] = useState<Aba>("fixas");
  const [nova, setNova] = useState(false);
  return (
    <Painel leitura={leitura} arquivo="planilha de compromissos">
      {(dados) => {
        const [, , filtro] = ABAS.find(([k]) => k === aba)!;
        const itens = dados.itens.filter(filtro);
        return (
          <Bloco style={{ maxWidth: 1080 }} titulo="Despesas" nota="Mudar vale do mês em curso se ele não foi pago; se já foi, do próximo. Meses passados não mudam."
            acao={!nova ? <button className="btn btn-sm" onClick={() => setNova(true)}><Plus size={14} strokeWidth={1.8} aria-hidden="true" />Nova despesa</button> : undefined}>
            <div role="tablist" aria-label="Despesas" className="abas abas-secao">
              {ABAS.map(([k, rotulo, f]) => (
                <button key={k} role="tab" className="aba" aria-selected={aba === k} onClick={() => setAba(k)}>{rotulo} <span className="num suave">{dados.itens.filter(f).length}</span></button>))}
            </div>
            {nova && <div className="folha"><DespesaForm modo="nova" aoCancelar={() => setNova(false)} aoSalvar={() => { setNova(false); void leitura.recarregar(); }} /></div>}
            {aba === "encerradas" && <p className="miudo">Só histórico. Para voltar a pagar uma delas, crie uma despesa nova.</p>}
            {itens.length === 0 ? <Vazio frase={VAZIO[aba]} /> : (
              <ul role="tabpanel" className="pauta">
                {itens.map((d) => <Linha key={d.id} d={d} recarregar={leitura.recarregar} />)}
              </ul>)}
          </Bloco>
        );
      }}
    </Painel>
  );
}
