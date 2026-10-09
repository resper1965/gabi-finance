import { useState } from "react";
import { Painel } from "../../componentes/Painel";
import { api } from "../../lib/api";
import { useToast } from "../../lib/toast";
import { useApi } from "../../lib/useApi";
import { Bloco } from "./Hoje";

interface Frente { id: number; nome: string; tipo: string; empresa_id: string | null; confirmados: number }
interface Detalhe { frente: Frente; emails: { id: number; remetente: string; assunto: string | null; recebido_em: string }[]; sugeridos: { id: number; remetente: string; assunto: string | null; motivo: string }[] }
const TIPOS = ["cliente", "prospect", "projeto", "interno", "pessoal"];

/** Frentes: árvore à esquerda, frente escolhida à direita. "A Gabi acha que isto entra aqui" só entra com o seu Entra (R1). */
export function Frentes() {
  const lista = useApi<{ itens: Frente[] }>("/api/v1/frentes");
  const [sel, setSel] = useState<number | null>(null);
  const [novo, setNovo] = useState({ nome: "", tipo: "cliente", dominios: "" });
  const avisar = useToast();
  const abrir = async () => {
    if (!novo.nome.trim()) { avisar("Dê um nome à frente."); return; }
    const dominios = novo.dominios.split(",").map((s) => s.trim()).filter(Boolean);
    try {
      await api.post("/api/v1/frentes", { nome: novo.nome.trim(), tipo: novo.tipo, regra: dominios.length ? { dominios } : null });
      setNovo({ nome: "", tipo: "cliente", dominios: "" }); lista.recarregar(); avisar("Frente aberta.");
    } catch (e) { avisar((e as Error).message); }
  };
  return (
    <Painel leitura={lista} arquivo="frentes">
      {(d) => (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(200px,260px) 1fr", gap: 16 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {d.itens.length === 0 && <p style={{ color: "var(--ink2)" }}>Nenhuma frente ainda. Abra a primeira abaixo.</p>}
            {d.itens.map((f) => <button key={f.id} aria-pressed={sel === f.id} onClick={() => setSel(f.id)} style={{ textAlign: "left", padding: 8, border: "1px solid var(--line3)", background: sel === f.id ? "var(--raised)" : "transparent", color: "var(--color-text)" }}>{f.nome} <small>· {f.tipo} · {f.confirmados}</small></button>)}
            <fieldset style={{ border: "1px dashed var(--line3)", padding: 8, display: "flex", flexDirection: "column", gap: 6 }}>
              <legend>+ Abrir frente</legend>
              <input aria-label="Nome da frente" value={novo.nome} onChange={(e) => setNovo({ ...novo, nome: e.target.value })} placeholder="Nome" />
              <select aria-label="Tipo da frente" value={novo.tipo} onChange={(e) => setNovo({ ...novo, tipo: e.target.value })}>{TIPOS.map((t) => <option key={t}>{t}</option>)}</select>
              <input aria-label="Domínios que reconhecem" value={novo.dominios} onChange={(e) => setNovo({ ...novo, dominios: e.target.value })} placeholder="domínios, separados por vírgula" />
              <button onClick={abrir}>Abrir</button>
            </fieldset>
          </div>
          {sel === null ? <p style={{ color: "var(--ink2)" }}>Escolha uma frente.</p> : <Detalhe id={sel} />}
        </div>
      )}
    </Painel>
  );
}

function Detalhe({ id }: { id: number }) {
  const leitura = useApi<Detalhe>(`/api/v1/frentes/${id}`);
  const avisar = useToast();
  const entra = async (item: number) => {
    try { await api.post(`/api/v1/frentes/${id}/itens/${item}/confirmar`); leitura.recarregar(); avisar("Entrou na frente."); } catch (e) { avisar((e as Error).message); }
  };
  return (
    <Painel leitura={leitura} arquivo="frente">
      {(d) => (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <h3 style={{ margin: 0 }}>{d.frente.nome}</h3>
          <Bloco titulo="Em aberto">{d.emails.length === 0 ? <li style={{ listStyle: "none" }}>Nada confirmado ainda.</li> : d.emails.map((m) => <li key={m.id}>{m.assunto} · {m.remetente}</li>)}</Bloco>
          <Bloco titulo="A Gabi acha que isto entra aqui">{d.sugeridos.length === 0 ? <li style={{ listStyle: "none" }}>Sem sugestões.</li> : d.sugeridos.map((s) => (
            <li key={s.id} data-sugerido>{s.assunto} · {s.remetente} <small>({s.motivo})</small> <button onClick={() => entra(s.id)}>Entra</button></li>))}</Bloco>
        </div>
      )}
    </Painel>
  );
}
