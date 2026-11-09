/** Projetos: a pasta do projeto (ADR-038): orçamento contra gasto, fatos, anexos e pessoas; projeto e etapas moram no Linear (botão "Abrir no Linear"). Sem gráficos.
 * Consome: GET /api/v1/projetos?status=, POST /projetos, GET/PATCH /projetos/{id}, POST /projetos/{id}/pessoas|gastos|fatos|anexos, GET /api/v1/anexos/recentes e /anexos/{id}/arquivo. */
import { useState } from "react";
import { Bloco } from "../componentes/Bloco";
import { Vazio } from "../componentes/Estados";
import { Painel } from "../componentes/Painel";
import { api } from "../lib/api";
import { dataCurta, formatarBRL as brl } from "../lib/formato";
import { Aviso, useAcao } from "../lib/useAcao";
import { useApi } from "../lib/useApi";

type Agir = ReturnType<typeof useAcao>["agir"];
interface Progresso { feitas: number; total: number }  // só as atividades antigas do brain; não é mostrado
interface Projeto { id: number; nome: string; status: string; prazo: string | null; objetivo: string | null; linear_url: string | null }
interface Pessoa { id: number; nome: string; papel: string | null; contato: string | null }
interface Fato { id: number; texto: string; data: string | null; pessoa_nome: string | null; anexo_id: number | null }
interface AnexoItem { id: number; tipo: "imagem" | "audio" | "documento"; recebido_em: string; transcricao: string | null; paperless_id: number | null }
interface Detalhe {
  id: number; nome: string; objetivo: string | null; status: string; prazo: string | null; progresso: Progresso; linear_url: string | null; pessoas: Pessoa[];
  orcamento: string | null; gasto: string; saldo: string | null; fatos_recentes: Fato[]; anexos: number; anexos_itens: AnexoItem[];
}
const ROTA = "/api/v1/projetos";
const arquivo = (id: number) => `/api/v1/anexos/${id}/arquivo`;
const suave = { color: "var(--ink2)" } as const;
const chip = (ativo: boolean) => ({ height: 32, padding: "0 12px", border: "1px solid var(--line3)", background: ativo ? "var(--sel-bg, var(--raised))" : "transparent", color: "var(--color-text)", font: "600 12.5px var(--font-body)", cursor: "pointer" }) as const;
const campo = { display: "flex", flexDirection: "column", gap: 3, fontSize: 13 } as const;
const STATUS: Record<string, string> = { ativo: "Ativo", pausado: "Pausado", concluido: "Concluído", cancelado: "Cancelado" };

/** Lista de um status; clicar abre o detalhe. */
function Lista({ status, vazio, onAbrir }: { status: string; vazio: string; onAbrir: (id: number) => void }) {
  const leitura = useApi<{ itens: Projeto[] }>(`${ROTA}?status=${status}`);
  return (
    <Painel leitura={leitura} arquivo="projetos">
      {(dados) => dados.itens.length === 0 ? <Vazio frase={vazio} /> : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {dados.itens.map((p) => (
            <li key={p.id} style={{ borderTop: "1px solid var(--color-divider)" }}>
              <button onClick={() => onAbrir(p.id)} style={{ all: "unset", cursor: "pointer", display: "flex", gap: 12, justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", width: "100%", boxSizing: "border-box", padding: "10px 0" }}>
                <span>{p.nome}</span>
                <span style={{ display: "flex", gap: 12, fontSize: 12.5, ...suave }}>
                  {p.prazo && <span>prazo {dataCurta(p.prazo)}</span>}
                  {p.linear_url && <span>Linear</span>}
                </span>
              </button>
            </li>))}
        </ul>)}
    </Painel>
  );
}

function NovoProjeto({ agir, ocupado, erro, aoCriar }: { agir: Agir; ocupado: boolean; erro?: string; aoCriar: () => Promise<void> }) {
  const [aberto, setAberto] = useState(false);
  const [nome, setNome] = useState("");
  const [objetivo, setObjetivo] = useState("");
  if (!aberto) return <button className="btn btn-secondary" style={{ minHeight: 32, alignSelf: "flex-start" }} onClick={() => setAberto(true)}>Novo projeto</button>;
  const criar = async () => {
    if (!nome.trim()) return;
    const corpo = { nome: nome.trim(), ...(objetivo.trim() ? { objetivo: objetivo.trim() } : {}) };
    if (await agir("novo", () => api.post(ROTA, corpo), "Projeto criado.", aoCriar)) { setNome(""); setObjetivo(""); setAberto(false); }
  };
  return (
    <form onSubmit={(e) => { e.preventDefault(); void criar(); }} style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
      <label style={{ ...campo, flex: "1 1 220px" }}>Nome do projeto<input value={nome} maxLength={200} onChange={(e) => setNome(e.target.value)} /></label>
      <label style={{ ...campo, flex: "2 1 280px" }}>Objetivo<input value={objetivo} maxLength={2000} onChange={(e) => setObjetivo(e.target.value)} /></label>
      <button type="submit" className="btn btn-primary" disabled={ocupado || !nome.trim()}>Criar projeto</button>
      <button type="button" className="btn btn-secondary" onClick={() => setAberto(false)}>Fechar</button>
      <Aviso erro={erro} />
    </form>
  );
}

/** Anexos que chegaram (print, imagem, áudio) e ainda não estão num projeto: liga a um projeto ativo. Some quando não há nenhum. */
function CaixaDeEntrada({ onLigado }: { onLigado: () => void }) {
  const caixa = useApi<{ itens: { id: number; tipo: string; recebido_em: string; transcricao: string | null }[] }>("/api/v1/anexos/recentes");
  const ativos = useApi<{ itens: Projeto[] }>(`${ROTA}?status=ativo`);
  const { ocupado, erros, agir } = useAcao();
  const [escolha, setEscolha] = useState<Record<number, string>>({});
  const itens = caixa.env?.dados.itens ?? [];
  const projetos = ativos.env?.dados.itens ?? [];
  if (itens.length === 0) return null;
  return (
    <Bloco titulo="Caixa de entrada" nota="Prints, imagens e áudios que você mandou e ainda não estão em nenhum projeto.">
      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {itens.map((a) => (
          <li key={a.id} style={{ display: "flex", flexDirection: "column", gap: 6, borderTop: "1px solid var(--color-divider)", padding: "10px 0" }}>
            <span style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <span>{a.tipo === "audio" ? "Áudio" : "Imagem"} de {dataCurta(a.recebido_em)}</span>
              <a href={arquivo(a.id)} target="_blank" rel="noreferrer" aria-label={`Abrir anexo ${a.id}`}>abrir</a>
            </span>
            {a.transcricao && <span style={{ fontSize: 13.5 }}>{a.transcricao}</span>}
            <span style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13 }}>
                <span style={suave}>Ligar a…</span>
                <select aria-label={`Ligar anexo ${a.id} a`} value={escolha[a.id] ?? ""} onChange={(e) => setEscolha({ ...escolha, [a.id]: e.target.value })}>
                  <option value="">escolha o projeto</option>
                  {projetos.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
                </select>
              </label>
              <button className="btn btn-secondary" style={{ minHeight: 32 }} disabled={ocupado || !escolha[a.id]} aria-label={`Ligar anexo ${a.id}`}
                onClick={() => agir(String(a.id), () => api.post(`${ROTA}/${escolha[a.id]}/anexos`, { anexo_id: a.id }), "Anexo ligado ao projeto.", async () => { await caixa.recarregar(); onLigado(); })}>Ligar</button>
            </span>
            <Aviso erro={erros[String(a.id)]} />
          </li>))}
      </ul>
    </Bloco>
  );
}

type Form = "fato" | "gasto" | "pessoa" | null;

function Formularios({ id, agir, ocupado, erros, recarregar }: { id: number; agir: Agir; ocupado: boolean; erros: Record<string, string>; recarregar: () => Promise<void> }) {
  const [aberto, setAberto] = useState<Form>(null);
  const [v, setV] = useState({ fato: "", dataFato: "", valor: "", descricao: "", nome: "", papel: "" });
  const mudar = (k: keyof typeof v) => (e: { target: { value: string } }) => setV({ ...v, [k]: e.target.value });
  const enviar = async (chave: string, rota: string, corpo: unknown, ok: string, limpa: Partial<typeof v>) => {
    if (await agir(chave, () => api.post(`${ROTA}/${id}/${rota}`, corpo), ok, recarregar)) { setV({ ...v, ...limpa }); setAberto(null); }
  };
  const Fechar = <button type="button" className="btn btn-secondary" onClick={() => setAberto(null)}>Fechar</button>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button className="btn btn-secondary" style={{ minHeight: 32 }} onClick={() => setAberto("fato")}>Anotar fato</button>
        <button className="btn btn-secondary" style={{ minHeight: 32 }} onClick={() => setAberto("gasto")}>Registrar gasto</button>
        <button className="btn btn-secondary" style={{ minHeight: 32 }} onClick={() => setAberto("pessoa")}>Adicionar pessoa</button>
      </span>
      {aberto === "fato" && (
        <form onSubmit={(e) => { e.preventDefault(); if (v.fato.trim()) void enviar("fato", "fatos", { texto: v.fato.trim(), ...(v.dataFato ? { data: v.dataFato } : {}) }, "Fato anotado.", { fato: "", dataFato: "" }); }}
          style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <label style={{ ...campo, flex: "1 1 280px" }}>Fato<input value={v.fato} maxLength={1000} onChange={mudar("fato")} /></label>
          <label style={campo}>Data do fato<input type="date" value={v.dataFato} onChange={mudar("dataFato")} /></label>
          <button type="submit" className="btn btn-primary" disabled={ocupado || !v.fato.trim()}>Salvar fato</button>{Fechar}<Aviso erro={erros.fato} />
        </form>)}
      {aberto === "gasto" && (
        <form onSubmit={(e) => { e.preventDefault(); if (v.valor.trim()) void enviar("gasto", "gastos", { valor: v.valor.trim(), ...(v.descricao.trim() ? { descricao: v.descricao.trim() } : {}) }, "Gasto registrado.", { valor: "", descricao: "" }); }}
          style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <label style={campo}>Valor do gasto<input inputMode="decimal" value={v.valor} placeholder="300,00" onChange={mudar("valor")} /></label>
          <label style={{ ...campo, flex: "1 1 220px" }}>Descrição do gasto<input value={v.descricao} onChange={mudar("descricao")} /></label>
          <button type="submit" className="btn btn-primary" disabled={ocupado || !v.valor.trim()}>Salvar gasto</button>{Fechar}<Aviso erro={erros.gasto} />
        </form>)}
      {aberto === "pessoa" && (
        <form onSubmit={(e) => { e.preventDefault(); if (v.nome.trim()) void enviar("pessoa", "pessoas", { nome: v.nome.trim(), ...(v.papel.trim() ? { papel: v.papel.trim() } : {}) }, "Pessoa adicionada.", { nome: "", papel: "" }); }}
          style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <label style={{ ...campo, flex: "1 1 220px" }}>Nome da pessoa<input value={v.nome} onChange={mudar("nome")} /></label>
          <label style={campo}>Papel<input value={v.papel} placeholder="mecânico, advogada…" onChange={mudar("papel")} /></label>
          <button type="submit" className="btn btn-primary" disabled={ocupado || !v.nome.trim()}>Salvar pessoa</button>{Fechar}<Aviso erro={erros.pessoa} />
        </form>)}
    </div>
  );
}

function Detalhe_({ id, onVoltar }: { id: number; onVoltar: () => void }) {
  const leitura = useApi<Detalhe>(`${ROTA}/${id}`);
  const { ocupado, erros, agir } = useAcao();
  const [confirmar, setConfirmar] = useState<"concluido" | "cancelado" | null>(null);
  const [prazo, setPrazo] = useState<string | null>(null);
  const patch = (corpo: object, ok: string) => agir("status", () => api.patch(`${ROTA}/${id}`, corpo), ok, leitura.recarregar);
  return (
    <Painel leitura={leitura} arquivo="projeto">
      {(d) => {
        const encerrado = d.status === "concluido" || d.status === "cancelado";
        return (
          <>
            <button className="btn btn-secondary" style={{ minHeight: 32, alignSelf: "flex-start" }} onClick={onVoltar}>← Projetos</button>
            <Bloco titulo={d.nome} nota={STATUS[d.status] ?? d.status}>
              {d.objetivo && <p style={{ margin: 0 }}>{d.objetivo}</p>}
              {d.linear_url && <a className="btn btn-secondary" style={{ minHeight: 32, alignSelf: "flex-start" }} href={d.linear_url} target="_blank" rel="noopener noreferrer">Abrir no Linear</a>}
              <span style={{ fontSize: 13.5, ...suave }}>
                {d.orcamento === null ? `Sem orçamento · gasto ${brl(d.gasto)}` : `Orçamento ${brl(d.orcamento)} · gasto ${brl(d.gasto)} · saldo ${brl(d.saldo ?? "0")}`}
              </span>
              {encerrado ? <p style={{ margin: 0, ...suave }}>Projeto {d.status === "concluido" ? "concluído" : "cancelado"}: não reabre; para voltar, crie um projeto novo.</p> : (
                <>
                  <form onSubmit={(e) => { e.preventDefault(); if (prazo) void patch({ prazo }, "Prazo salvo.").then((ok) => ok && setPrazo(null)); }} style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
                    <label style={campo}>Prazo do projeto<input type="date" value={prazo ?? d.prazo ?? ""} onChange={(e) => setPrazo(e.target.value)} /></label>
                    <button type="submit" className="btn btn-secondary" style={{ minHeight: 32 }} disabled={ocupado || !prazo}>Salvar prazo</button>
                  </form>
                  <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {d.status === "ativo"
                      ? <button className="btn btn-secondary" style={{ minHeight: 32 }} disabled={ocupado} onClick={() => patch({ status: "pausado" }, "Projeto pausado.")}>Pausar projeto</button>
                      : <button className="btn btn-secondary" style={{ minHeight: 32 }} disabled={ocupado} onClick={() => patch({ status: "ativo" }, "Projeto retomado.")}>Retomar projeto</button>}
                    <button className="btn btn-secondary" style={{ minHeight: 32 }} disabled={ocupado} onClick={() => setConfirmar("concluido")}>Concluir projeto</button>
                    <button className="btn btn-secondary" style={{ minHeight: 32 }} disabled={ocupado} onClick={() => setConfirmar("cancelado")}>Cancelar projeto</button>
                  </span>
                  {confirmar && (
                    <div role="alert" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      <p style={{ margin: 0 }}>{confirmar === "concluido" ? "Concluir" : "Cancelar"} "{d.nome}"? Não há como reabrir; para voltar, crie um projeto novo.{d.progresso.total > 0 ? " As atividades abertas dele também são canceladas." : ""}</p>
                      <span style={{ display: "flex", gap: 8 }}>
                        <button className="btn btn-primary" disabled={ocupado} aria-label={`Confirmar ${confirmar === "concluido" ? "concluir" : "cancelar"}`}
                          onClick={() => patch({ status: confirmar }, confirmar === "concluido" ? "Projeto concluído." : "Projeto cancelado.").then((ok) => ok && setConfirmar(null))}>Confirmar</button>
                        <button className="btn btn-secondary" disabled={ocupado} onClick={() => setConfirmar(null)}>Voltar</button>
                      </span>
                    </div>)}
                </>)}
              <Aviso erro={erros.status} />
            </Bloco>
            <Bloco titulo="Pessoas">
              {d.pessoas.length === 0 ? <Vazio frase="Nenhuma pessoa ligada a este projeto." /> : (
                <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                  {d.pessoas.map((p) => (
                    <li key={p.id} style={{ display: "flex", gap: 10, justifyContent: "space-between", flexWrap: "wrap", padding: "6px 0", borderTop: "1px solid var(--color-divider)" }}>
                      <span>{p.nome}{p.papel ? ` — ${p.papel}` : ""}</span>
                      {p.contato && <span style={{ fontSize: 12.5, ...suave }}>{p.contato}</span>}
                    </li>))}
                </ul>)}
            </Bloco>
            <Bloco titulo="Fatos" nota="O diário do projeto: o que você contou e confirmou.">
              {d.fatos_recentes.length === 0 ? <Vazio frase="Nenhum fato anotado ainda." /> : (
                <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                  {d.fatos_recentes.map((f) => (
                    <li key={f.id} style={{ display: "flex", flexDirection: "column", gap: 2, padding: "6px 0", borderTop: "1px solid var(--color-divider)" }}>
                      <span>{f.texto}</span>
                      <span style={{ fontSize: 12.5, ...suave }}>
                        {f.data ? dataCurta(f.data) : ""}{f.pessoa_nome ? ` · ${f.pessoa_nome}` : ""}{f.anexo_id ? <> · <a href={arquivo(f.anexo_id)} target="_blank" rel="noreferrer">Ver anexo {f.anexo_id}</a></> : null}
                      </span>
                    </li>))}
                </ul>)}
            </Bloco>
            <Bloco titulo="Anexos">
              {d.anexos_itens.length === 0 ? <Vazio frase="Nenhum anexo ligado a este projeto." /> : (
                <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                  {d.anexos_itens.map((a) => (
                    <li key={a.id} style={{ display: "flex", flexDirection: "column", gap: 6, padding: "8px 0", borderTop: "1px solid var(--color-divider)" }}>
                      {a.tipo === "imagem" && <a href={arquivo(a.id)} target="_blank" rel="noreferrer" aria-label={`Abrir anexo ${a.id}`}><img src={arquivo(a.id)} alt={`Imagem de ${dataCurta(a.recebido_em)}`} style={{ maxWidth: 160, maxHeight: 160, objectFit: "cover" }} /></a>}
                      {a.tipo === "audio" && <audio controls src={arquivo(a.id)} />}
                      {a.tipo === "documento" && <span>Documento do Paperless #{a.paperless_id}</span>}
                      {a.transcricao && <span style={{ fontSize: 13.5 }}>{a.transcricao}</span>}
                      <span style={{ fontSize: 12.5, ...suave }}>{dataCurta(a.recebido_em)}</span>
                    </li>))}
                </ul>)}
            </Bloco>
            <Formularios id={id} agir={agir} ocupado={ocupado} erros={erros} recarregar={leitura.recarregar} />
          </>
        );
      }}
    </Painel>
  );
}

const ABAS = ["Ativos", "Pausados", "Encerrados"] as const;

/** Lista de projetos (Ativos, Pausados, Encerrados) com a caixa de entrada de anexos; clicar num projeto abre o detalhe. */
export function Projetos() {
  const [aberto, setAberto] = useState<number | null>(null);
  const [aba, setAba] = useState<(typeof ABAS)[number]>("Ativos");
  const [rev, setRev] = useState(0);
  const { ocupado, erros, agir } = useAcao();
  if (aberto !== null) return <div style={{ display: "flex", flexDirection: "column", gap: 16 }}><Detalhe_ id={aberto} onVoltar={() => setAberto(null)} /></div>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <CaixaDeEntrada key={rev} onLigado={() => setRev((n) => n + 1)} />
      <Bloco titulo="Projetos" nota="Conte um projeto ao Hermes (Telegram ou WhatsApp); ele cria o projeto e as etapas no Linear e guarda aqui a pasta (orçamento, fatos, anexos). Aqui você vê e corrige.">
        <NovoProjeto agir={agir} ocupado={ocupado} erro={erros.novo} aoCriar={async () => setRev((n) => n + 1)} />
        <div role="tablist" aria-label="Projetos" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {ABAS.map((a) => <button key={a} role="tab" aria-selected={aba === a} onClick={() => setAba(a)} style={chip(aba === a)}>{a}</button>)}
        </div>
        {aba === "Ativos" && <Lista key={rev} status="ativo" vazio="Nenhum projeto ativo. Conte um ao Hermes ou crie aqui." onAbrir={setAberto} />}
        {aba === "Pausados" && <Lista status="pausado" vazio="Nenhum projeto pausado." onAbrir={setAberto} />}
        {aba === "Encerrados" && (
          <>
            <Lista status="concluido" vazio="Nenhum projeto concluído." onAbrir={setAberto} />
            <Lista status="cancelado" vazio="Nenhum projeto cancelado." onAbrir={setAberto} />
          </>)}
      </Bloco>
    </div>
  );
}
