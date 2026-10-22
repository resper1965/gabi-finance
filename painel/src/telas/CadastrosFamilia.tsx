/** Casa › Cadastros › Família: ficha por pessoa (contato e documentos com número), propostas de documento e histórico com Desfazer.
 * Consome: /api/v1/familia (fichas, propostas, historico). O número do documento só aparece aqui, nunca em aviso ou erro. */
import { useState } from "react";
import { Bloco } from "../componentes/Bloco";
import { Painel } from "../componentes/Painel";
import { Vazio } from "../componentes/Estados";
import { api } from "../lib/api";
import { Aviso, useAcao } from "../lib/useAcao";
import { useApi } from "../lib/useApi";

const ROTA = "/api/v1" + "/familia"; // base; as rotas completas existem em docs/openapi.json
interface Resumo { id: string; nome: string; apelido: string | null; parentesco: string | null; nascimento: string | null; documentos_qtd: number }
interface Doc { id: number; tipo: string; pais: string; numero: string; emissor: string | null; emissao: string | null; validade: string | null; paperless_id: number | null; origem: string; atualizado_em: string | null }
interface Ficha {
  id: string; nome: string; nome_completo: string | null; apelido: string | null; parentesco: string | null; nascimento: string | null;
  telefones: string[]; emails: string[]; enderecos: unknown[]; documentos: Doc[]; divergencias: { documento_id: number; tipo: string; campos: string[] }[]; paperless_url: string | null;
}
interface DocProposto { tipo: string; pais: string; numero: string; emissor?: string | null; emissao?: string | null; validade?: string | null; paperless_id?: number | null }
interface Proposta { id: number; pessoa_id: string; conferir: number | boolean; origem: string; atual: (DocProposto & { id: number }) | null; proposto: DocProposto }
interface Mudanca { id: number; pessoa_id: string; campo: string; antes: unknown; depois: unknown; quem: string; quando: string; desfeito_em: string | null }

const suave = { color: "var(--ink2)" } as const;
const linha = { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", justifyContent: "space-between", borderTop: "1px solid var(--color-divider)", padding: "8px 0" } as const;
const lista = { listStyle: "none", margin: 0, padding: 0 } as const;
const destaque = { color: "var(--danger)", fontWeight: 600 } as const;

/** AAAA-MM-DD (ou ISO) para dd/mm/aaaa. */
export const dataBR = (iso: string | null | undefined) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : "—");
const venceEmBreve = (validade: string | null) => {
  if (!validade) return false;
  const limite = new Date(); limite.setMonth(limite.getMonth() + 6);
  return validade <= limite.toISOString().slice(0, 10);
};
const textoItem = (v: unknown): string => {
  if (typeof v === "string") return v;
  if (v && typeof v === "object") { const o = v as Record<string, unknown>; const t = o.texto ?? o.endereco; return typeof t === "string" ? t : JSON.stringify(v); }
  return String(v);
};
const valor = (v: unknown) => (Array.isArray(v) ? (v.length ? v.map(textoItem).join(", ") : "(vazio)") : v == null || v === "" ? "(vazio)" : textoItem(v));
const docTexto = (d: DocProposto | null) => (d ? `${d.tipo.toUpperCase()} ${d.numero} · validade ${dataBR(d.validade)}` : "— (novo)");

function Paperless({ id, base }: { id: number | null; base: string | null }) {
  if (id == null) return null;
  return base
    ? <a href={`${base.replace(/\/$/, "")}/documents/${id}/details`} target="_blank" rel="noreferrer">Paperless #{id}</a>
    : <span style={suave}>Paperless #{id}</span>;
}

function FichaPessoa({ id }: { id: string }) {
  const leitura = useApi<Ficha>(`${ROTA}/fichas/${encodeURIComponent(id)}`);
  return (
    <Painel leitura={leitura} arquivo="familia-ficha">
      {(f) => {
        const lst = (t: string, itens: unknown[]) => itens.length > 0 && <p style={{ margin: 0 }}><span style={suave}>{t}: </span>{itens.map((x, i) => <span key={i}>{i > 0 && " · "}<span>{textoItem(x)}</span></span>)}</p>;
        return (
          <Bloco titulo={f.nome_completo ?? f.nome} nota={[f.apelido, f.parentesco, f.nascimento && `nasc. ${dataBR(f.nascimento)}`].filter(Boolean).join(" · ")}>
            {lst("Telefones", f.telefones)}{lst("E-mails", f.emails)}{lst("Endereços", f.enderecos)}
            {f.documentos.length === 0 ? <Vazio frase="Nenhum documento cadastrado." /> : (
              <ul style={lista}>
                {f.documentos.map((d) => {
                  const breve = venceEmBreve(d.validade);
                  return (
                    <li key={d.id} style={linha}>
                      <span><strong>{d.tipo.toUpperCase()}</strong> <span style={suave}>{d.pais}</span> <span>{d.numero}</span>{d.emissor && <span style={suave}> · {d.emissor}</span>}</span>
                      <span style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                        <span style={suave}>validade</span> <span style={breve ? destaque : undefined}>{dataBR(d.validade)}</span>
                        {breve && <span style={destaque}>Vence em breve</span>}
                        <Paperless id={d.paperless_id} base={f.paperless_url} />
                      </span>
                    </li>);
                })}
              </ul>)}
            {f.divergencias.length > 0 && <p role="status" style={{ margin: 0, ...suave }}>Há proposta divergente do documento ativo ({f.divergencias.map((x) => `${x.tipo}: ${x.campos.join(", ")}`).join("; ")}).</p>}
          </Bloco>);
      }}
    </Painel>
  );
}

export function CadastrosFamilia() {
  const { ocupado, erros, agir } = useAcao();
  const [sel, setSel] = useState<string | null>(null);
  const fichas = useApi<{ itens: Resumo[] }>(`${ROTA}/fichas`);
  const propostas = useApi<{ itens: Proposta[] }>(`${ROTA}/propostas?estado=pendente`);
  const historico = useApi<{ itens: Mudanca[] }>(`${ROTA}/historico`);
  const nomes = new Map((fichas.env?.dados.itens ?? []).map((p) => [p.id, p.nome]));
  const recarregar = async () => { await Promise.all([propostas.recarregar(), historico.recarregar(), fichas.recarregar()]); };
  const agirEm = async (chave: string, fn: () => Promise<unknown>, ok: string) => { if (!(await agir(chave, fn, ok, recarregar))) await recarregar(); };
  const decidir = (p: Proposta, estado: "aprovada" | "recusada") =>
    agirEm(`proposta${p.id}`, () => api.post(`${ROTA}/propostas/${p.id}/decisao`, { estado }), estado === "aprovada" ? "Proposta aprovada." : "Proposta recusada.");
  return (
    <>
      <Painel leitura={fichas} arquivo="familia-fichas">
        {(d) => {
          const atual = sel ?? d.itens[0]?.id ?? null;
          return (
            <>
              <Bloco titulo={`Família · ${d.itens.length}`} nota="Quem está no cadastro. Documentos só mudam por proposta aprovada aqui.">
                {d.itens.length === 0 ? <Vazio frase="Ninguém no cadastro ainda." /> : (
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {d.itens.map((p) => (
                      <button key={p.id} className={`btn ${p.id === atual ? "btn-primary" : "btn-secondary"}`} aria-pressed={p.id === atual} onClick={() => setSel(p.id)}>
                        {p.apelido ?? p.nome} · {p.documentos_qtd}
                      </button>))}
                  </div>)}
              </Bloco>
              {atual && <FichaPessoa key={atual} id={atual} />}
            </>);
        }}
      </Painel>
      <Painel leitura={propostas} arquivo="familia-propostas">
        {(d) => (
          <Bloco titulo={`Propostas de documento · ${d.itens.length}`} nota="Nada muda no cadastro até você aprovar. 'conferir' = leitura duvidosa.">
            {d.itens.length === 0 ? <Vazio frase="Nenhuma proposta pendente." /> : (
              <ul style={lista}>
                {d.itens.map((p) => (
                  <li key={p.id} style={linha}>
                    <span>
                      <strong>{nomes.get(p.pessoa_id) ?? p.pessoa_id}</strong> <span style={suave}>· {p.origem}</span>
                      {!!p.conferir && <span style={destaque}> conferir</span>}<br />
                      <span style={suave}>{docTexto(p.atual)}</span>{" → "}<span>{docTexto(p.proposto)}</span>
                    </span>
                    <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <button className="btn btn-primary" disabled={ocupado} aria-label={`Aprovar proposta ${p.id}`} onClick={() => decidir(p, "aprovada")}>Aprovar</button>
                      <button className="btn btn-secondary" disabled={ocupado} aria-label={`Recusar proposta ${p.id}`} onClick={() => decidir(p, "recusada")}>Recusar</button>
                    </span>
                    <Aviso erro={erros[`proposta${p.id}`]} />
                  </li>))}
              </ul>)}
          </Bloco>)}
      </Painel>
      <Painel leitura={historico} arquivo="familia-historico">
        {(d) => (
          <Bloco titulo="Histórico de contato" nota="Mudanças de contato feitas pelo Hermes. Desfazer só vale se o valor ainda for o da mudança.">
            {d.itens.length === 0 ? <Vazio frase="Nenhuma mudança registrada." /> : (
              <ul style={lista}>
                {d.itens.map((h) => (
                  <li key={h.id} style={linha}>
                    <span>
                      <strong>{nomes.get(h.pessoa_id) ?? h.pessoa_id}</strong> <span style={suave}>· {h.campo} · {h.quem} · {dataBR(h.quando)}</span><br />
                      <span style={suave}>{valor(h.antes)}</span>{" → "}<span>{valor(h.depois)}</span>
                    </span>
                    {h.desfeito_em
                      ? <span style={suave}>desfeito em {dataBR(h.desfeito_em)}</span>
                      : <button className="btn btn-secondary" disabled={ocupado} aria-label={`Desfazer mudança ${h.id}`} onClick={() => agirEm(`hist${h.id}`, () => api.post(`${ROTA}/historico/${h.id}/desfazer`, {}), "Mudança desfeita.")}>Desfazer</button>}
                    <Aviso erro={erros[`hist${h.id}`]} />
                  </li>))}
              </ul>)}
          </Bloco>)}
      </Painel>
    </>
  );
}
