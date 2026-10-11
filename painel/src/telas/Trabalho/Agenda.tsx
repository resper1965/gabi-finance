import { Painel } from "../../componentes/Painel";
import { useApi } from "../../lib/useApi";
import { dataCurta } from "../../lib/formato";
import { Bloco, quando, type Evento } from "./Hoje";

interface Dados { eventos: Evento[]; conflitos: { evento_a: number; evento_b: number; sugestao_inicio: string }[] }

/** Agenda: eventos e conflitos. A sugestão de horário é só uma PROPOSTA; nada é enviado a ninguém sem a sua confirmação. */
export function Agenda() {
  const leitura = useApi<Dados>("/api/v1/agenda");
  return (
    <Painel leitura={leitura} arquivo="agenda">
      {(d) => {
        const nome = (id: number) => d.eventos.find((e) => e.id === id)?.titulo ?? `#${id}`;
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <Bloco titulo="Compromissos">{d.eventos.length === 0 ? <li style={{ listStyle: "none" }}>Sem compromissos no período.</li> : d.eventos.map((e) => (
              <li key={e.id}>{dataCurta(e.dia_local)} {quando(e)} · {e.titulo ?? "(sem título)"}{e.privado && <small> · privado</small>} <small style={{ color: "var(--ink2)" }}>· {e.fonte}</small></li>))}</Bloco>
            {d.conflitos.length > 0 && <Bloco titulo="Conflitos">{d.conflitos.map((c, i) => (
              <li key={i} data-conflito>{nome(c.evento_a)} × {nome(c.evento_b)} · a Gabi propõe {c.sugestao_inicio.slice(11, 16)} <small>(proposta: só sai após você confirmar)</small></li>))}</Bloco>}
          </div>
        );
      }}
    </Painel>
  );
}
