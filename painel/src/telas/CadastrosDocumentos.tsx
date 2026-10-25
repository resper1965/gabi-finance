/** Casa › Cadastros › Documentos: propostas de documento (aprovar, recusar, corrigir campo, acrescentar ou remover número e data,
 * trocar titular, dar nome ao bem novo), vencimentos, documentos
 * por pessoa (com contato) e por bem, com número completo e botão copiar, e o histórico de contato da família com Desfazer.
 * Consome: /api/v1/documentos (propostas, titulares, vencimentos) e /api/v1/familia/historico. Número completo só aqui (boss). */
import { useState } from "react";
import { Bloco } from "../componentes/Bloco";
import { Painel } from "../componentes/Painel";
import { Vazio } from "../componentes/Estados";
import { api } from "../lib/api";
import { useToast } from "../lib/toast";
import { Aviso, useAcao } from "../lib/useAcao";
import { useApi } from "../lib/useApi";

interface Numero { nome: string; valor: string }
interface Data { tipo: string; data: string }
interface DocBase { titular_tipo: string; titular_id: string | null; tipo: string; pais: string; emissor: string | null; numeros: Numero[]; datas: Data[] }
interface Doc extends DocBase { id: number; titular_id: string; paperless_id: number | null; origem: string }
interface BemNovo { tipo: string; nome: string; dados: Record<string, unknown> }
interface Proposta {
  id: number; titular: { tipo: string; id: string; nome: string | null } | null; doc: DocBase; bem_novo: BemNovo | null;
  conferir: boolean; motivos: string[]; paperless_id: number | null; origem: string; atual: Doc | null;
}
interface Pessoa { id: string; nome: string; nome_completo: string | null; apelido: string | null; parentesco: string | null; nascimento: string | null; telefones: string[]; emails: string[]; enderecos: unknown[]; documentos: Doc[] }
interface Bem { id: string; tipo: string; nome: string; dados: Record<string, unknown>; documentos: Doc[] }
interface Titulares { pessoas: Pessoa[]; bens: Bem[]; paperless_url: string | null }
interface Vencimento { documento_id: number; titular_nome: string; tipo: string; data_tipo: string; data: string; vencido: boolean }
interface Mudanca { id: number; pessoa_id: string; campo: string; antes: unknown; depois: unknown; quem: string; quando: string; desfeito_em: string | null }

const suave = { color: "var(--ink2)" } as const;
const linha = { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", justifyContent: "space-between", borderTop: "1px solid var(--color-divider)", padding: "8px 0" } as const;
const lista = { listStyle: "none", margin: 0, padding: 0 } as const;
const destaque = { color: "var(--danger)", fontWeight: 600 } as const;
const atencao = { color: "var(--warn)", fontWeight: 600 } as const;
const grupo = { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" } as const;

const DATAS_VENCE = ["validade", "vigencia_fim", "vencimento"];
const TIPOS_DATA = ["emissao", "validade", "vigencia_inicio", "vigencia_fim", "vencimento", "renovacao"];
const ROTULO_DATA: Record<string, string> = { emissao: "emissão", validade: "validade", vigencia_inicio: "início da vigência", vigencia_fim: "fim da vigência", vencimento: "vencimento", renovacao: "renovação" };

/** AAAA-MM-DD (ou ISO) para dd/mm/aaaa. */
const dataBR = (iso: string | null | undefined) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : "—");
const isoLocal = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
/** A última data entre validade, fim de vigência e vencimento (ou null). */
const venceEm = (d: { datas: Data[] }) => d.datas.filter((x) => DATAS_VENCE.includes(x.tipo)).map((x) => x.data).sort().pop() ?? null;
/** "vencido" (antes de hoje), "atencao" (até 60 dias) ou null; datas no fuso local. */
const situacao = (data: string | null): "vencido" | "atencao" | null => {
  if (!data) return null;
  const hoje = new Date(); const limite = new Date(); limite.setDate(limite.getDate() + 60);
  return data < isoLocal(hoje) ? "vencido" : data <= isoLocal(limite) ? "atencao" : null;
};
function Situacao({ s }: { s: "vencido" | "atencao" | null }) {
  if (!s) return null;
  return s === "vencido" ? <span style={destaque}>Vencido</span> : <span style={atencao}>Vence em até 60 dias</span>;
}
// Endereço em dict (forma do yaml): "logradouro, bairro, cidade/uf, cep", sem as partes vazias (o mesmo de formatar_endereco no brain).
const parte = (x: unknown) => (x == null || typeof x === "boolean" ? "" : String(x).trim());
const formatarEndereco = (o: Record<string, unknown>) =>
  [parte(o.logradouro), parte(o.bairro), [parte(o.cidade), parte(o.uf)].filter(Boolean).join("/"), parte(o.cep)].filter(Boolean).join(", ");
const textoItem = (v: unknown): string => {
  if (typeof v === "string") return v;
  if (v && typeof v === "object") { const o = v as Record<string, unknown>; const t = o.texto ?? o.endereco; return typeof t === "string" ? t : formatarEndereco(o) || "—"; }
  return String(v);
};
const valor = (v: unknown) => (Array.isArray(v) ? (v.length ? v.map(textoItem).join(", ") : "(vazio)") : v == null || v === "" ? "(vazio)" : textoItem(v));
const chaveTitular = (tipo: string, id: string | null) => (id == null ? "" : `${tipo}:${id}`);

function Paperless({ id, base }: { id: number | null; base: string | null }) {
  if (id == null) return null;
  return base
    ? <a href={`${base.replace(/\/$/, "")}/documents/${id}/details`} target="_blank" rel="noreferrer">Paperless #{id}</a>
    : <span style={suave}>Paperless #{id}</span>;
}

/** Correção enviada na aprovação: campos do documento (listas `numeros` e `datas` inteiras) e `bem_nome` do bem novo. */
type Correcao = Partial<DocBase> & { bem_nome?: string };

function CartaoProposta({ p, opcoes, paperless, ocupado, erro, decidir }: {
  p: Proposta; opcoes: [string, string][]; paperless: string | null; ocupado: boolean; erro?: string;
  decidir: (estado: "aprovada" | "recusada", correcao?: Correcao) => void;
}) {
  const original = chaveTitular(p.doc.titular_tipo, p.doc.titular_id);
  const [editando, setEditando] = useState(false);
  const [numeros, setNumeros] = useState(p.doc.numeros);
  const [datas, setDatas] = useState(p.doc.datas);
  const [emissor, setEmissor] = useState(p.doc.emissor ?? "");
  const [titular, setTitular] = useState(original);
  const [bemNome, setBemNome] = useState(p.bem_novo?.nome ?? "");
  const [novoNumero, setNovoNumero] = useState({ nome: "", valor: "" });
  const [novaData, setNovaData] = useState({ tipo: "", data: "" });
  const desfazer = () => {
    setNumeros(p.doc.numeros); setDatas(p.doc.datas); setEmissor(p.doc.emissor ?? ""); setTitular(original); setBemNome(p.bem_novo?.nome ?? "");
    setNovoNumero({ nome: "", valor: "" }); setNovaData({ tipo: "", data: "" }); setEditando(false);
  };
  const livres = TIPOS_DATA.filter((t) => !datas.some((d) => d.tipo === t));
  const acrescentarNumero = () => {
    if (!novoNumero.nome.trim() || !novoNumero.valor.trim()) return;
    setNumeros([...numeros, { nome: novoNumero.nome.trim().toLowerCase(), valor: novoNumero.valor.trim() }]); setNovoNumero({ nome: "", valor: "" });
  };
  const acrescentarData = () => {
    if (!novaData.tipo || !novaData.data) return;
    setDatas(TIPOS_DATA.flatMap((t) => (t === novaData.tipo ? [novaData] : datas.filter((d) => d.tipo === t)))); setNovaData({ tipo: "", data: "" });
  };
  const correcao = (): Correcao => {
    const c: Correcao = {};
    if (JSON.stringify(numeros) !== JSON.stringify(p.doc.numeros)) c.numeros = numeros;
    if (JSON.stringify(datas) !== JSON.stringify(p.doc.datas)) c.datas = datas;
    if (emissor !== (p.doc.emissor ?? "")) c.emissor = emissor.trim() || null;
    if (titular !== original && titular) { const [tipo, ...id] = titular.split(":"); c.titular_tipo = tipo; c.titular_id = id.join(":"); }
    if (p.bem_novo && !titular && bemNome.trim() && bemNome.trim() !== p.bem_novo.nome) c.bem_nome = bemNome.trim();
    return c;
  };
  const aprovar = () => { const c = correcao(); decidir("aprovada", Object.keys(c).length ? c : undefined); };
  const nome = p.titular ? (p.titular.nome ?? p.titular.id) : p.bem_novo ? `bem novo: ${p.bem_novo.nome}` : "sem titular";
  return (
    <li style={linha}>
      <span style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span>
          <strong>{nome}</strong> · <strong>{p.doc.tipo.toUpperCase()}</strong> <span style={suave}>{p.doc.pais}{p.doc.emissor && ` · ${p.doc.emissor}`} · {p.origem}</span>
          {p.conferir && <span style={destaque}> conferir</span>}
          {p.paperless_id != null && <> · <Paperless id={p.paperless_id} base={paperless} /></>}
        </span>
        <span>{p.doc.numeros.map((n, i) => <span key={i}>{i > 0 && " · "}<span style={suave}>{n.nome} </span><span>{n.valor}</span></span>)}</span>
        {p.doc.datas.length > 0 && <span>{p.doc.datas.map((d, i) => <span key={d.tipo}>{i > 0 && " · "}<span style={suave}>{ROTULO_DATA[d.tipo] ?? d.tipo} </span><span>{dataBR(d.data)}</span></span>)}</span>}
        {p.atual && <span style={suave}>Substitui o documento atual ({p.atual.numeros[0]?.valor ?? "sem número"}{venceEm(p.atual) && `, vence ${dataBR(venceEm(p.atual))}`}).</span>}
        {p.motivos.length > 0 && <span style={suave}>Conferir: {p.motivos.join("; ")}</span>}
        {editando && (
          <span style={grupo}>
            <label>Titular<br /><select aria-label={`Titular da proposta ${p.id}`} value={titular} onChange={(e) => setTitular(e.target.value)}>
              {p.bem_novo ? <option value="">bem novo: {p.bem_novo.nome}</option> : <option value="">escolha…</option>}
              {opcoes.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
            </select></label>
            {p.bem_novo && !titular && (
              <label>Nome do bem<br /><input aria-label={`Nome do bem da proposta ${p.id}`} maxLength={120} value={bemNome} onChange={(e) => setBemNome(e.target.value)} /></label>)}
            {numeros.map((n, i) => (
              <span key={`n${i}`} style={grupo}>
                <label>{n.nome}<br /><input aria-label={`${n.nome} da proposta ${p.id}`} value={n.valor}
                  onChange={(e) => setNumeros(numeros.map((x, j) => (j === i ? { ...x, valor: e.target.value } : x)))} /></label>
                <button className="btn btn-secondary" aria-label={`Remover ${n.nome} da proposta ${p.id}`} onClick={() => setNumeros(numeros.filter((_, j) => j !== i))}>Remover</button>
              </span>))}
            {datas.map((d, i) => (
              <span key={d.tipo} style={grupo}>
                <label>{ROTULO_DATA[d.tipo] ?? d.tipo}<br /><input type="date" aria-label={`${d.tipo} da proposta ${p.id}`} value={d.data}
                  onChange={(e) => setDatas(datas.map((x, j) => (j === i ? { ...x, data: e.target.value } : x)))} /></label>
                <button className="btn btn-secondary" aria-label={`Remover ${d.tipo} da proposta ${p.id}`} onClick={() => setDatas(datas.filter((_, j) => j !== i))}>Remover</button>
              </span>))}
            <span style={grupo}>
              <label>Número novo<br /><input aria-label={`nome do número novo da proposta ${p.id}`} placeholder="nome" value={novoNumero.nome}
                onChange={(e) => setNovoNumero({ ...novoNumero, nome: e.target.value })} /></label>
              <label><br /><input aria-label={`valor do número novo da proposta ${p.id}`} placeholder="valor" value={novoNumero.valor}
                onChange={(e) => setNovoNumero({ ...novoNumero, valor: e.target.value })} /></label>
              <button className="btn btn-secondary" aria-label={`Acrescentar número na proposta ${p.id}`} onClick={acrescentarNumero}>Acrescentar número</button>
            </span>
            {livres.length > 0 && (
              <span style={grupo}>
                <label>Data nova<br /><select aria-label={`tipo da data nova da proposta ${p.id}`} value={novaData.tipo} onChange={(e) => setNovaData({ ...novaData, tipo: e.target.value })}>
                  <option value="">escolha…</option>
                  {livres.map((t) => <option key={t} value={t}>{ROTULO_DATA[t]}</option>)}
                </select></label>
                <label><br /><input type="date" aria-label={`data nova da proposta ${p.id}`} value={novaData.data} onChange={(e) => setNovaData({ ...novaData, data: e.target.value })} /></label>
                <button className="btn btn-secondary" aria-label={`Acrescentar data na proposta ${p.id}`} onClick={acrescentarData}>Acrescentar data</button>
              </span>)}
            <label>Emissor<br /><input aria-label={`emissor da proposta ${p.id}`} value={emissor} onChange={(e) => setEmissor(e.target.value)} /></label>
          </span>)}
      </span>
      <span style={grupo}>
        <button className="btn btn-primary" disabled={ocupado} aria-label={`Aprovar proposta ${p.id}`} onClick={aprovar}>Aprovar</button>
        <button className="btn btn-secondary" disabled={ocupado} aria-label={`Recusar proposta ${p.id}`} onClick={() => decidir("recusada")}>Recusar</button>
        {editando
          ? <button className="btn btn-secondary" disabled={ocupado} aria-label={`Desfazer correção da proposta ${p.id}`} onClick={desfazer}>Desfazer correção</button>
          : <button className="btn btn-secondary" disabled={ocupado} aria-label={`Corrigir proposta ${p.id}`} onClick={() => setEditando(true)}>Corrigir</button>}
      </span>
      <Aviso erro={erro} />
    </li>
  );
}

function ListaDocumentos({ docs, paperless }: { docs: Doc[]; paperless: string | null }) {
  const avisar = useToast();
  const copiar = async (v: string) => {
    try { await navigator.clipboard.writeText(v); avisar("Copiado."); } catch { avisar("Não consegui copiar."); }
  };
  if (docs.length === 0) return <Vazio frase="Nenhum documento cadastrado." />;
  return (
    <ul style={lista}>
      {docs.map((d) => {
        const vence = venceEm(d);
        return (
          <li key={d.id} style={linha}>
            <span style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span><strong>{d.tipo.toUpperCase()}</strong> <span style={suave}>{d.pais}</span>{d.emissor && <span style={suave}> · {d.emissor}</span>}</span>
              {d.numeros.map((n, i) => (
                <span key={i} style={grupo}>
                  <span style={suave}>{n.nome}</span> <span>{n.valor}</span>
                  <button className="btn btn-secondary" aria-label={`Copiar ${n.nome} de ${d.tipo.toUpperCase()}`} onClick={() => copiar(n.valor)}>Copiar</button>
                </span>))}
            </span>
            <span style={grupo}>
              {d.datas.map((x) => (
                <span key={x.tipo}><span style={suave}>{ROTULO_DATA[x.tipo] ?? x.tipo} </span>
                  <span style={x.data === vence && situacao(vence) ? (situacao(vence) === "vencido" ? destaque : atencao) : undefined}>{dataBR(x.data)}</span></span>))}
              <Situacao s={situacao(vence)} />
              <Paperless id={d.paperless_id} base={paperless} />
            </span>
          </li>);
      })}
    </ul>
  );
}

function BlocoPessoa({ p, paperless }: { p: Pessoa; paperless: string | null }) {
  const lst = (t: string, itens: unknown[]) => itens.length > 0 && <p style={{ margin: 0 }}><span style={suave}>{t}: </span>{itens.map((x, i) => <span key={i}>{i > 0 && " · "}<span>{textoItem(x)}</span></span>)}</p>;
  return (
    <Bloco titulo={p.nome_completo ?? p.nome} nota={[p.apelido, p.parentesco, p.nascimento && `nasc. ${dataBR(p.nascimento)}`].filter(Boolean).join(" · ")}>
      {lst("Telefones", p.telefones)}{lst("E-mails", p.emails)}{lst("Endereços", p.enderecos)}
      <ListaDocumentos docs={p.documentos} paperless={paperless} />
    </Bloco>
  );
}

function BlocoBem({ b, paperless }: { b: Bem; paperless: string | null }) {
  const dados = Object.entries(b.dados).filter(([, v]) => v != null && v !== "");
  return (
    <Bloco titulo={b.nome} nota={b.tipo === "imovel" ? "imóvel" : b.tipo === "veiculo" ? "veículo" : "outro bem"}>
      {dados.length > 0 && <p style={{ margin: 0 }}>{dados.map(([k, v], i) => <span key={k}>{i > 0 && " · "}<span style={suave}>{k}: </span><span>{textoItem(v)}</span></span>)}</p>}
      <ListaDocumentos docs={b.documentos} paperless={paperless} />
    </Bloco>
  );
}

export function CadastrosDocumentos() {
  const { ocupado, erros, agir } = useAcao();
  const [sel, setSel] = useState<string | null>(null);
  const propostas = useApi<{ itens: Proposta[]; paperless_url: string | null }>("/api/v1/documentos/propostas?estado=pendente");
  const titulares = useApi<Titulares>("/api/v1/documentos/titulares");
  const vencimentos = useApi<{ itens: Vencimento[] }>("/api/v1/documentos/vencimentos?meses=12");
  const historico = useApi<{ itens: Mudanca[] }>("/api/v1/familia/historico");
  const t = titulares.env?.dados;
  const nomes = new Map((t?.pessoas ?? []).map((p) => [p.id, p.nome]));
  const opcoes: [string, string][] = [...(t?.pessoas ?? []).map((p): [string, string] => [`pessoa:${p.id}`, p.nome]), ...(t?.bens ?? []).map((b): [string, string] => [`bem:${b.id}`, `bem: ${b.nome}`])];
  const recarregar = async () => { await Promise.all([propostas.recarregar(), titulares.recarregar(), vencimentos.recarregar(), historico.recarregar()]); };
  const agirEm = async (chave: string, fn: () => Promise<unknown>, ok: string) => { if (!(await agir(chave, fn, ok, recarregar))) await recarregar(); };
  const decidir = (p: Proposta) => (estado: "aprovada" | "recusada", correcao?: Correcao) =>
    agirEm(`proposta${p.id}`, () => api.post(`/api/v1/documentos/propostas/${p.id}/decisao`, correcao ? { estado, correcao } : { estado }),
      estado === "aprovada" ? "Proposta aprovada." : "Proposta recusada.");
  return (
    <>
      <Painel leitura={propostas} arquivo="documentos-propostas">
        {(d) => (
          <Bloco titulo={`Propostas de documento · ${d.itens.length}`} nota="Nada muda no cadastro até você aprovar. 'conferir' = leitura duvidosa.">
            {d.itens.length === 0 ? <Vazio frase="Nenhuma proposta pendente." /> : (
              <ul style={lista}>
                {d.itens.map((p) => <CartaoProposta key={p.id} p={p} opcoes={opcoes} paperless={d.paperless_url} ocupado={ocupado} erro={erros[`proposta${p.id}`]} decidir={decidir(p)} />)}
              </ul>)}
          </Bloco>)}
      </Painel>
      <Painel leitura={vencimentos} arquivo="documentos-vencimentos">
        {(d) => (
          <Bloco titulo={`Vencimentos · ${d.itens.length}`} nota="Próximos 12 meses e os vencidos há até 30 dias.">
            {d.itens.length === 0 ? <Vazio frase="Nenhum documento vence nos próximos 12 meses." /> : (
              <ul style={lista}>
                {d.itens.map((v) => (
                  <li key={v.documento_id} style={linha}>
                    <strong>{v.titular_nome} · {v.tipo.toUpperCase()}</strong>
                    <span style={grupo}><span style={suave}>{ROTULO_DATA[v.data_tipo] ?? v.data_tipo}</span> <span>{dataBR(v.data)}</span><Situacao s={situacao(v.data)} /></span>
                  </li>))}
              </ul>)}
          </Bloco>)}
      </Painel>
      <Painel leitura={titulares} arquivo="documentos-titulares">
        {(d) => {
          const todos = [...d.pessoas.map((p) => ({ chave: `pessoa:${p.id}`, rotulo: `${p.apelido ?? p.nome} · ${p.documentos.length}` })),
            ...d.bens.map((b) => ({ chave: `bem:${b.id}`, rotulo: `${b.nome} · ${b.documentos.length}` }))];
          const atual = sel ?? todos[0]?.chave ?? null;
          const pessoa = d.pessoas.find((p) => `pessoa:${p.id}` === atual);
          const bem = d.bens.find((b) => `bem:${b.id}` === atual);
          return (
            <>
              <Bloco titulo={`Pessoas e bens · ${todos.length}`} nota="Documentos só mudam por proposta aprovada aqui.">
                {todos.length === 0 ? <Vazio frase="Ninguém no cadastro ainda." /> : (
                  <div style={grupo}>
                    {todos.map((x) => (
                      <button key={x.chave} className={`btn ${x.chave === atual ? "btn-primary" : "btn-secondary"}`} aria-pressed={x.chave === atual} onClick={() => setSel(x.chave)}>{x.rotulo}</button>))}
                  </div>)}
              </Bloco>
              {pessoa && <BlocoPessoa p={pessoa} paperless={d.paperless_url} />}
              {bem && <BlocoBem b={bem} paperless={d.paperless_url} />}
            </>);
        }}
      </Painel>
      <Painel leitura={historico} arquivo="documentos-historico">
        {(d) => (
          <Bloco titulo="Histórico de contato" nota="Mudanças de contato (pelo Hermes ou pela carga; cada linha diz quem). Desfazer só vale se o valor ainda for o da mudança.">
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
                      : <button className="btn btn-secondary" disabled={ocupado} aria-label={`Desfazer mudança ${h.id}`} onClick={() => agirEm(`hist${h.id}`, () => api.post(`/api/v1/familia/historico/${h.id}/desfazer`, {}), "Mudança desfeita.")}>Desfazer</button>}
                    <Aviso erro={erros[`hist${h.id}`]} />
                  </li>))}
              </ul>)}
          </Bloco>)}
      </Painel>
    </>
  );
}
