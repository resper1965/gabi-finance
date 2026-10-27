import { useState } from "react";
import { api } from "../../lib/api";
import { mesCurto, reaisDoTexto } from "../../lib/formato";
import { Aviso, useAcao } from "../../lib/useAcao";

/** A despesa sobre a qual o formulário age. `vencimento` pode ser a data do mês (A Pagar, "2026-10-10") ou a regra do cadastro ("dia:10"). */
export interface DespesaAlvo { linha_id: string; nome: string; valor?: string | null; mes?: string | null; vencimento?: string | null }
export type ModoDespesa = "nova" | "daqui" | "mes";

const FORMAS: [string, string][] = [["pix", "Pix"], ["boleto", "boleto"], ["debito_automatico", "débito automático"]];
/** "2100.00" → "2100,00" para o campo (só troca o separador). */
const paraCampo = (v?: string | null) => (v ? v.replace(".", ",") : "");
/** Dia do vencimento: "dia:10" → "10"; "2026-10-10" → "10"; outra regra (ex.: último dia útil) → "". */
const diaDe = (v?: string | null) => (!v ? "" : v.startsWith("dia:") ? v.slice(4) : /^\d{4}-\d{2}-\d{2}$/.test(v) ? String(Number(v.slice(8, 10))) : "");
const diaValido = (s: string) => /^\d{1,2}$/.test(s) && Number(s) >= 1 && Number(s) <= 31;
const campo = { display: "flex", flexDirection: "column" as const, gap: 3, fontSize: 13 };

/** Formulário de despesa (A Pagar e Cadastros › Despesas). "nova": fixa (dia) ou avulsa (data); "daqui": muda valor/dia daqui em diante
 *  (a API decide o mês se "a partir de" ficar vazio); "mes": valor/data só do mês do item. Manda só o que mudou; valor sempre em reais string. */
export function DespesaForm({ modo, item, aoSalvar, aoCancelar }: { modo: ModoDespesa; item?: DespesaAlvo; aoSalvar: () => void; aoCancelar?: () => void }) {
  const { ocupado, erros, agir } = useAcao();
  const [tipo, setTipo] = useState<"fixa" | "avulsa">("fixa");
  const [nome, setNome] = useState("");
  const [valor, setValor] = useState(paraCampo(item?.valor));
  const [dia, setDia] = useState(diaDe(item?.vencimento));
  const [data, setData] = useState(modo === "mes" && item?.vencimento && /^\d{4}-/.test(item.vencimento) ? item.vencimento : "");
  const [forma, setForma] = useState("pix");
  const [aPartir, setAPartir] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const id = item ? encodeURIComponent(item.linha_id) : "";

  /** Monta o pedido do modo; devolve o texto do erro de preenchimento, se houver. */
  const pedido = (): { fazer: () => Promise<unknown>; ok: string } | string => {
    const reais = valor.trim() ? reaisDoTexto(valor) : null;
    if (valor.trim() && reais === null) return "valor inválido (ex.: 1.500,00).";
    if (modo === "nova") {
      if (!nome.trim()) return "informe o nome.";
      const corpo: Record<string, string> = { tipo, nome: nome.trim() };
      if (reais) corpo.valor_padrao = reais;
      if (tipo === "fixa") {
        if (!diaValido(dia)) return "dia do vencimento de 1 a 31.";
        corpo.vencimento = `dia:${Number(dia)}`;
      } else {
        if (!reais) return "informe o valor.";
        if (!data) return "informe a data.";
        corpo.data = data;
      }
      corpo.forma = forma;
      return { fazer: () => api.post("/api/v1/despesas", corpo), ok: `Despesa criada: ${corpo.nome}.` };
    }
    if (!item) return "despesa não informada.";
    if (modo === "daqui") {
      const corpo: Record<string, string> = {};
      if (reais && reais !== item.valor) corpo.valor_padrao = reais;
      if (dia !== diaDe(item.vencimento)) { if (!diaValido(dia)) return "dia do vencimento de 1 a 31."; corpo.vencimento = `dia:${Number(dia)}`; }
      if (Object.keys(corpo).length === 0) return "nada mudou.";
      if (aPartir) corpo.a_partir = aPartir;
      return { fazer: () => api.patch(`/api/v1/despesas/${id}`, corpo), ok: `${item.nome}: muda a partir de ${aPartir ? mesCurto(aPartir) : "o primeiro mês não pago"}.` };
    }
    const corpo: Record<string, string> = {};
    if (reais && reais !== item.valor) corpo.valor = reais;
    if (data && data !== item.vencimento) corpo.vencimento = data;
    if (Object.keys(corpo).length === 0) return "nada mudou.";
    const mes = item.mes ?? "";
    return { fazer: () => api.post(`/api/v1/despesas/${id}/mes/${mes}`, corpo), ok: `${item.nome}: ${mes ? mesCurto(mes) : "mês"} ajustado.` };
  };

  return (
    <form aria-label={modo === "nova" ? "Nova despesa" : modo === "daqui" ? `Mudar ${item?.nome} daqui em diante` : `Editar ${item?.nome} neste mês`}
      style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "end", padding: "10px 0" }} onSubmit={async (e) => {
        e.preventDefault();
        if (ocupado) return;
        const p = pedido();
        if (typeof p === "string") { setMsg(p); return; }
        setMsg(null);
        if (await agir("form", p.fazer, p.ok)) aoSalvar();
      }}>
      {modo === "nova" && (
        <fieldset style={{ border: 0, padding: 0, margin: 0, display: "flex", gap: 12, fontSize: 13 }}>
          <legend style={{ padding: 0, marginBottom: 3 }}>Tipo</legend>
          <label><input type="radio" name="tipo-despesa" checked={tipo === "fixa"} onChange={() => setTipo("fixa")} /> Fixa</label>
          <label><input type="radio" name="tipo-despesa" checked={tipo === "avulsa"} onChange={() => setTipo("avulsa")} /> Avulsa</label>
        </fieldset>)}
      {modo === "nova" && <label style={campo}>Nome<input value={nome} onChange={(e) => setNome(e.target.value)} /></label>}
      <label style={campo}>Valor<input inputMode="decimal" placeholder="0,00" value={valor} onChange={(e) => setValor(e.target.value)} /></label>
      {(modo === "daqui" || (modo === "nova" && tipo === "fixa")) && <label style={campo}>Dia do vencimento<input inputMode="numeric" style={{ width: 70 }} value={dia} onChange={(e) => setDia(e.target.value)} /></label>}
      {(modo === "mes" || (modo === "nova" && tipo === "avulsa")) && <label style={campo}>Data<input type="date" value={data} onChange={(e) => setData(e.target.value)} /></label>}
      {modo === "daqui" && <label style={campo}>A partir de (opcional)<input type="month" value={aPartir} onChange={(e) => setAPartir(e.target.value)} /></label>}
      {modo === "nova" && (
        <label style={campo}>Forma<select value={forma} onChange={(e) => setForma(e.target.value)}>{FORMAS.map(([k, r]) => <option key={k} value={k}>{r}</option>)}</select></label>)}
      <span style={{ display: "flex", gap: 8 }}>
        <button className="btn btn-primary" type="submit" disabled={ocupado}>Salvar</button>
        {aoCancelar && <button className="btn btn-secondary" type="button" disabled={ocupado} onClick={aoCancelar}>Cancelar</button>}
      </span>
      {modo === "daqui" && <p style={{ margin: 0, flexBasis: "100%", fontSize: 12.5, color: "var(--ink2)" }}>Sem "a partir de": vale do mês em curso se ele não foi pago; se já foi, do próximo. Meses passados não mudam.</p>}
      {msg && <p role="alert" style={{ margin: 0, flexBasis: "100%", color: "var(--danger)" }}>Erro: {msg}</p>}
      <Aviso erro={erros.form} />
    </form>
  );
}
