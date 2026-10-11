import { useState } from "react";
import { Painel } from "../../componentes/Painel";
import { useApi } from "../../lib/useApi";
import { dataCurta } from "../../lib/formato";
import { Bloco, quando, type Evento } from "./Hoje";

interface Dados { eventos: Evento[]; conflitos: { evento_a: number; evento_b: number; sugestao_inicio: string }[] }

const FUSO = "America/Sao_Paulo";
const DIA_MS = 86_400_000;
/** "AAAA-MM-DD" de hoje + `n` dias no fuso de Brasília (sem passar pelo fuso do navegador). */
export const diaLocal = (n: number) => new Intl.DateTimeFormat("sv-SE", { timeZone: FUSO }).format(new Date(Date.now() + n * DIA_MS));
const OPCOES: [string, string, number, number][] = [["hoje", "Hoje", 0, 0], ["amanha", "Amanhã", 1, 1], ["semana", "Próximos 7 dias", 0, 6]];

/** Agenda: compromissos por dia (evento que cruza a meia-noite aparece nos dois dias) e conflitos. A sugestão de horário é só uma PROPOSTA; nada é enviado a ninguém sem a sua confirmação. */
export function Agenda() {
  const [escolha, setEscolha] = useState("semana");
  const [, , de, ate] = OPCOES.find((o) => o[0] === escolha)!;
  const dias = Array.from({ length: ate - de + 1 }, (_, i) => diaLocal(de + i));
  const leitura = useApi<Dados>(`/api/v1/agenda?de=${dias[0]}&ate=${dias[dias.length - 1]}`);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div role="group" aria-label="Período" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {OPCOES.map(([k, rotulo]) => (
          <button key={k} className={`btn ${escolha === k ? "btn-primary" : "btn-secondary"}`} aria-pressed={escolha === k} onClick={() => setEscolha(k)}>{rotulo}</button>))}
      </div>
      <Painel leitura={leitura} arquivo="agenda">
        {(d) => {
          const nome = (id: number) => d.eventos.find((e) => e.id === id)?.titulo ?? `#${id}`;
          return (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {dias.map((dia) => {
                const doDia = d.eventos.filter((e) => e.dia_local <= dia && dia <= e.dia_fim_local);
                return (
                  <Bloco key={dia} titulo={dataCurta(dia)}>{doDia.length === 0 ? <li style={{ listStyle: "none" }}>Sem compromissos.</li> : doDia.map((e) => (
                    <li key={e.id}>{quando(e)} · {e.titulo ?? "(sem título)"}{e.privado && <small> · privado</small>} <small style={{ color: "var(--ink2)" }}>· {e.fonte}</small></li>))}</Bloco>);
              })}
              {d.conflitos.length > 0 && <Bloco titulo="Conflitos">{d.conflitos.map((c, i) => (
                <li key={i} data-conflito>{nome(c.evento_a)} × {nome(c.evento_b)} · a Gabi propõe {c.sugestao_inicio.slice(11, 16)} <small>(proposta: só sai após você confirmar)</small></li>))}</Bloco>}
            </div>
          );
        }}
      </Painel>
    </div>
  );
}
