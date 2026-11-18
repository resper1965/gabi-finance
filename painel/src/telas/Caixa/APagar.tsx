import { useState } from "react";
import { ChevronDown, Plus } from "lucide-react";
import { Etiqueta } from "../../componentes/Etiqueta";
import { Evidencia } from "../../componentes/Evidencia";
import { formatarDadosAte } from "../../componentes/Faixa";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { Vazio } from "../../componentes/Estados";
import { api } from "../../lib/api";
import { dataCurta, mesCurto, num } from "../../lib/formato";
import { useToast } from "../../lib/toast";
import { FONTE } from "../../lib/proveniencia";
import { useApi } from "../../lib/useApi";
import { DespesaForm, type DespesaAlvo, type ModoDespesa } from "./DespesaForm";

interface Item {
  id: string; nome: string; vencimento: string; vencimento_util: string; valor: string | null; estado: string; forma: string;
  dias_atraso?: number; pago_em?: string | null; diferenca?: string | null; motivo?: string | null;
  linha_id?: string | null; mes?: string | null; tipo?: string | null; // a despesa do cadastro; null em fatura e documento avulso
}
type Grupos = Record<"atrasadas" | "hoje" | "proximas" | "adiante" | "debito_automatico" | "a_conferir" | "pagas", Item[]>;

interface Rodada { id: number; fonte: string; fim: string | null; status: string; lidos: number; novos: number; conferida: boolean; reprovadas: { conta: string; tipo: string; detalhe: string }[] }
const TIPO_CONFERENCIA: Record<string, string> = { saldo_final: "saldo", dias_sem_buraco: "dias sem movimento", volume_proximo: "volume" };

/** Últimas rodadas de extrato (06h e 14h) com o que foi lido e se a conferência fechou; se não, quais contas reprovaram e por quê. */
function Rodadas() {
  const itens = (useApi<{ itens: Rodada[] }>("/api/v1/rodadas?limite=20").env?.dados.itens ?? []).filter((r) => r.fonte === "open-finance").slice(0, 2);
  if (itens.length === 0) return null;
  return (
    <section role="region" aria-label="Rodadas" className="secao">
      <div className="secao-cab"><h2>Rodadas</h2><span className="secao-nota">extratos às 6h e 14h; a conferência fecha o saldo de cada conta com o banco</span></div>
      <ul className="pauta">
        {itens.map((r) => (
          <li key={r.id} className="pilha-curta" style={{ gap: 6 }}>
            <span className="fila" style={{ gap: 12 }}>
              <span className="mono" style={{ color: "var(--tinta)" }}>{r.fim ? formatarDadosAte(r.fim) : "em andamento"}</span>
              <span className="carimbo" data-tipo={r.conferida ? "ok" : "erro"} data-estado={r.conferida ? "conferida" : "nao-conferida"}>{r.conferida ? "conferida" : "não conferida"}</span>
              <span className="miudo">{r.lidos} lidos · {r.novos} novos · rodada <span className="mono">#{r.id}</span></span>
            </span>
            {r.reprovadas.map((x, i) => (
              <span key={i} className="fila miudo"><Etiqueta tipo="erro" texto="divergente" /><span>{x.conta}: {TIPO_CONFERENCIA[x.tipo] ?? x.tipo} — {x.detalhe}</span></span>))}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** grupo → título, explicação, carimbo do grupo */
/** grupo → título, explicação e código estável do total (o Resumo cita AP-01 + AP-02 + AP-03) */
const GRUPOS: [keyof Grupos, string, string, string][] = [
  ["atrasadas", "Atrasadas", "já venceram", "AP-01"], ["hoje", "Vencem hoje", "pague hoje", "AP-02"],
  ["proximas", "Próximos 7 dias", "até a próxima semana", "AP-03"], ["adiante", "Mais adiante", "depois disso", "AP-04"],
  ["a_conferir", "A conferir", "valor ou documento incerto", "AP-05"], ["debito_automatico", "Débito automático", "só aviso: o banco debita sozinho", "AP-06"],
];
const FORMA: Record<string, string> = { pix: "Pix", boleto: "boleto", debito_automatico: "débito automático", fatura: "fatura do cartão", "": "" };

const alvo = (b: Item): DespesaAlvo => ({ linha_id: b.linha_id!, nome: b.nome, valor: b.valor, mes: b.mes, vencimento: b.vencimento });
const MENU: [ModoDespesa | "dispensar" | "encerrar", string][] = [["mes", "Editar este mês"], ["dispensar", "Dispensar este mês"], ["daqui", "Mudar daqui em diante"], ["encerrar", "Encerrar"]];
/** Mês em curso (AAAA-MM) em Brasília. Mês já passado não tem "Editar/Dispensar este mês": a API recusa (a rodada só gera o mês em curso e o seguinte). */
const mesAtual = () => new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo", year: "numeric", month: "2-digit" }).format(new Date());
const SO_DO_MES = new Set(["mes", "dispensar"]);

/** Linha de A Pagar. Despesa (item com `linha_id`; fatura e documento avulso não têm) ganha o menu Ações: dispensar tem "Desfazer" no toast;
 *  encerrar pede confirmação e não tem desfazer (não há reabrir; para voltar a pagar, cria-se uma despesa nova); editar o mês e mudar daqui em diante abrem o formulário na linha. */
function Linha({ g, b, paga, recarregar }: { g: keyof Grupos; b: Item; paga: (i: Item) => void; recarregar: () => Promise<void> }) {
  const avisar = useToast();
  const [menu, setMenu] = useState(false);
  const [aberto, setAberto] = useState<ModoDespesa | "encerrar" | null>(null);
  const id = encodeURIComponent(b.linha_id ?? "");
  const tentar = async (fn: () => Promise<void>) => { try { await fn(); } catch (e) { avisar((e as Error).message); } };
  const desfazer = () => tentar(async () => {
    await api.delete(`/api/v1/despesas/${id}/mes/${b.mes}/dispensar`);
    avisar(`Dispensa desfeita: ${b.nome} volta para A Pagar.`);
    await recarregar();
  });
  const dispensar = () => tentar(async () => {
    await api.post(`/api/v1/despesas/${id}/mes/${b.mes}/dispensar`);
    avisar(`${b.nome}: ${mesCurto(b.mes!)} dispensado.`, { rotulo: "Desfazer", fazer: desfazer });
    await recarregar();
  });
  const encerrar = () => tentar(async () => {
    await api.post(`/api/v1/despesas/${id}/encerrar`);
    setAberto(null);
    avisar(`${b.nome} encerrada: o que não foi pago saiu de A Pagar.`);
    await recarregar();
  });
  const escolher = (k: (typeof MENU)[number][0]) => { setMenu(false); if (k === "dispensar") void dispensar(); else setAberto(k); };
  return (
    <li className="linha-item">
      <div className="pilha-curta" style={{ gap: 4 }}>
        <span className="linha-titulo">{b.nome}</span>
        <span className="linha-meta">
          <span className="mono" style={{ color: g === "atrasadas" ? "var(--carimbo-vermelho)" : undefined }}>vence {dataCurta(b.vencimento_util)}</span>
          {FORMA[b.forma] && <span>{FORMA[b.forma]}</span>}
          {g === "atrasadas" && <Etiqueta tipo="erro" texto={`atrasada · ${b.dias_atraso} ${b.dias_atraso === 1 ? "dia" : "dias"}`} />}
          {g === "hoje" && <Etiqueta tipo="erro" texto="vence hoje" />}
          {g === "debito_automatico" && <Etiqueta tipo="parado" texto="débito automático · só aviso" />}
          {g === "a_conferir" && b.motivo && <span>{b.motivo}</span>}
        </span>
      </div>
      <div className="linha-acoes">
        <span className="linha-valor">{b.valor === null ? <Etiqueta tipo="conferir" texto="valor a conferir" /> : <Valor valor={b.valor} />}</span>
        {g !== "debito_automatico" && g !== "a_conferir" && <button className="btn btn-sm" onClick={() => paga(b)}>Já paguei</button>}
        {b.linha_id && (
          <span style={{ position: "relative" }}>
            <button className="btn btn-sm btn-ghost" aria-label={`Ações de ${b.nome}`} aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu(!menu)}
              onKeyDown={(e) => { if (e.key === "Escape") setMenu(false); }}>Ações<ChevronDown size={14} strokeWidth={1.8} aria-hidden="true" /></button>
            {menu && (
              <div role="menu" aria-label={`Ações de ${b.nome}`} className="menu" onKeyDown={(e) => { if (e.key === "Escape") setMenu(false); }}>
                {MENU.filter(([k]) => !(SO_DO_MES.has(k) && b.mes && b.mes < mesAtual())).map(([k, r]) => <button key={k} role="menuitem" className="menu-item" onClick={() => escolher(k)}>{r}</button>)}
              </div>)}
          </span>)}
      </div>
      {aberto === "encerrar" && (
        <div role="alert" className="linha-painel">
          <p>Encerrar {b.nome}? O que não foi pago sai de A Pagar; o que já foi pago fica no histórico.</p>
          <span className="fila">
            <button className="btn btn-primary btn-sm" aria-label={`Confirmar encerrar ${b.nome}`} onClick={encerrar}>Confirmar</button>
            <button className="btn btn-sm" onClick={() => setAberto(null)}>Cancelar</button>
          </span>
        </div>)}
      {(aberto === "mes" || aberto === "daqui") && (
        <div className="linha-painel">
          <DespesaForm modo={aberto} item={alvo(b)} aoCancelar={() => setAberto(null)} aoSalvar={() => { setAberto(null); void recarregar(); }} />
        </div>)}
    </li>
  );
}

/** Caixa › A pagar: o que vence e quando, em grupos por urgência; cada total é um item do laudo com a sua proveniência. */
export function APagar() {
  const leitura = useApi<Grupos>("/api/v1/contas-pagar");
  const avisar = useToast();
  const [nova, setNova] = useState(false);
  const paga = async (i: Item) => {
    try {
      await api.post(`/api/v1/contas-pagar/${encodeURIComponent(i.id)}/paga`);
      avisar(`Anotado: ${i.nome} paga. A próxima rodada confere com o extrato.`);
      leitura.recarregar();
    } catch (e) { avisar((e as Error).message); }
  };
  return (
    <Painel leitura={leitura} arquivo="planilha de compromissos">
      {(d) => {
        const vazio = (Object.keys(d) as (keyof Grupos)[]).every((g) => d[g].length === 0);
        const visiveis = GRUPOS.filter(([g]) => d[g].length > 0);
        return (
          <div className="pilha" style={{ gap: 32, maxWidth: 1080 }}>
            <div className="fila-entre">
              <p className="suave" style={{ maxWidth: "70ch" }}>Cada grupo soma o que vence nele. "Já paguei" anota o pagamento; a próxima rodada confere com o extrato.</p>
              {!nova && <button className="btn" onClick={() => setNova(true)}><Plus size={15} strokeWidth={1.8} aria-hidden="true" />Nova despesa</button>}
            </div>
            {nova && <div className="folha"><DespesaForm modo="nova" aoCancelar={() => setNova(false)} aoSalvar={() => { setNova(false); leitura.recarregar(); }} /></div>}
            {vazio && <Vazio frase="Nenhum compromisso no mês. Cadastre as despesas em Cadastros › Despesas." />}
            {visiveis.map(([g, titulo, sub, codigo]) => {
              const total = d[g].reduce((s, i) => s + num(i.valor), 0);
              return (
                <section key={g} data-grupo={g} className="secao" aria-label={titulo}>
                  <div className="secao-cab">
                    <span className="fila" style={{ gap: 10 }}><h2>{titulo}</h2><span className="secao-nota">{sub} · {d[g].length}</span></span>
                    <span className="linha-valor">
                      <Evidencia codigo={codigo} rotulo={`Total: ${titulo.toLowerCase()}`} fontes={[FONTE.planilha(), FONTE.extrato("conferência dos pagamentos")]} base={`soma de ${d[g].length} ${d[g].length === 1 ? "compromisso" : "compromissos"} da planilha`}
                        estado={g === "a_conferir" ? "a_conferir" : undefined}><Valor valor={total} /></Evidencia>
                    </span>
                  </div>
                  <ul className="pauta">{d[g].map((b) => <Linha key={b.id} g={g} b={b} paga={paga} recarregar={leitura.recarregar} />)}</ul>
                </section>
              );
            })}
            {d.pagas.length > 0 && (
              <section data-grupo="pagas" className="secao" aria-label="Pagas">
                <div className="secao-cab"><span className="fila" style={{ gap: 10 }}><h2>Pagas</h2><span className="secao-nota">conciliadas com o extrato · {d.pagas.length}</span></span></div>
                <ul className="pauta">
                  {d.pagas.map((p) => {
                    const diff = p.diferenca && num(p.diferenca) !== 0;
                    return (
                      <li key={p.id} className="linha-item">
                        <div className="pilha-curta" style={{ gap: 4 }}>
                          <span className="linha-titulo">{p.nome}</span>
                          <span className="linha-meta">
                            <Etiqueta tipo="ok" texto="pago" />
                            <span className="mono">venc. {dataCurta(p.vencimento_util)}</span>
                            {p.pago_em && <span>no extrato em <span className="mono">{dataCurta(p.pago_em)}</span></span>}
                            {diff && <><Etiqueta tipo="erro" texto="divergente" /><span>diferença de <Valor valor={p.diferenca!} /></span></>}
                          </span>
                        </div>
                        <span className="linha-valor" style={{ color: "var(--tinta-2)" }}>{p.valor === null ? "" : <Valor valor={p.valor} />}</span>
                      </li>
                    );
                  })}
                </ul>
              </section>
            )}
            <Rodadas />
          </div>
        );
      }}
    </Painel>
  );
}
