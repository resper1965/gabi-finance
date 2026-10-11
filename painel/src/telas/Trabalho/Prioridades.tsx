import { Painel } from "../../componentes/Painel";
import { Vazio } from "../../componentes/Estados";
import { api } from "../../lib/api";
import { Aviso, useAcao } from "../../lib/useAcao";
import { useApi } from "../../lib/useApi";
import { quandoBRT } from "../CadastrosCorreio";
import { Bloco } from "./Hoje";

interface Msg { id: number; conta: string; remetente: string | null; assunto: string | null; recebida_em: string; classe: "emergencial" | "importante" | "normal" | "lixo"; prioridade: number | null; motivo: string | null; movida_em?: string }

const suave = { color: "var(--ink2)" } as const;
const quem = (m: Msg) => `${m.remetente || "?"} — ${m.assunto || "(sem assunto)"}`;

/** Mensagens › Prioridades: o que exige ação primeiro e o que a Gabi mandou para a lixeira (com Restaurar). Só cabeçalho e motivo; o corpo fica no Gmail. */
export function Prioridades() {
  const fila = useApi<{ mensagens: Msg[] }>("/api/v1/correio/prioridades");
  const lixeira = useApi<{ mensagens: Msg[] }>("/api/v1/correio/lixeira");
  const { ocupado, erros, agir } = useAcao();
  if ([fila, lixeira].some((l) => l.estado === "erro" && l.erro?.status === 403)) return <Vazio frase="Só o dono vê o e-mail." />;
  const recarregar = async () => { await Promise.all([fila.recarregar(), lixeira.recarregar()]); };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <Painel leitura={fila} arquivo="correio-prioridades">
        {(d) => (
          <Bloco titulo={`Emergenciais e importantes · ${d.mensagens.length}`}>{d.mensagens.length === 0 ? <li style={{ listStyle: "none" }}>Nada importante esperando.</li> : d.mensagens.map((m) => (
            <li key={m.id}><strong>{m.classe === "emergencial" ? "Emergencial · " : ""}{quem(m)}</strong>{m.motivo && <small> · {m.motivo}</small>} <small style={suave}>· {quandoBRT(m.recebida_em)} · {m.conta}</small></li>))}</Bloco>
        )}
      </Painel>
      <Painel leitura={lixeira} arquivo="correio-lixeira">
        {(d) => (
          <Bloco titulo={`Na lixeira · últimos 30 dias · ${d.mensagens.length}`}>{d.mensagens.length === 0 ? <li style={{ listStyle: "none" }}>Nada foi para a lixeira.</li> : d.mensagens.map((m) => (
            <li key={m.id} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
              <span>{quem(m)} <small style={suave}>· {m.motivo || "sem motivo"} · {m.conta}</small></span>
              <button className="btn btn-secondary" disabled={ocupado} aria-label={`Restaurar ${m.assunto || "mensagem sem assunto"}`}
                onClick={() => agir(`m${m.id}`, () => api.post(`/api/v1/correio/mensagens/${m.id}/restaurar`), "Mensagem restaurada.", recarregar)}>Restaurar</button>
              <Aviso erro={erros[`m${m.id}`]} />
            </li>))}</Bloco>
        )}
      </Painel>
    </div>
  );
}
