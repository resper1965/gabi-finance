import { useState } from "react";
import { Bloco } from "../componentes/Bloco";
import { api } from "../lib/api";
import { useToast } from "../lib/toast";
import { useApi } from "../lib/useApi";

interface Empresa { id: string; nome: string; dados: Record<string, unknown> }
interface Pessoa { id: string; nome: string; dados: Record<string, unknown> }
interface Categoria { id: number; nome: string; nibo_category_id: string | null }

const RELACOES: [string, string][] = [["", "não definida"], ["contratante", "contratante (cobra reembolso)"], ["pj_titular", "PJ titular (lote do Nibo)"], ["outra", "outra"]];

/** Cadastros que a cobrança precisa (Fase 2): relação e e-mail das empresas, quem pode pedir, ids do Nibo e a liberação de dado sensível.
 *  Tudo é dado do Ricardo (R6): fica no cadastro, nunca no código. */
export function CadastrosCobranca() {
  const empresas = useApi<{ itens: Empresa[] }>("/api/v1/cadastros/empresas");
  const pessoas = useApi<{ itens: Pessoa[] }>("/api/v1/cadastros/pessoas");
  const categorias = useApi<{ itens: Categoria[] }>("/api/v1/cadastros/categorias");
  const nibo = useApi<{ socio_id: string | null }>("/api/v1/cadastros/nibo");
  const avisar = useToast();
  const [edit, setEdit] = useState<Record<string, string>>({});
  const v = (k: string, padrao: string) => edit[k] ?? padrao;
  const set = (k: string, valor: string) => setEdit({ ...edit, [k]: valor });
  const [socio, setSocio] = useState<string | null>(null);

  const salvarEmpresa = async (e: Empresa) => {
    const relacao = v(`rel:${e.id}`, String(e.dados.relacao ?? "")), email = v(`mail:${e.id}`, String(e.dados.email_cobranca ?? ""));
    const dados: Record<string, unknown> = { ...e.dados, ...(relacao ? { relacao } : {}), ...(email ? { email_cobranca: email } : {}) };
    try { await api.patch(`/api/v1/cadastros/empresas/${e.id}`, { dados }); avisar(`${e.nome} salva.`); empresas.recarregar(); } catch (x) { avisar((x as Error).message); }
  };
  const salvarPessoa = async (p: Pessoa) => {
    const canais = v(`canais:${p.id}`, ((p.dados.canais as string[] | undefined) ?? []).join(", ")).split(",").map((c) => c.trim()).filter(Boolean);
    try { await api.patch(`/api/v1/cadastros/pessoas/${p.id}`, { dados: { ...p.dados, canais } }); avisar(`${p.nome} salva.`); pessoas.recarregar(); } catch (x) { avisar((x as Error).message); }
  };
  const salvarCategoria = async (c: Categoria) => {
    try { await api.patch(`/api/v1/cadastros/categorias/${c.id}`, { nibo_category_id: v(`nibo:${c.id}`, c.nibo_category_id ?? "") || null }); avisar(`${c.nome} salva.`); categorias.recarregar(); }
    catch (x) { avisar((x as Error).message); }
  };
  const salvarSocio = async () => {
    try { await api.put("/api/v1/cadastros/nibo", { socio_id: socio ?? nibo.env?.dados.socio_id ?? "" }); avisar("Sócio do Nibo salvo."); nibo.recarregar(); } catch (x) { avisar((x as Error).message); }
  };

  return (
    <div className="pilha" style={{ gap: 40 }}>
      <Bloco titulo="Empresas" nota="relação e e-mail de cobrança">
        <section role="region" aria-label="Empresas">
          {(empresas.env?.dados.itens ?? []).map((e) => (
            <div key={e.id} className="cadastro-linha">
              <span className="forte">{e.nome}</span>
              <select aria-label={`Relação de ${e.nome}`} value={v(`rel:${e.id}`, String(e.dados.relacao ?? ""))} onChange={(x) => set(`rel:${e.id}`, x.target.value)}>
                {RELACOES.map(([k, r]) => <option key={k} value={k}>{r}</option>)}
              </select>
              <input aria-label={`E-mail de cobrança de ${e.nome}`} placeholder="e-mail de cobrança" value={v(`mail:${e.id}`, String(e.dados.email_cobranca ?? ""))} onChange={(x) => set(`mail:${e.id}`, x.target.value)} />
              <button className="btn btn-sm" aria-label={`Salvar ${e.nome}`} onClick={() => salvarEmpresa(e)}>Salvar</button>
            </div>
          ))}
        </section>
      </Bloco>
      <Bloco titulo="Canais de cada pessoa" nota="canal:identificador, separados por vírgula">
        <section role="region" aria-label="Canais de cada pessoa">
          {(pessoas.env?.dados.itens ?? []).map((p) => (
            <div key={p.id} className="cadastro-linha">
              <span className="forte">{p.nome}</span>
              <input aria-label={`Canais de ${p.nome}`} placeholder="whatsapp:+55..., telegram:@..." value={v(`canais:${p.id}`, ((p.dados.canais as string[] | undefined) ?? []).join(", "))} onChange={(x) => set(`canais:${p.id}`, x.target.value)} />
              <button className="btn btn-sm" aria-label={`Salvar ${p.nome}`} onClick={() => salvarPessoa(p)}>Salvar</button>
            </div>
          ))}
        </section>
      </Bloco>
      <Bloco titulo="Categorias no Nibo" nota="sem o id equivalente, a despesa da Bekaa não vai no lote">
        <section role="region" aria-label="Categorias no Nibo">
          {(categorias.env?.dados.itens ?? []).map((c) => (
            <div key={c.id} className="cadastro-linha">
              <span className="forte">{c.nome}</span>
              <input aria-label={`Id no Nibo de ${c.nome}`} placeholder="id da categoria no Nibo" value={v(`nibo:${c.id}`, c.nibo_category_id ?? "")} onChange={(x) => set(`nibo:${c.id}`, x.target.value)} />
              <button className="btn btn-sm" aria-label={`Salvar ${c.nome}`} onClick={() => salvarCategoria(c)}>Salvar</button>
            </div>
          ))}
        </section>
      </Bloco>
      <Bloco titulo="Nibo">
        <section role="region" aria-label="Nibo" className="cadastro-linha">
          <input aria-label="Id do sócio no Nibo" placeholder="stakeholderId do sócio" value={socio ?? nibo.env?.dados.socio_id ?? ""} onChange={(x) => setSocio(x.target.value)} />
          <button className="btn btn-sm" aria-label="Salvar sócio" onClick={salvarSocio}>Salvar</button>
          <span className="miudo" style={{ gridColumn: "1 / -1" }}>O token do Nibo não passa por aqui: vai no arquivo de ambiente do servidor.</span>
        </section>
      </Bloco>
    </div>
  );
}
