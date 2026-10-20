import { useState } from "react";
import { Bloco } from "../componentes/Bloco";
import { Painel } from "../componentes/Painel";
import { Vazio } from "../componentes/Estados";
import { api } from "../lib/api";
import { Aviso, type Acao } from "../lib/useAcao";
import { useApi } from "../lib/useApi";

interface Proposta {
  id: number; tipo: "criar" | "corrigir"; conta: string;
  nome_antes: string | null; telefone_antes: string | null; nome_depois: string | null; telefone_depois: string | null;
  origem: "whatsapp" | "telefone_invalido"; estado: string;
}
interface Fila { itens: Proposta[]; escrita: "ligado" | "desligado" }

const suave = { color: "var(--ink2)" } as const;
const linha = { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", justifyContent: "space-between", borderTop: "1px solid var(--color-divider)", padding: "8px 0" } as const;
const lista = { listStyle: "none", margin: 0, padding: 0 } as const;
const AVISO_DESLIGADO = "A gravação está desligada: aprovar não grava ainda. Ligue em contatos.escrita quando quiser.";
const ROTA = "/api/v1/escuta/contatos/propostas";
const texto = (nome: string | null, tel: string | null) => [nome, tel].filter(Boolean).join(" ") || "—";

/** Escuta › Contatos: fila de propostas de criar/corrigir contato. Só grava o que o dono aprovar. */
export function ContatosPropostas({ acao }: { acao: Acao }) {
  const { ocupado, erros, agir } = acao;
  const [resumo, setResumo] = useState<string | null>(null);
  const leitura = useApi<Fila>(`${ROTA}?estado=pendente`);
  return (
    <Painel leitura={leitura} arquivo="escuta-contatos-propostas">
      {(d) => {
        const decidir = (p: Proposta, estado: "aprovada" | "recusada", ok: string) =>
          agir(`proposta${p.id}`, () => api.post(`${ROTA}/${p.id}/decisao`, { estado }), ok, leitura.recarregar);
        return (
          <Bloco titulo={`Propostas de contatos · ${d.itens.length}`} nota="Contatos novos do WhatsApp e telefones a corrigir. Nada muda no Google até você aprovar.">
            {d.escrita === "desligado" && <p role="status" style={{ margin: 0, ...suave }}>{AVISO_DESLIGADO}</p>}
            <Aviso erro={erros.propostas} />
            {resumo && <p role="status" style={{ margin: 0, ...suave }}>{resumo}</p>}
            {d.itens.some((p) => p.tipo === "corrigir") && (
              <div>
                <button className="btn btn-primary" disabled={ocupado} onClick={() => agir("propostas", async () => {
                  const r = await api.post<{ aprovadas: number }>(`${ROTA}/aprovar-correcoes`);
                  setResumo(`${r.dados.aprovadas} correção(ões) aprovada(s).`);
                }, "Correções aprovadas.", leitura.recarregar)}>Aprovar todas as correções de telefone</button>
              </div>)}
            {d.itens.length === 0 ? <Vazio frase="Nenhuma proposta pendente." /> : (
              <ul style={lista}>
                {d.itens.map((p) => {
                  const quem = p.nome_depois ?? p.telefone_depois ?? `proposta ${p.id}`;
                  return (
                    <li key={p.id} style={linha}>
                      <span>
                        <strong>{p.tipo === "criar" ? "Criar" : "Corrigir"}</strong> <span style={suave}>· {p.conta}</span><br />
                        <span style={suave}>{p.tipo === "criar" ? "— (novo)" : texto(p.nome_antes, p.telefone_antes)}</span>
                        {" → "}
                        <span>{texto(p.nome_depois, p.telefone_depois)}</span>
                      </span>
                      <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        <button className="btn btn-primary" disabled={ocupado} aria-label={`Aprovar ${quem}`} onClick={() => decidir(p, "aprovada", "Proposta aprovada.")}>Aprovar</button>
                        <button className="btn btn-secondary" disabled={ocupado} aria-label={`Recusar ${quem}`} onClick={() => decidir(p, "recusada", "Proposta recusada.")}>Recusar</button>
                      </span>
                      <Aviso erro={erros[`proposta${p.id}`]} />
                    </li>);
                })}
              </ul>)}
          </Bloco>
        );
      }}
    </Painel>
  );
}
