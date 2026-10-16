import { useState } from "react";
import { Painel } from "../componentes/Painel";
import { api } from "../lib/api";
import { dataCurta } from "../lib/formato";
import { useToast } from "../lib/toast";
import { useApi } from "../lib/useApi";
import { FilaExames, MensagensSaude, Serie, TabelaExames, type Medicao, type Pessoa, type Ponto } from "./FamiliaSaude";

interface Marcador { marcador: string; valor: string; unidade: string | null; em: string; fora_da_faixa: boolean; qualitativo?: boolean }

function Exames({ pessoa }: { pessoa: Pessoa }) {
  const lista = useApi<{ marcadores: Marcador[]; historico?: Medicao[] }>(`/api/v1/familia/exames/${pessoa.id}`);
  const [marcador, setMarcador] = useState<string | null>(null);
  const serie = useApi<{ pontos: Ponto[] }>(marcador ? `/api/v1/familia/exames/${pessoa.id}/serie?marcador=${encodeURIComponent(marcador)}` : null);
  const faixa = (lista.env?.dados.historico ?? []).find((h) => h.marcador === marcador && h.ref_min !== null && h.ref_max !== null);
  const [resumo, setResumo] = useState<string | null>(null);
  const avisar = useToast();
  const gerar = async () => {
    try { setResumo((await api.get<{ texto: string }>(`/api/v1/familia/exames/${pessoa.id}/resumo`)).dados.texto); } catch (e) { avisar((e as Error).message); }
  };
  return (
    <Painel leitura={lista} arquivo="familia-exames">
      {(d) => (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {d.marcadores.length === 0 && <p style={{ color: "var(--ink2)" }}>Nenhum exame de {pessoa.nome} ainda.</p>}
          {d.marcadores.filter((m) => !m.qualitativo).map((m) => (
            <button key={m.marcador} className="btn btn-secondary" onClick={() => setMarcador(m.marcador)} aria-pressed={marcador === m.marcador}
              style={{ display: "flex", justifyContent: "space-between", textAlign: "left", gap: 12 }}>
              <span>{m.marcador}</span>
              <span style={{ color: m.fora_da_faixa ? "var(--bad, #c0392b)" : "inherit", fontWeight: 600 }}>{m.valor} {m.unidade ?? ""}{m.fora_da_faixa ? " · fora da faixa" : ""} <small>({dataCurta(m.em)})</small></span>
            </button>))}
          <TabelaExames historico={d.historico ?? []} />
          {marcador && serie.env && <div><h4 style={{ margin: "0 0 6px" }}>{marcador}</h4><Serie pontos={serie.env.dados.pontos} refMin={faixa?.ref_min} refMax={faixa?.ref_max} /></div>}
          {d.marcadores.length > 0 && <div><button className="btn btn-primary" onClick={gerar}>Gerar resumo para a consulta</button></div>}
          {resumo && <pre aria-label="Resumo para a consulta" style={{ whiteSpace: "pre-wrap", background: "var(--color-surface)", padding: 12, margin: 0 }}>{resumo}</pre>}
        </div>
      )}
    </Painel>
  );
}

/** Família: exames por pessoa. Quem vê o quê vem da matriz de acesso no servidor; a saúde fica em arquivo próprio e criptografado. */
export function Familia() {
  const pessoas = useApi<{ itens: Pessoa[] }>("/api/v1/familia/pessoas");
  const [escolhida, setEscolhida] = useState<string | null>(null);
  return (
    <Painel leitura={pessoas} arquivo="familia">
      {(d) => {
        const atual = d.itens.find((p) => p.id === (escolhida ?? d.itens[0]?.id));
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            <label>Pessoa{" "}
              <select aria-label="Pessoa" value={atual?.id ?? ""} onChange={(e) => setEscolhida(e.target.value)}>
                {d.itens.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
              </select>
            </label>
            {atual ? <Exames key={atual.id} pessoa={atual} /> : <p style={{ color: "var(--ink2)" }}>Nenhuma pessoa liberada para você.</p>}
            <FilaExames pessoas={d.itens} />
            <MensagensSaude pessoas={d.itens} />
          </div>
        );
      }}
    </Painel>
  );
}
