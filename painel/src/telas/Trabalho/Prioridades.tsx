import { Painel } from "../../componentes/Painel";
import { Vazio } from "../../componentes/Estados";
import { api } from "../../lib/api";
import { Aviso, useAcao } from "../../lib/useAcao";
import { useApi } from "../../lib/useApi";
import { quandoBRT } from "../CadastrosCorreio";
import { Bloco } from "./Hoje";

interface Msg { id: number; conta: string; remetente: string | null; assunto: string | null; recebida_em: string; classe: "emergencial" | "importante" | "normal" | "lixo"; prioridade: number | null; motivo: string | null; movida_em?: string; conta_lixeira?: 0 | 1; conta_desligada?: boolean; dispensada_em?: string }

const suave = { color: "var(--ink2)" } as const;
const quem = (m: Msg) => `${m.remetente || "?"} — ${m.assunto || "(sem assunto)"}`;

/** Mensagens › Prioridades: o que exige ação primeiro (com Dispensar), o lixo sugerido que NÃO foi movido (Mover para a lixeira ou Não é lixo) e o que a Gabi
 * mandou para a lixeira (com Restaurar). Só cabeçalho e motivo; o corpo fica no Gmail. Nada aqui apaga e-mail de vez: só lixeira recuperável. */
export function Prioridades() {
  const fila = useApi<{ mensagens: Msg[] }>("/api/v1/correio/prioridades");
  const lixeira = useApi<{ mensagens: Msg[] }>("/api/v1/correio/lixeira");
  const sugerido = useApi<{ mensagens: Msg[] }>("/api/v1/correio/lixo-sugerido");
  const dispensadas = useApi<{ mensagens: Msg[] }>("/api/v1/correio/dispensadas");
  const { ocupado, erros, agir } = useAcao();
  if ([fila, lixeira, sugerido, dispensadas].some((l) => l.estado === "erro" && l.erro?.status === 403)) return <Vazio frase="Só o dono vê o e-mail." />;
  const recarregar = async () => { await Promise.all([fila.recarregar(), lixeira.recarregar(), sugerido.recarregar(), dispensadas.recarregar()]); };
  const dispensar = (m: Msg) => agir(`m${m.id}`, () => api.post(`/api/v1/correio/mensagens/${m.id}/dispensar`), "Mensagem dispensada.", recarregar);
  const desfazer = (m: Msg) => agir(`m${m.id}`, () => api.post(`/api/v1/correio/mensagens/${m.id}/desfazer-dispensa`), "Dispensa desfeita.", recarregar);
  const mover = (m: Msg) => agir(`m${m.id}`, () => api.post(`/api/v1/correio/mensagens/${m.id}/lixeira`), "Mensagem movida para a lixeira.", recarregar);
  const sempreLixo = (m: Msg, mover: boolean) => agir(`m${m.id}`, async () => {
    await api.post(`/api/v1/correio/mensagens/${m.id}/regra-lixo`, { tipo: "remetente" });
    if (mover) await api.post(`/api/v1/correio/mensagens/${m.id}/lixeira`);
  }, "Regra criada: o que vier deste remetente vai para a lixeira.", recarregar);
  const naoELixo = (m: Msg) => agir(`m${m.id}`, () => api.post(`/api/v1/correio/mensagens/${m.id}/nao-e-lixo`), "Marcada como não é lixo.", recarregar);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <Painel leitura={fila} arquivo="correio-prioridades">
        {(d) => (
          <Bloco titulo={`Emergenciais e importantes · ${d.mensagens.length}`}>{d.mensagens.length === 0 ? <li style={{ listStyle: "none" }}>Nada importante esperando.</li> : d.mensagens.map((m) => (
            <li key={m.id} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
              <span><strong>{m.classe === "emergencial" ? "Emergencial · " : ""}{quem(m)}</strong>{m.motivo && <small> · {m.motivo}</small>} <small style={suave}>· {quandoBRT(m.recebida_em)} · {m.conta}</small></span>
              <button className="btn btn-secondary" disabled={ocupado} aria-label={`Dispensar ${m.assunto || "mensagem sem assunto"}`} onClick={() => dispensar(m)}>Dispensar</button>
              <Aviso erro={erros[`m${m.id}`]} />
            </li>))}</Bloco>
        )}
      </Painel>
      <Painel leitura={sugerido} arquivo="correio-lixo-sugerido">
        {(d) => (
          <Bloco titulo={`Lixo sugerido (não movido) · ${d.mensagens.length}`}>{d.mensagens.length === 0 ? <li style={{ listStyle: "none" }}>Nenhum lixo sugerido esperando.</li> : d.mensagens.map((m) => (
            <li key={m.id} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
              <span>{quem(m)} <small style={suave}>· {m.motivo || "sem motivo"} · {m.conta}{m.conta_lixeira ? "" : " · lixeira desligada nesta conta"}</small></span>
              <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button className="btn btn-secondary" disabled={ocupado || !m.conta_lixeira} title={m.conta_lixeira ? undefined : "Ligue a lixeira desta conta em Cadastros › E-mail"} aria-label={`Mover para a lixeira ${m.assunto || "mensagem sem assunto"}`}
                  onClick={() => mover(m)}>Mover para a lixeira</button>
                <button className="btn btn-secondary" disabled={ocupado} title="Cria a regra: tudo que vier deste remetente vai para a lixeira (desfaça em Cadastros › E-mail)" aria-label={`Sempre lixo ${m.assunto || "mensagem sem assunto"}`}
                  onClick={() => sempreLixo(m, !!m.conta_lixeira)}>Sempre lixo deste remetente</button>
                <button className="btn btn-secondary" disabled={ocupado} aria-label={`Não é lixo ${m.assunto || "mensagem sem assunto"}`} onClick={() => naoELixo(m)}>Não é lixo</button>
              </span>
              <Aviso erro={erros[`m${m.id}`]} />
            </li>))}</Bloco>
        )}
      </Painel>
      <Painel leitura={lixeira} arquivo="correio-lixeira">
        {(d) => (
          <Bloco titulo={`Na lixeira · últimos 30 dias · ${d.mensagens.length}`}>{d.mensagens.length === 0 ? <li style={{ listStyle: "none" }}>Nada foi para a lixeira.</li> : d.mensagens.map((m) => (
            <li key={m.id} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
              <span>{quem(m)} <small style={suave}>· {m.motivo || "sem motivo"} · {m.conta}{m.conta_desligada ? " · conta desligada (ainda dá para restaurar)" : ""}</small></span>
              <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button className="btn btn-secondary" disabled={ocupado} aria-label={`Sempre lixo ${m.assunto || "mensagem sem assunto"}`} onClick={() => sempreLixo(m, false)}>Sempre lixo deste remetente</button>
                <button className="btn btn-secondary" disabled={ocupado} aria-label={`Restaurar ${m.assunto || "mensagem sem assunto"}`}
                  onClick={() => agir(`m${m.id}`, () => api.post(`/api/v1/correio/mensagens/${m.id}/restaurar`), "Mensagem restaurada.", recarregar)}>Restaurar</button>
              </span>
              <Aviso erro={erros[`m${m.id}`]} />
            </li>))}</Bloco>
        )}
      </Painel>
      <Painel leitura={dispensadas} arquivo="correio-dispensadas">
        {(d) => d.mensagens.length === 0 ? null : (
          <Bloco titulo={`Dispensadas · últimos 30 dias · ${d.mensagens.length}`}>{d.mensagens.map((m) => (
            <li key={m.id} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
              <span>{quem(m)} <small style={suave}>· {m.conta}</small></span>
              <button className="btn btn-secondary" disabled={ocupado} aria-label={`Desfazer dispensa de ${m.assunto || "mensagem sem assunto"}`} onClick={() => desfazer(m)}>Desfazer</button>
              <Aviso erro={erros[`m${m.id}`]} />
            </li>))}</Bloco>
        )}
      </Painel>
    </div>
  );
}
