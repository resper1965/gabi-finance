/** Atividades: o to-do do Ricardo (ADR-033). O recado ao Hermes vira atividade; aqui ele vê, anota, conclui, adia e exclui.
 * Consome: GET /api/v1/atividades, POST /atividades, POST /atividades/{id}/concluir e /cancelar, PATCH /atividades/{id}. */
import { useState } from "react";
import { Bloco } from "../componentes/Bloco";
import { Vazio } from "../componentes/Estados";
import { Painel } from "../componentes/Painel";
import { api } from "../lib/api";
import { dataCurta } from "../lib/formato";
import { Aviso, useAcao } from "../lib/useAcao";
import { useApi } from "../lib/useApi";

type Prazo = "vencida" | "hoje" | "proxima" | "sem_data";
interface Atividade { id: number; texto: string; vence_em: string | null; tem_hora: boolean; status: string; prazo: Prazo }
const ROTA = "/api/v1/atividades";
const GRUPOS: [Prazo, string][] = [["vencida", "Vencidas"], ["hoje", "Hoje"], ["proxima", "Próximas"], ["sem_data", "Sem data"]];
const suave = { color: "var(--ink2)" } as const;

/** Data de hoje (ou de amanhã) no relógio do navegador, `AAAA-MM-DD`. */
const dia = (mais = 0) => {
  const d = new Date(); d.setDate(d.getDate() + mais);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const quando = (a: Atividade) => (a.vence_em ? `${dataCurta(a.vence_em)}${a.tem_hora ? ` às ${a.vence_em.slice(11, 16)}` : ""}` : "");

function Linha({ a, agir, ocupado, erro, recarregar }: { a: Atividade; agir: ReturnType<typeof useAcao>["agir"]; ocupado: boolean; erro?: string; recarregar: () => Promise<void> }) {
  const [aberto, setAberto] = useState<"adiar" | "excluir" | null>(null);
  const [data, setData] = useState("");
  const chave = String(a.id);
  const adiar = (vence_em: string) => agir(chave, () => api.patch(`${ROTA}/${a.id}`, { vence_em }), "Atividade adiada.", recarregar).then((ok) => ok && setAberto(null));
  return (
    <li style={{ display: "flex", flexDirection: "column", gap: 6, borderTop: "1px solid var(--color-divider)", padding: "10px 0" }}>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", justifyContent: "space-between" }}>
        <span style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 0 }}>
          <span>{a.texto}</span>
          {a.vence_em && <span style={{ fontSize: 12.5, ...suave }}>{quando(a)}</span>}
        </span>
        <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="btn btn-primary" style={{ minHeight: 32 }} disabled={ocupado} aria-label={`Feita: ${a.texto}`}
            onClick={() => agir(chave, () => api.post(`${ROTA}/${a.id}/concluir`), "Atividade feita.", recarregar)}>Feita</button>
          <button className="btn btn-secondary" style={{ minHeight: 32 }} disabled={ocupado} aria-label={`Adiar: ${a.texto}`} onClick={() => setAberto("adiar")}>Adiar</button>
          <button className="btn btn-secondary" style={{ minHeight: 32 }} disabled={ocupado} aria-label={`Excluir: ${a.texto}`} onClick={() => setAberto("excluir")}>Excluir</button>
        </span>
      </div>
      {aberto === "adiar" && (
        <span style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <button className="btn btn-secondary" style={{ minHeight: 32 }} disabled={ocupado} onClick={() => adiar(dia())}>Hoje</button>
          <button className="btn btn-secondary" style={{ minHeight: 32 }} disabled={ocupado} onClick={() => adiar(dia(1))}>Amanhã</button>
          <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13 }}>Escolher data
            <input type="date" value={data} min={dia()} onChange={(e) => setData(e.target.value)} /></label>
          <button className="btn btn-primary" style={{ minHeight: 32 }} disabled={ocupado || !data} onClick={() => adiar(data)}>Adiar para a data</button>
          <button className="btn btn-secondary" style={{ minHeight: 32 }} onClick={() => setAberto(null)}>Fechar</button>
        </span>)}
      {aberto === "excluir" && (
        <div role="alert" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <p style={{ margin: 0 }}>Excluir "{a.texto}"? Não há como voltar; para ter de novo, crie outra.</p>
          <span style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary" disabled={ocupado} aria-label={`Confirmar excluir ${a.texto}`}
              onClick={() => agir(chave, () => api.post(`${ROTA}/${a.id}/cancelar`), "Atividade excluída.", recarregar).then((ok) => ok && setAberto(null))}>Confirmar</button>
            <button className="btn btn-secondary" disabled={ocupado} onClick={() => setAberto(null)}>Cancelar</button>
          </span>
        </div>)}
      <Aviso erro={erro} />
    </li>
  );
}

function Nova({ agir, ocupado, recarregar }: { agir: ReturnType<typeof useAcao>["agir"]; ocupado: boolean; recarregar: () => Promise<void> }) {
  const [texto, setTexto] = useState("");
  const [data, setData] = useState("");
  const [hora, setHora] = useState("");
  const adicionar = async () => {
    if (!texto.trim()) return;
    const corpo = { texto: texto.trim(), ...(data ? { vence_em: hora ? `${data}T${hora}` : data } : {}) };
    if (await agir("nova", () => api.post(ROTA, corpo), "Atividade criada.", recarregar)) { setTexto(""); setData(""); setHora(""); }
  };
  return (
    <form onSubmit={(e) => { e.preventDefault(); void adicionar(); }} style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
      <label style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 13, flex: "1 1 240px" }}>Nova atividade
        <input value={texto} maxLength={500} onChange={(e) => setTexto(e.target.value)} /></label>
      <label style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 13 }}>Data (opcional)
        <input type="date" value={data} onChange={(e) => { setData(e.target.value); if (!e.target.value) setHora(""); }} /></label>
      <label style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 13 }}>Hora (opcional)
        <input type="time" value={hora} disabled={!data} onChange={(e) => setHora(e.target.value)} /></label>
      <button type="submit" className="btn btn-primary" disabled={ocupado || !texto.trim()}>Adicionar</button>
    </form>
  );
}

/** Lista agrupada por prazo (Vencidas, Hoje, Próximas, Sem data; grupo vazio some). O brain avisa no Telegram na hora e de manhã. */
export function Atividades() {
  const leitura = useApi<{ itens: Atividade[] }>(ROTA);
  const { ocupado, erros, agir } = useAcao();
  return (
    <Painel leitura={leitura} arquivo="atividades">
      {(dados) => (
        <Bloco titulo="Atividades" nota="Deixe o recado ao Hermes (Telegram ou WhatsApp) ou anote aqui. O brain avisa no Telegram na hora marcada e de manhã.">
          <Nova agir={agir} ocupado={ocupado} recarregar={leitura.recarregar} />
          <Aviso erro={erros.nova} />
          {dados.itens.length === 0 ? <Vazio frase="Nada para fazer." /> : GRUPOS.map(([prazo, rotulo]) => {
            const itens = dados.itens.filter((a) => a.prazo === prazo);
            return itens.length === 0 ? null : (
              <section key={prazo}>
                <h4 style={{ margin: "12px 0 4px", fontSize: 14 }}>{rotulo}</h4>
                <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                  {itens.map((a) => <Linha key={a.id} a={a} agir={agir} ocupado={ocupado} erro={erros[String(a.id)]} recarregar={leitura.recarregar} />)}
                </ul>
              </section>);
          })}
        </Bloco>)}
    </Painel>
  );
}
