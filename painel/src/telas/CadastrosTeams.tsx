import { useState } from "react";
import { Bloco } from "../componentes/Bloco";
import { Painel } from "../componentes/Painel";
import { Vazio } from "../componentes/Estados";
import { api } from "../lib/api";
import { Aviso, useAcao } from "../lib/useAcao";
import { useApi } from "../lib/useApi";

interface Fonte { id: number; conta: string; estado: "sim" | "nao" | "a_decidir"; coletada_em: string | null; ultimo_erro: string | null }

const ESTADO = { sim: "Lendo", nao: "Pausada", a_decidir: "A decidir" } as const;
const suave = { color: "var(--ink2)" } as const;
const linha = { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", justifyContent: "space-between", borderTop: "1px solid var(--color-divider)", padding: "8px 0" } as const;
const lista = { listStyle: "none", margin: 0, padding: 0 } as const;
const quando = (iso: string | null) => {
  if (!iso) return "nunca";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "nunca";
  return new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }).format(d);
};

/** Cadastros › Teams: quais contas a Gabi lê. Só metadados; nunca texto de mensagem. */
export function CadastrosTeams() {
  const leitura = useApi<{ fontes: Fonte[] }>("/api/v1/teams/fontes");
  const { ocupado, erros, agir } = useAcao();
  const [conta, setConta] = useState("");
  if (leitura.estado === "erro" && leitura.erro?.status === 403) return <Vazio frase="Só o dono configura o Teams." />;
  const mudar = (f: Fonte, estado: "sim" | "nao", msg: string) => agir(`f${f.id}`, () => api.put(`/api/v1/teams/fontes/${f.id}/estado`, { estado }), msg, leitura.recarregar);
  return (
    <Painel leitura={leitura} arquivo="teams-fontes">
      {(d) => (
        <Bloco titulo={`Contas do Teams · ${d.fontes.length}`} nota="Só metadados: só quem escreveu e quando; o texto não é guardado. Nada é lido até você liberar.">
          <Aviso erro={erros.geral} />
          {d.fontes.length === 0 ? <Vazio frase="Nenhuma conta do Teams cadastrada. Cadastre uma conta abaixo." /> : (
            <ul style={lista}>
              {d.fontes.map((f) => {
                const aviso = f.ultimo_erro && f.coletada_em !== null && f.estado === "sim";
                return (
                  <li key={f.id} style={linha}>
                    <span><strong>{f.conta}</strong> <span style={suave}>· {ESTADO[f.estado]} · última coleta {quando(f.coletada_em)}</span></span>
                    <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {f.estado !== "sim" && <button className="btn btn-primary" disabled={ocupado} aria-label={`Liberar ${f.conta}`} onClick={() => mudar(f, "sim", "Conta liberada.")}>Liberar</button>}
                      {f.estado !== "nao" && <button className="btn btn-secondary" disabled={ocupado} aria-label={`Pausar ${f.conta}`} onClick={() => mudar(f, "nao", "Conta pausada.")}>Pausar</button>}
                    </span>
                    {f.ultimo_erro && <p style={{ margin: 0, flexBasis: "100%", ...(aviso ? suave : { color: "var(--danger)" }) }}>{aviso ? "Aviso" : "Último erro"}: {f.ultimo_erro}</p>}
                    <Aviso erro={erros[`f${f.id}`]} />
                  </li>);
              })}
            </ul>)}
          <form style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "end" }} onSubmit={async (e) => {
            e.preventDefault();
            if (ocupado || !conta.trim()) return;
            if (await agir("geral", () => api.post("/api/v1/teams/fontes", { conta: conta.trim() }), "Conta cadastrada.", leitura.recarregar)) setConta("");
          }}>
            <label>Conta (e-mail)<br /><input aria-label="Conta do Teams" value={conta} onChange={(e) => setConta(e.target.value)} /></label>
            <button className="btn btn-primary" type="submit" disabled={ocupado}>Cadastrar conta</button>
          </form>
        </Bloco>
      )}
    </Painel>
  );
}
