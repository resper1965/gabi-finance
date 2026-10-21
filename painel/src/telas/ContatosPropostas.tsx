import { useState, type ReactNode } from "react";
import { Bloco } from "../componentes/Bloco";
import { Painel } from "../componentes/Painel";
import { Vazio } from "../componentes/Estados";
import { api } from "../lib/api";
import { Aviso, type Acao } from "../lib/useAcao";
import { useApi } from "../lib/useApi";

type Tipo = "criar" | "corrigir" | "corrigir_nome" | "adicionar_email" | "apagar_telefone" | "apagar_contato";
const ROTULOS: Record<Tipo, string> = { criar: "Criar", corrigir: "Corrigir", corrigir_nome: "Corrigir nome", adicionar_email: "Adicionar e-mail", apagar_telefone: "Apagar telefone", apagar_contato: "Apagar contato" };
const EM_LOTE: Tipo[] = ["corrigir", "corrigir_nome", "adicionar_email"];  // apagar nunca entra em lote
const APAGA = (t: Tipo) => t === "apagar_telefone" || t === "apagar_contato";
const CONFIRMA = "Apagar não dá para desfazer no Outlook. Aprovar esta proposta?";

interface Proposta {
  id: number; tipo: Tipo; conta: string;
  nome_antes: string | null; telefone_antes: string | null; nome_depois: string | null; telefone_depois: string | null; email_depois: string | null;
  origem: "whatsapp" | "telefone_invalido" | "nome_sujo" | "nome_curto" | "google_email"; estado: string;
}
interface Fila { itens: Proposta[]; escrita: "ligado" | "desligado" }

const suave = { color: "var(--ink2)" } as const;
const linha = { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", justifyContent: "space-between", borderTop: "1px solid var(--color-divider)", padding: "8px 0" } as const;
const lista = { listStyle: "none", margin: 0, padding: 0 } as const;
const AVISO_DESLIGADO = "A gravação está desligada: aprovar não grava ainda. Ligue em contatos.escrita quando quiser.";
const ROTA = "/api/v1/escuta/contatos/propostas";
const texto = (nome: string | null, tel: string | null) => [nome, tel].filter(Boolean).join(" ") || "—";

const emails = (e: string | null) => (e ? e.split(";").filter(Boolean).join(", ") : "—");  // o banco guarda separado por ;

const rotulo = (acao: string, p: Proposta) => `${acao} proposta ${p.id} (${p.tipo})`; // sem nome, telefone nem e-mail

function Linha({ p, children }: { p: Proposta; children: ReactNode }) {
  return (
    <li style={linha}>
      <span>
        <strong>{ROTULOS[p.tipo]}</strong> <span style={suave}>· {p.conta}</span><br />
        <span style={suave}>{p.tipo === "criar" ? "— (novo)" : texto(p.nome_antes, p.telefone_antes)}</span>
        {" → "}
        <span>{p.tipo === "apagar_telefone" ? "(telefone removido)" : p.tipo === "apagar_contato" ? "(contato apagado)" : p.tipo === "adicionar_email" ? emails(p.email_depois) : texto(p.nome_depois, p.telefone_depois)}</span>
      </span>
      {children}
    </li>);
}

/** Escuta › Contatos: fila de propostas de contato (criar, corrigir, corrigir nome, adicionar e-mail, apagar telefone, apagar contato). Só grava o que o dono aprovar; uma aprovada ainda pode ser recusada antes da gravação. */
export function ContatosPropostas({ acao }: { acao: Acao }) {
  const { ocupado, erros, agir } = acao;
  const [resumo, setResumo] = useState<string | null>(null);
  const leitura = useApi<Fila>(`${ROTA}?estado=pendente`);
  const aprovadas = useApi<Fila>(`${ROTA}?estado=aprovada`);
  const recarregar = async () => { await Promise.all([leitura.recarregar(), aprovadas.recarregar()]); };
  const executar = async (chave: string, fn: () => Promise<unknown>, ok: string) => {
    if (!(await agir(chave, fn, ok, recarregar))) await recarregar(); // falhou (ex.: 409 já decidida): relê para não mostrar fila velha
  };
  const decidir = (p: Proposta, estado: "aprovada" | "recusada", ok: string) => {
    setResumo(null);
    if (estado === "aprovada" && APAGA(p.tipo) && !window.confirm(CONFIRMA)) return Promise.resolve();
    return executar(`proposta${p.id}`, () => api.post(`${ROTA}/${p.id}/decisao`, { estado }), ok);
  };
  const aguardando = aprovadas.env?.dados.itens ?? [];
  return (
    <Painel leitura={leitura} arquivo="escuta-contatos-propostas">
      {(d) => {
        const correcoes = d.itens.filter((p) => EM_LOTE.includes(p.tipo)).map((p) => p.id);
        return (
          <Bloco titulo={`Propostas de contatos · ${d.itens.length}`} nota="Contatos novos do WhatsApp, telefones e nomes a corrigir, e-mails a adicionar, e o que apagar. Nada muda na Microsoft (conta ness) até você aprovar.">
            {d.escrita === "desligado" && <p role="status" style={{ margin: 0, ...suave }}>{AVISO_DESLIGADO}</p>}
            <Aviso erro={erros.propostas} />
            {resumo && <p role="status" style={{ margin: 0, ...suave }}>{resumo}</p>}
            {correcoes.length > 0 && (
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <button className="btn btn-primary" disabled={ocupado} onClick={() => { setResumo(null); return executar("propostas", async () => {
                  const r = await api.post<{ aprovadas: number }>(`${ROTA}/aprovar-correcoes`, { ids: correcoes });
                  setResumo(`${r.dados.aprovadas} correção(ões) aprovada(s).`);
                }, "Correções aprovadas."); }}>Aprovar todas as correções</button>
                <span style={suave}>Só as correções (telefone e nome) e os e-mails a adicionar listados aqui. Não inclui contatos novos nem apagar.</span>
              </div>)}
            {d.itens.length === 0 ? <Vazio frase="Nenhuma proposta pendente." /> : (
              <ul style={lista}>
                {d.itens.map((p) => (
                  <Linha key={p.id} p={p}>
                    <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <button className="btn btn-primary" disabled={ocupado} aria-label={rotulo("Aprovar", p)} onClick={() => decidir(p, "aprovada", "Proposta aprovada.")}>Aprovar</button>
                      <button className="btn btn-secondary" disabled={ocupado} aria-label={rotulo("Recusar", p)} onClick={() => decidir(p, "recusada", "Proposta recusada.")}>Recusar</button>
                    </span>
                    <Aviso erro={erros[`proposta${p.id}`]} />
                  </Linha>))}
              </ul>)}
            {aguardando.length > 0 && (
              <>
                <h4 style={{ margin: "8px 0 0" }}>Aprovadas aguardando gravação · {aguardando.length}</h4>
                <ul style={lista}>
                  {aguardando.map((p) => (
                    <Linha key={p.id} p={p}>
                      <button className="btn btn-secondary" disabled={ocupado} aria-label={rotulo("Recusar", p)} onClick={() => decidir(p, "recusada", "Aprovação desfeita.")}>Recusar</button>
                      <Aviso erro={erros[`proposta${p.id}`]} />
                    </Linha>))}
                </ul>
              </>)}
          </Bloco>
        );
      }}
    </Painel>
  );
}
