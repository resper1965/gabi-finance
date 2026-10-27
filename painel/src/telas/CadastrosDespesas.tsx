import { useState } from "react";
import { Bloco } from "../componentes/Bloco";
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
const suave = { color: "var(--ink2)" } as const;
const chip = (ativo: boolean) => ({ height: 32, padding: "0 12px", border: "1px solid var(--line3)", background: ativo ? "var(--sel-bg, var(--raised))" : "transparent", color: "var(--color-text)", font: "600 12.5px var(--font-body)", cursor: "pointer" }) as const;

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
    <li style={{ display: "flex", flexDirection: "column", gap: 6, borderTop: "1px solid var(--color-divider)", padding: "10px 0" }}>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", justifyContent: "space-between" }}>
        <span style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 0 }}>
          <strong>{d.nome}</strong>
          <span style={{ fontSize: 12.5, ...suave }}>
            {quando(d, avulsa)}{FORMA[d.forma] ? ` · ${FORMA[d.forma]}` : ""}
            {ativa && d.proximo_vencimento ? ` · próximo ${dataCurta(d.proximo_vencimento)}` : ""}
            {d.valido_ate && !avulsa ? ` · ${ativa ? "termina" : "encerrada"} em ${mesCurto(d.valido_ate)}` : ""}
          </span>
        </span>
        <span style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700, whiteSpace: "nowrap" }}>{d.valor === null ? "sem valor" : <Valor valor={d.valor} />}</span>
          {ativa && <>
            <button className="btn btn-secondary" style={{ minHeight: 32 }} disabled={ocupado} aria-label={`Editar ${d.nome}`} onClick={() => setAberto("editar")}>Editar</button>
            <button className="btn btn-secondary" style={{ minHeight: 32 }} disabled={ocupado} aria-label={`Encerrar ${d.nome}`} onClick={() => setAberto("encerrar")}>Encerrar</button>
            <button className="btn btn-secondary" style={{ minHeight: 32 }} disabled={ocupado} aria-label={`Excluir ${d.nome}`} onClick={() => setAberto("excluir")}>Excluir</button>
          </>}
        </span>
      </div>
      {aberto === "encerrar" && (
        <div role="alert" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <p style={{ margin: 0 }}>Encerrar {d.nome}? O que não foi pago sai de A Pagar; o que já foi pago fica no histórico.</p>
          <span style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary" disabled={ocupado} aria-label={`Confirmar encerrar ${d.nome}`} onClick={encerrar}>Confirmar</button>
            <button className="btn btn-secondary" disabled={ocupado} onClick={() => setAberto(null)}>Cancelar</button>
          </span>
        </div>)}
      {aberto === "excluir" && (
        <div role="alert" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <p style={{ margin: 0 }}>Excluir {d.nome}? Use só para cadastro errado. Se já teve pagamento, ela é encerrada em vez de excluída.</p>
          <span style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary" disabled={ocupado} aria-label={`Confirmar excluir ${d.nome}`} onClick={excluir}>Confirmar</button>
            <button className="btn btn-secondary" disabled={ocupado} onClick={() => setAberto(null)}>Cancelar</button>
          </span>
        </div>)}
      {aberto === "editar" && (
        <DespesaForm modo="daqui" item={{ linha_id: d.id, nome: d.nome, valor: d.valor, vencimento: d.vencimento }}
          aoCancelar={() => setAberto(null)} aoSalvar={() => { setAberto(null); void recarregar(); }} />)}
      <Aviso erro={erro} />
      <details style={{ fontSize: 12.5 }}>
        <summary style={{ cursor: "pointer", ...suave }}>Histórico · {d.versoes.length} {d.versoes.length === 1 ? "versão" : "versões"}</summary>
        <ul style={{ listStyle: "none", margin: "6px 0 0", padding: 0, display: "flex", flexDirection: "column", gap: 3 }}>
          {d.versoes.map((v) => (
            <li key={v.id} style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <span style={{ fontFamily: "var(--mono)" }}>{periodo(v)}</span>
              <span>{v.valor === null ? "sem valor" : <Valor valor={v.valor} />}</span>
              <span style={suave}>{quando(v, avulsa)}</span>
            </li>))}
        </ul>
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
          <Bloco titulo="Despesas" nota="Mudar vale do mês em curso se ele não foi pago; se já foi, do próximo. Meses passados não mudam.">
            <div style={{ display: "flex", gap: 10, justifyContent: "space-between", alignItems: "center", flexWrap: "wrap" }}>
              <div role="tablist" aria-label="Despesas" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {ABAS.map(([k, rotulo, f]) => (
                  <button key={k} role="tab" aria-selected={aba === k} onClick={() => setAba(k)} style={chip(aba === k)}>{rotulo} · {dados.itens.filter(f).length}</button>))}
              </div>
              {!nova && <button className="btn btn-secondary" style={{ minHeight: 32 }} onClick={() => setNova(true)}>+ despesa</button>}
            </div>
            {nova && <DespesaForm modo="nova" aoCancelar={() => setNova(false)} aoSalvar={() => { setNova(false); void leitura.recarregar(); }} />}
            {aba === "encerradas" && <p style={{ margin: 0, fontSize: 12.5, ...suave }}>Só histórico. Para voltar a pagar uma delas, crie uma despesa nova.</p>}
            {itens.length === 0 ? <Vazio frase={VAZIO[aba]} /> : (
              <ul role="tabpanel" style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {itens.map((d) => <Linha key={d.id} d={d} recarregar={leitura.recarregar} />)}
              </ul>)}
          </Bloco>
        );
      }}
    </Painel>
  );
}
