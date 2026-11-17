import { useState, type KeyboardEvent } from "react";
import { CheckCheck } from "lucide-react";
import { Etiqueta } from "../../componentes/Etiqueta";
import { Painel } from "../../componentes/Painel";
import { Valor } from "../../componentes/Valor";
import { Vazio } from "../../componentes/Estados";
import { api } from "../../lib/api";
import { useFiltros } from "../../lib/filtros";
import { dataCurta, num, originalEmReais } from "../../lib/formato";
import { useToast } from "../../lib/toast";
import { useApi } from "../../lib/useApi";
import { useOcultar } from "../../lib/ocultar";

interface Campo { id: number | string | null; nome: string | null; origem: string | null }
interface Lanc { id: number; data: string; estabelecimento: string; valor: string; conta: string; categoria: Campo; para_quem: Campo; empresa: Campo; moeda?: string; valor_original?: string | null; convertido?: boolean; gasto?: { valor: boolean; origem: string | null }; gastador?: Campo; portadores?: string[] }
interface Sug { id: number; tipo: string; lancamento_id: number | null; payload: Record<string, number | string>; motivo: string }
interface Pessoa { id: number | string; nome: string; papel?: string | null; dados?: Record<string, unknown> }
interface ContaUso { apelido: string; usuarios?: string[] }

const ORIGEM: Record<string, string> = { banco: "banco", regra: "regra", gabi: "Gabi sugere", voce: "você", fonte: "padrão do cadastro" };
const POR_QUE: Record<string, string> = { fatura: "paga fatura de cartão", emissor: "boleto de fatura de cartão", propria: "transferência para empresa sua", investimento: "investimento", voce: "marcado por você" };

/** Setas esquerda/direita (e Home/End) andam entre os botões do grupo; Enter ou espaço escolhem. */
function setas(e: KeyboardEvent<HTMLElement>) {
  const passo = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
  if (passo === undefined && e.key !== "Home" && e.key !== "End") return;
  const bs = [...e.currentTarget.querySelectorAll<HTMLButtonElement>("button")];
  const i = bs.indexOf(document.activeElement as HTMLButtonElement);
  if (i < 0) return;
  e.preventDefault();
  const j = e.key === "Home" ? 0 : e.key === "End" ? bs.length - 1 : (i + passo! + bs.length) % bs.length;
  bs[j]?.focus();
}

/** "De quem é cada gasto?": escolher a pessoa vale só para aquele lançamento; "sempre assim" cria regra (R1: só com o seu toque). */
export function Lancamentos() {
  const { conta } = useFiltros();
  const avisar = useToast();
  const oculto = useOcultar();
  const [filtro, setFiltro] = useState<"esperando" | "gastador" | "todos">("esperando");
  const url = `/api/v1/lancamentos?limite=100${filtro === "esperando" ? "&pendente=para_quem" : filtro === "gastador" ? "&pendente=gastador" : ""}${conta ? `&conta=${encodeURIComponent(conta)}` : ""}`;
  const leitura = useApi<{ itens: Lanc[]; total: number }>(url);
  const pessoas = useApi<{ itens: Pessoa[] }>("/api/v1/cadastros/pessoas").env?.dados.itens ?? [];
  const contas = useApi<{ itens: ContaUso[] }>("/api/v1/cadastros/contas").env?.dados.itens ?? [];
  const empresas = useApi<{ itens: { id: string; nome: string }[] }>("/api/v1/cadastros/empresas").env?.dados.itens ?? [];
  const sugestoes = useApi<{ itens: Sug[] }>("/api/v1/sugestoes");
  const sugParaQuem = (sugestoes.env?.dados.itens ?? []).filter((s) => s.tipo === "para_quem" && s.lancamento_id !== null);
  const recarregar = () => { leitura.recarregar(); sugestoes.recarregar(); };

  /** Quem aparece como opção: nunca quem só recebe pagamento (beneficiario=false); num cartão de 2+ usuários, só eles e os donos coletivos (Casa, Pets). */
  const opcoesPara = (l: Lanc) => {
    const usuarios = contas.find((c) => c.apelido.trim() === l.conta.trim())?.usuarios ?? [];
    return pessoas.filter((p) => p.id === l.para_quem.id || (p.dados?.beneficiario !== false &&
      (usuarios.length < 2 || usuarios.includes(String(p.id)) || p.papel === "coletivo")));
  };
  const escolher = async (l: Lanc, p: Pessoa) => {
    try { await api.patch(`/api/v1/lancamentos/${l.id}`, { beneficiario_id: p.id }); avisar(`Anotado: ${l.estabelecimento} é de ${p.nome}, só este lançamento.`); recarregar(); }
    catch (e) { avisar((e as Error).message); }
  };
  const confirmar = async (s: Sug, l: Lanc) => {
    try { await api.post(`/api/v1/sugestoes/${s.id}/aprovar`); avisar(`Confirmado por você: ${l.estabelecimento}.`); recarregar(); }
    catch (e) { avisar((e as Error).message); }
  };
  const confirmarTodas = async () => {
    for (const s of sugParaQuem) await api.post(`/api/v1/sugestoes/${s.id}/aprovar`).catch(() => null);
    avisar(`${sugParaQuem.length} sugestões confirmadas por você.`);
    recarregar();
  };
  /** gasto: true/false é a sua marcação (vence as regras); null devolve a decisão à Gabi. */
  const marcarGasto = async (l: Lanc, gasto: boolean | null) => {
    try { await api.patch(`/api/v1/lancamentos/${l.id}`, { gasto }); avisar(gasto === null ? `${l.estabelecimento}: a Gabi volta a decidir.` : `Anotado: ${l.estabelecimento} ${gasto ? "é" : "não é"} gasto.`); recarregar(); }
    catch (e) { avisar((e as Error).message); }
  };
  /** Reembolso: a empresa que te devolve esta compra (entra em "Despesas por empresa"); continua sendo gasto seu. "" = pessoal. */
  const marcarReembolso = async (l: Lanc, empresa: string) => {
    const nome = empresas.find((c) => c.id === empresa)?.nome;
    try { await api.patch(`/api/v1/lancamentos/${l.id}`, { empresa_id: empresa || null }); avisar(nome ? `Anotado: ${l.estabelecimento} é reembolso ${nome}.` : `Anotado: ${l.estabelecimento} é pessoal, sem reembolso.`); recarregar(); }
    catch (e) { avisar((e as Error).message); }
  };
  /** Quem gastou (portador): só nos cartões com 2+ portadores; "sempre" grava a regra desta loja neste cartão. */
  const indicar = async (l: Lanc, pessoa: string, sempre = false) => {
    const nome = pessoas.find((p) => String(p.id) === pessoa)?.nome ?? pessoa;
    try {
      await api.post("/api/v1/lancamentos/lote", { ids: [l.id], mudancas: { gastador_id: pessoa }, criar_regra: sempre });
      avisar(sempre ? `Regra criada por você: ${l.estabelecimento} neste cartão é sempre de ${nome}.` : `Anotado: ${nome} gastou em ${l.estabelecimento}.`); recarregar();
    } catch (e) { avisar((e as Error).message); }
  };
  const sempreAssim = async (l: Lanc) => {
    try { await api.post("/api/v1/lancamentos/lote", { ids: [l.id], mudancas: { beneficiario_id: l.para_quem.id }, criar_regra: true }); avisar(`Regra criada por você: os próximos de ${l.estabelecimento} seguem igual.`); recarregar(); }
    catch (e) { avisar((e as Error).message); }
  };

  return (
    <Painel leitura={leitura} arquivo="lançamentos do extrato">
      {(d) => (
        <div className="pilha" style={{ gap: 20, maxWidth: 1040 }}>
          <p className="suave" style={{ maxWidth: "72ch" }}>
            Escolha de quem é cada gasto. A escolha vale <strong style={{ color: "var(--tinta)" }}>só para aquele lançamento</strong>; "sempre assim" vira regra para os próximos do mesmo estabelecimento. Use as setas para andar entre as pessoas e Enter para escolher.
          </p>
          <div className="fila-entre">
            <div className="fila" style={{ gap: 12 }}>
              <div role="group" aria-label="Filtro" className="seg">
                {([["esperando", "Esperando você"], ["gastador", "Quem gastou: a indicar"], ["todos", "Todos"]] as const).map(([id, r]) => (
                  <button key={id} className="seg-opt" aria-pressed={filtro === id} onClick={() => setFiltro(id)}>{r}</button>
                ))}
              </div>
              <span className="miudo num">{d.itens.length} {d.itens.length === 1 ? "lançamento" : "lançamentos"}{d.total > d.itens.length ? ` de ${d.total}` : ""}</span>
            </div>
            {sugParaQuem.length > 0 && <button className="btn" onClick={confirmarTodas}><CheckCheck size={15} strokeWidth={1.8} aria-hidden="true" />Confirmar as {sugParaQuem.length} sugestões da Gabi</button>}
          </div>
          {d.itens.length === 0 && <Vazio frase={filtro === "gastador" ? "Nenhuma compra de cartão compartilhado esperando você indicar quem gastou." : "Nada esperando você. Todos os lançamentos têm dono."} />}
          <ul className="pauta lancamentos">
            {d.itens.map((l) => {
              const sug = sugParaQuem.find((s) => s.lancamento_id === l.id);
              const despesa = num(l.valor) < 0;
              const original = !oculto && originalEmReais(l);
              return (
                <li key={l.id} data-lancamento={l.id} className="lanc">
                  <span className="lanc-data mono">{dataCurta(l.data)}</span>
                  <div className="lanc-corpo">
                    <div className="lanc-cab">
                      <span className="pilha-curta" style={{ gap: 2 }}>
                        <span className="lanc-nome">{l.estabelecimento}</span>
                        <span className="linha-meta">
                          <span>{l.conta}</span><span aria-hidden="true">·</span><span>{l.categoria.nome ?? "sem categoria"}</span>
                          {l.empresa.nome && <><span aria-hidden="true">·</span><span>reembolso {l.empresa.nome}</span></>}
                          {!sug && !l.para_quem.origem && <Etiqueta tipo="conferir" texto="sem dono" />}
                        </span>
                      </span>
                      <span className="lanc-valor num" style={{ color: despesa ? undefined : "var(--carimbo-verde)" }}>
                        <Valor valor={l.valor} />
                        {original && <span className="celula-sub">{original}</span>}
                      </span>
                    </div>

                    {(l.portadores?.length ?? 0) >= 2 && (
                      <div className="lanc-escolha">
                        <span className="lanc-rotulo">Quem gastou</span>
                        <span role="group" aria-label={`Quem gastou: ${l.estabelecimento}`} className="fila" style={{ gap: 6 }} onKeyDown={setas}>
                          {l.portadores!.map((pid) => (
                            <button key={pid} className="chip" aria-pressed={l.gastador?.id === pid} onClick={() => indicar(l, pid)}>{pessoas.find((p) => String(p.id) === pid)?.nome ?? pid}</button>
                          ))}
                        </span>
                        {l.gastador?.id && l.gastador.origem === "voce" && <button className="link miudo" onClick={() => indicar(l, String(l.gastador!.id), true)}>sempre {l.gastador.nome} em {l.estabelecimento} neste cartão</button>}
                        {l.gastador?.origem === "regra" && <span className="miudo">(regra desta loja)</span>}
                      </div>
                    )}

                    <div className="lanc-escolha">
                      <span className="lanc-rotulo">Para quem</span>
                      <span role="group" aria-label={`Para quem: ${l.estabelecimento}`} className="fila" style={{ gap: 6 }} onKeyDown={setas}>
                        {opcoesPara(l).map((p) => {
                          const marcado = l.para_quem.id === p.id, sugerido = sug?.payload.para_quem_id === p.id && !marcado;
                          return (
                            <button key={p.id} className="chip" aria-pressed={marcado} data-sugerido={sugerido || undefined} onClick={() => escolher(l, p)}
                              style={sugerido ? { border: "1px dashed var(--ambar-borda)" } : undefined}>{p.nome}</button>
                          );
                        })}
                      </span>
                      <span className="cresce" />
                      {despesa && (l.gasto || empresas.length > 0) && (
                        <span className="linha-meta lanc-secundario">
                          {l.gasto && <>
                            <span>{l.gasto.valor ? "é gasto" : `não é gasto${l.gasto.origem ? ` (${POR_QUE[l.gasto.origem] ?? l.gasto.origem})` : ""}`}</span>
                            <button className="link" onClick={() => marcarGasto(l, !l.gasto!.valor)}>{l.gasto.valor ? "não é gasto" : "é gasto"}</button>
                            {l.gasto.origem === "voce" && <button className="link" onClick={() => marcarGasto(l, null)}>deixar a Gabi decidir</button>}
                          </>}
                          {empresas.length > 0 && (
                            <label className="fila" style={{ gap: 6 }}>Reembolso
                              <select className="campo-sm" aria-label={`Reembolso: ${l.estabelecimento}`} value={l.empresa.id == null ? "" : String(l.empresa.id)} onChange={(e) => marcarReembolso(l, e.target.value)}>
                                <option value="">pessoal</option>
                                {empresas.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
                              </select>
                            </label>)}
                        </span>)}
                    </div>

                    {(sug || l.para_quem.origem) && <div className="lanc-rodape">
                      <span className="linha-meta">
                        {sug ? <>
                          <Etiqueta tipo="conferir" texto="sugestão" />
                          <span>Gabi sugere: {pessoas.find((p) => p.id === sug.payload.para_quem_id)?.nome ?? "?"} · {sug.motivo}</span>
                          <button className="link" onClick={() => confirmar(sug, l)}>confirmar</button>
                        </> : <span>{l.para_quem.nome} · {ORIGEM[l.para_quem.origem!] ?? l.para_quem.origem}</span>}
                        {l.para_quem.origem === "voce" && <button className="link" onClick={() => sempreAssim(l)}>sempre assim para {l.estabelecimento}</button>}
                      </span>
                    </div>}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </Painel>
  );
}
