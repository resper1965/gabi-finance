import { useState } from "react";
import { Bloco } from "../componentes/Bloco";
import { api } from "../lib/api";
import { useToast } from "../lib/toast";
import { useApi } from "../lib/useApi";

interface Empresa { id: string; nome: string; dados: Record<string, unknown> }
interface Pessoa { id: string; nome: string; dados: Record<string, unknown> }
interface Categoria { id: number; nome: string; nibo_category_id: string | null }

const RELACOES: [string, string][] = [["", "não definida"], ["contratante", "contratante (cobra reembolso)"], ["pj_titular", "PJ titular (lote do Nibo)"], ["outra", "outra"]];
const CAMPOS: [string, string][] = [["cpf", "CPF"], ["nascimento", "Nascimento"], ["documento", "Documento"]];
const caixa = { height: 32, border: "1px solid var(--color-divider)", background: "var(--color-surface)", color: "inherit", font: "500 14px var(--font-body)", padding: "0 8px" } as const;

/** Cadastros que a cobrança precisa (Fase 2): relação e e-mail das empresas, quem pode pedir, ids do Nibo e a liberação de dado sensível.
 *  Tudo é dado do Ricardo (R6): fica no cadastro, nunca no código. */
export function CadastrosCobranca() {
  const empresas = useApi<{ itens: Empresa[] }>("/api/v1/cadastros/empresas");
  const pessoas = useApi<{ itens: Pessoa[] }>("/api/v1/cadastros/pessoas");
  const categorias = useApi<{ itens: Categoria[] }>("/api/v1/cadastros/categorias");
  const nibo = useApi<{ socio_id: string | null }>("/api/v1/cadastros/nibo");
  const liberacoes = useApi<{ itens: { id: number; pessoa_id: string; campo: string }[] }>("/api/v1/cadastros/liberacoes");
  const avisar = useToast();
  const [edit, setEdit] = useState<Record<string, string>>({});
  const v = (k: string, padrao: string) => edit[k] ?? padrao;
  const set = (k: string, valor: string) => setEdit({ ...edit, [k]: valor });
  const [socio, setSocio] = useState<string | null>(null);
  const [lib, setLib] = useState({ pessoa: "", campo: "cpf" });

  const salvarEmpresa = async (e: Empresa) => {
    const relacao = v(`rel:${e.id}`, String(e.dados.relacao ?? "")), email = v(`mail:${e.id}`, String(e.dados.email_cobranca ?? ""));
    const dados: Record<string, unknown> = { ...e.dados, ...(relacao ? { relacao } : {}), ...(email ? { email_cobranca: email } : {}) };
    try { await api.patch(`/api/v1/cadastros/empresas/${e.id}`, { dados }); avisar(`${e.nome} salva.`); empresas.recarregar(); } catch (x) { avisar((x as Error).message); }
  };
  const salvarPessoa = async (p: Pessoa) => {
    const pode = edit[`pode:${p.id}`] !== undefined ? edit[`pode:${p.id}`] === "1" : p.dados.pode_pedir === true;
    const canais = v(`canais:${p.id}`, ((p.dados.canais as string[] | undefined) ?? []).join(", ")).split(",").map((c) => c.trim()).filter(Boolean);
    try { await api.patch(`/api/v1/cadastros/pessoas/${p.id}`, { dados: { ...p.dados, canais, pode_pedir: pode } }); avisar(`${p.nome} salva.`); pessoas.recarregar(); } catch (x) { avisar((x as Error).message); }
  };
  const salvarCategoria = async (c: Categoria) => {
    try { await api.patch(`/api/v1/cadastros/categorias/${c.id}`, { nibo_category_id: v(`nibo:${c.id}`, c.nibo_category_id ?? "") || null }); avisar(`${c.nome} salva.`); categorias.recarregar(); }
    catch (x) { avisar((x as Error).message); }
  };
  const salvarSocio = async () => {
    try { await api.put("/api/v1/cadastros/nibo", { socio_id: socio ?? nibo.env?.dados.socio_id ?? "" }); avisar("Sócio do Nibo salvo."); nibo.recarregar(); } catch (x) { avisar((x as Error).message); }
  };
  const liberar = async () => {
    try { await api.post("/api/v1/cadastros/liberacoes", { pessoa_id: lib.pessoa, campo: lib.campo }); avisar("Liberei UMA leitura para o agente. Fica registrado."); liberacoes.recarregar(); }
    catch (x) { avisar((x as Error).message); }
  };
  const linha = { display: "flex", gap: 8, flexWrap: "wrap" as const, alignItems: "center", padding: "8px 0", borderBottom: "1px solid var(--line2)" };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <Bloco titulo="Empresas" nota="relação e e-mail de cobrança">
        <section role="region" aria-label="Empresas">
          {(empresas.env?.dados.itens ?? []).map((e) => (
            <div key={e.id} style={linha}>
              <span style={{ flex: "1 1 120px", fontWeight: 600 }}>{e.nome}</span>
              <select aria-label={`Relação de ${e.nome}`} value={v(`rel:${e.id}`, String(e.dados.relacao ?? ""))} onChange={(x) => set(`rel:${e.id}`, x.target.value)} style={caixa}>
                {RELACOES.map(([k, r]) => <option key={k} value={k}>{r}</option>)}
              </select>
              <input aria-label={`E-mail de cobrança de ${e.nome}`} placeholder="e-mail de cobrança" value={v(`mail:${e.id}`, String(e.dados.email_cobranca ?? ""))} onChange={(x) => set(`mail:${e.id}`, x.target.value)} style={{ ...caixa, flex: "1 1 180px" }} />
              <button className="btn btn-secondary" aria-label={`Salvar ${e.nome}`} onClick={() => salvarEmpresa(e)}>Salvar</button>
            </div>
          ))}
        </section>
      </Bloco>
      <Bloco titulo="Quem pode fazer pedidos" nota="canal:identificador, separados por vírgula">
        <section role="region" aria-label="Quem pode fazer pedidos">
          {(pessoas.env?.dados.itens ?? []).map((p) => (
            <div key={p.id} style={linha}>
              <label style={{ display: "flex", alignItems: "center", gap: 6, flex: "1 1 140px" }}>
                <input type="checkbox" aria-label={`${p.nome} pode fazer pedidos`} checked={edit[`pode:${p.id}`] !== undefined ? edit[`pode:${p.id}`] === "1" : p.dados.pode_pedir === true}
                  onChange={(x) => set(`pode:${p.id}`, x.target.checked ? "1" : "0")} />{p.nome}
              </label>
              <input aria-label={`Canais de ${p.nome}`} placeholder="whatsapp:+55..., telegram:@..." value={v(`canais:${p.id}`, ((p.dados.canais as string[] | undefined) ?? []).join(", "))} onChange={(x) => set(`canais:${p.id}`, x.target.value)} style={{ ...caixa, flex: "2 1 220px" }} />
              <button className="btn btn-secondary" aria-label={`Salvar ${p.nome}`} onClick={() => salvarPessoa(p)}>Salvar</button>
            </div>
          ))}
        </section>
      </Bloco>
      <Bloco titulo="Categorias no Nibo" nota="sem o id equivalente, a despesa da Bekaa não vai no lote">
        <section role="region" aria-label="Categorias no Nibo">
          {(categorias.env?.dados.itens ?? []).map((c) => (
            <div key={c.id} style={linha}>
              <span style={{ flex: "1 1 140px" }}>{c.nome}</span>
              <input aria-label={`Id no Nibo de ${c.nome}`} placeholder="id da categoria no Nibo" value={v(`nibo:${c.id}`, c.nibo_category_id ?? "")} onChange={(x) => set(`nibo:${c.id}`, x.target.value)} style={{ ...caixa, flex: "1 1 200px" }} />
              <button className="btn btn-secondary" aria-label={`Salvar ${c.nome}`} onClick={() => salvarCategoria(c)}>Salvar</button>
            </div>
          ))}
        </section>
      </Bloco>
      <Bloco titulo="Nibo">
        <section role="region" aria-label="Nibo" style={linha}>
          <input aria-label="Id do sócio no Nibo" placeholder="stakeholderId do sócio" value={socio ?? nibo.env?.dados.socio_id ?? ""} onChange={(x) => setSocio(x.target.value)} style={{ ...caixa, flex: "1 1 240px" }} />
          <button className="btn btn-secondary" aria-label="Salvar sócio" onClick={salvarSocio}>Salvar</button>
          <span style={{ fontSize: 12.5, color: "var(--ink2)" }}>O token do Nibo não passa por aqui: vai no arquivo de ambiente do servidor.</span>
        </section>
      </Bloco>
      <Bloco titulo="Dado sensível" nota="cada liberação vale uma leitura pelo agente">
        <section role="region" aria-label="Dado sensível" style={linha}>
          <select aria-label="Pessoa" value={lib.pessoa} onChange={(x) => setLib({ ...lib, pessoa: x.target.value })} style={caixa}>
            <option value="">escolha</option>{(pessoas.env?.dados.itens ?? []).map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
          </select>
          <select aria-label="Campo" value={lib.campo} onChange={(x) => setLib({ ...lib, campo: x.target.value })} style={caixa}>
            {CAMPOS.map(([k, r]) => <option key={k} value={k}>{r}</option>)}
          </select>
          <button className="btn btn-primary" disabled={!lib.pessoa} onClick={liberar}>Liberar uma leitura</button>
          <span style={{ fontSize: 12.5, color: "var(--ink2)" }}>{(liberacoes.env?.dados.itens ?? []).length} liberação(ões) ainda não usada(s)</span>
        </section>
      </Bloco>
    </div>
  );
}
