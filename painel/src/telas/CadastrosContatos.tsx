import { useEffect, useRef, useState } from "react";
import { Bloco } from "../componentes/Bloco";
import { Painel } from "../componentes/Painel";
import { Vazio } from "../componentes/Estados";
import { api } from "../lib/api";
import { Aviso, useAcao, type Acao } from "../lib/useAcao";
import { useApi } from "../lib/useApi";
import { ContatosPropostas } from "./ContatosPropostas";

interface Contato { nome: string | null; telefone: string; contas: string[]; ja_e_pessoa: boolean }
interface ListaContatos { itens: Contato[]; total: number; limite: number; offset: number }

const suave = { color: "var(--ink2)" } as const;
const linha = { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", justifyContent: "space-between", borderTop: "1px solid var(--color-divider)", padding: "8px 0" } as const;
const lista = { listStyle: "none", margin: 0, padding: 0 } as const;

const POR_PAGINA = 50;
const MAX_TRAZER = 100;

export function Contatos({ acao }: { acao: Acao }) {
  const { ocupado, erros, agir } = acao;
  const [busca, setBusca] = useState("");
  const [termo, setTermo] = useState(""); // a busca só vale ao enviar o formulário
  const [pagina, setPagina] = useState(0);
  const [marcados, setMarcados] = useState<Set<string>>(new Set());
  const [resumo, setResumo] = useState<string | null>(null);
  const [apagando, setApagando] = useState(false);
  const leitura = useApi<ListaContatos>(`/api/v1/contatos?busca=${encodeURIComponent(termo)}&limite=${POR_PAGINA}&offset=${pagina * POR_PAGINA}`);
  const confirmar = useRef<HTMLButtonElement>(null);
  const apagar = useRef<HTMLButtonElement>(null);
  const voltar = useRef(false);
  useEffect(() => {
    if (apagando) confirmar.current?.focus();
    else if (voltar.current) { apagar.current?.focus(); voltar.current = false; }
  }, [apagando]);
  const alternar = (tel: string) => setMarcados((m) => { const n = new Set(m); if (n.has(tel)) n.delete(tel); else n.add(tel); return n; });
  const demais = marcados.size > MAX_TRAZER;
  return (
    <Painel leitura={leitura} arquivo="contatos">
      {(d) => (
        <Bloco titulo={`Contatos do Google · ${d.total}`} nota="Só nome e telefone, lidos das suas contas do Google. Só grava o que você aprovar abaixo.">
          <Aviso erro={erros.contatos} />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <button className="btn btn-primary" disabled={ocupado} onClick={() => agir("contatos", async () => {
              const r = await api.post<{ contas: Record<string, { lidos?: number; erro?: string }>; total: number; invalidos: number }>("/api/v1/contatos/sincronizar");
              const falhas = Object.entries(r.dados.contas).filter(([, v]) => v.erro).map(([conta, v]) => `${conta} (${v.erro})`);
              setResumo(`Sincronizado: ${r.dados.total} contatos, ${r.dados.invalidos} números inválidos pulados.` + (falhas.length ? ` Falharam: ${falhas.join("; ")}.` : ""));
              setMarcados(new Set()); setPagina(0);
            }, "Contatos sincronizados.", leitura.recarregar)}>Sincronizar agora</button>
            <a className="btn btn-secondary" href="/api/v1/contatos/so-na-ness.csv" download>Baixar contatos só na ness (CSV)</a>
            <button ref={apagar} className="btn btn-secondary" disabled={ocupado} onClick={() => setApagando(true)}>Apagar contatos</button>
          </div>
          {resumo && <p role="status" style={{ margin: 0, ...suave }}>{resumo}</p>}
          <ContatosPropostas acao={acao} />
          {apagando && (
            <div role="alert" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <p style={{ margin: 0 }}>Apagar todos os contatos guardados? As pessoas já criadas a partir deles ficam.</p>
              <span style={{ display: "flex", gap: 8 }}>
                <button ref={confirmar} className="btn btn-primary" disabled={ocupado} onClick={async () => {
                  if (await agir("contatos", () => api.delete("/api/v1/contatos"), "Contatos apagados.", leitura.recarregar)) { setApagando(false); setMarcados(new Set()); setResumo(null); setPagina(0); }
                }}>Confirmar apagar contatos</button>
                <button className="btn btn-secondary" disabled={ocupado} onClick={() => { voltar.current = true; setApagando(false); }}>Cancelar</button>
              </span>
            </div>)}
          <form style={{ display: "flex", gap: 8, flexWrap: "wrap" }} onSubmit={(e) => { e.preventDefault(); setPagina(0); setTermo(busca.trim()); }}>
            <input aria-label="Buscar contato" value={busca} onChange={(e) => setBusca(e.target.value)} />
            <button className="btn btn-secondary" type="submit">Buscar</button>
          </form>
          {d.itens.length === 0 ? <Vazio frase={termo ? "Nenhum contato encontrado." : "Nenhum contato ainda. Use Sincronizar agora."} /> : (
            <ul style={lista}>
              {d.itens.map((c) => {
                const quem = c.nome ?? c.telefone;
                const rotulo = c.nome ? `${c.nome} ${c.telefone}` : c.telefone;
                return (
                  <li key={c.telefone} style={linha}>
                    <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <input type="checkbox" aria-label={`Selecionar ${rotulo}`} disabled={ocupado || c.ja_e_pessoa} checked={marcados.has(c.telefone)} onChange={() => alternar(c.telefone)} />
                      <span><strong>{quem}</strong>{c.nome && <span style={suave}> · {c.telefone}</span>}</span>
                    </label>
                    <span style={suave}>{c.ja_e_pessoa ? "já é pessoa" : c.contas.join(", ")}</span>
                  </li>);
              })}
            </ul>)}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <button className="btn btn-secondary" disabled={pagina === 0} onClick={() => setPagina((p) => p - 1)}>Anterior</button>
            <button className="btn btn-secondary" disabled={(pagina + 1) * POR_PAGINA >= d.total} onClick={() => setPagina((p) => p + 1)}>Próxima</button>
            <button className="btn btn-primary" disabled={ocupado || marcados.size === 0 || demais} onClick={() => agir("contatos", async () => {
              const r = await api.post<{ criadas: number; ignoradas: number }>("/api/v1/contatos/trazer", { telefones: [...marcados] });
              setResumo(`Criadas ${r.dados.criadas} pessoas, ${r.dados.ignoradas} ignoradas.`);
              setMarcados(new Set());
            }, "Contatos trazidos.", leitura.recarregar)}>Trazer dos contatos</button>
            <span style={suave}>{marcados.size} selecionado(s){demais ? ` · no máximo ${MAX_TRAZER} por vez` : ""}</span>
          </div>
        </Bloco>
      )}
    </Painel>
  );
}

/** Cadastros › Contatos: contatos do Google e do Graph da ness, trazer como pessoa e a fila de propostas de escrita. */
export function CadastrosContatos() {
  const acao = useAcao();
  return <Contatos acao={acao} />;
}
