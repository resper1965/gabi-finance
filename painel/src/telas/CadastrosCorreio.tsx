import { useState } from "react";
import { Bloco } from "../componentes/Bloco";
import { Painel } from "../componentes/Painel";
import { Vazio } from "../componentes/Estados";
import { api } from "../lib/api";
import { Aviso, useAcao, type Acao } from "../lib/useAcao";
import { useApi, type Leitura } from "../lib/useApi";

interface Fonte { id: number; conta: string; provedor: "google" | "graph"; estado: "sim" | "nao" | "a_decidir"; lixeira: 0 | 1; sincronizada_em: string | null; ultimo_erro: string | null; mensagens: number; na_lixeira: number }
interface Parametros { criterios_emergencia: string; vips: string[]; lixeira_confianca: number; janela_dias: number; retencao_dias: number; retencao_msg_dias: number; dias_em_aberto: number; max_alertas_dia: number; palavras_protegidas: string[] }

const ESTADO = { sim: "Lendo", nao: "Desligada", a_decidir: "A decidir" } as const;
const suave = { color: "var(--ink2)" } as const;
const linha = { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", justifyContent: "space-between", borderTop: "1px solid var(--color-divider)", padding: "8px 0" } as const;
const lista = { listStyle: "none", margin: 0, padding: 0 } as const;
const inteiro = (v: string, min: number, max: number) => (/^\d+$/.test(v.trim()) && Number(v) >= min && Number(v) <= max ? Number(v) : null);
const decimal = (v: string) => Number(v.trim().replace(",", "."));
/** Horário de Brasília (o servidor guarda UTC); sem passar pelo fuso do navegador. */
export const quandoBRT = (iso: string | null) => (iso ? new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(iso)) : "nunca");

function Contas({ leitura, acao }: { leitura: Leitura<{ fontes: Fonte[] }>; acao: Acao }) {
  const { ocupado, erros, agir } = acao;
  const [conta, setConta] = useState("");
  const [confirmando, setConfirmando] = useState<number | null>(null);
  return (
    <Painel leitura={leitura} arquivo="correio-contas">
      {(d) => (
        <Bloco titulo={`Contas de e-mail · ${d.fontes.length}`} nota="Ler e mover para a lixeira são duas chaves separadas. A Gabi nunca envia, responde nem apaga de vez: a lixeira esvazia sozinha em 30 dias e dá para restaurar.">
          <Aviso erro={erros.geral} />
          {d.fontes.length === 0 ? <Vazio frase="Nenhuma conta cadastrada. Cadastre uma conta abaixo." /> : (
            <ul style={lista}>
              {d.fontes.map((f) => (
                <li key={f.id} style={linha}>
                  <span><strong>{f.conta}</strong> <span style={suave}>· {f.provedor === "google" ? "Google" : "Microsoft"} · {ESTADO[f.estado]} · lixeira {f.lixeira ? "ligada" : "desligada"} · {f.mensagens} mensagem(ns), {f.na_lixeira} na lixeira · última leitura {quandoBRT(f.sincronizada_em)}</span></span>
                  <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {f.estado !== "sim" && <button className="btn btn-primary" disabled={ocupado} aria-label={`Liberar leitura de ${f.conta}`} onClick={() => agir(`f${f.id}`, () => api.patch(`/api/v1/correio/fontes/${f.id}`, { estado: "sim" }), "Leitura liberada.", leitura.recarregar)}>Liberar leitura</button>}
                    {f.estado !== "nao" && <button className="btn btn-secondary" disabled={ocupado} aria-label={`Desligar ${f.conta}`} onClick={() => agir(`f${f.id}`, () => api.patch(`/api/v1/correio/fontes/${f.id}`, { estado: "nao" }), "Conta desligada.", leitura.recarregar)}>Desligar</button>}
                    {f.estado === "sim" && !f.lixeira && <button className="btn btn-secondary" disabled={ocupado} aria-label={`Ligar lixeira de ${f.conta}`} onClick={() => setConfirmando(f.id)}>Ligar lixeira</button>}
                    {f.estado === "sim" && f.lixeira === 1 && <button className="btn btn-secondary" disabled={ocupado} aria-label={`Desligar lixeira de ${f.conta}`} onClick={() => agir(`f${f.id}`, () => api.patch(`/api/v1/correio/fontes/${f.id}`, { lixeira: 0 }), "Lixeira desligada.", leitura.recarregar)}>Desligar lixeira</button>}
                  </span>
                  {confirmando === f.id && (
                    <div role="alert" style={{ display: "flex", flexDirection: "column", gap: 8, flexBasis: "100%" }}>
                      <p style={{ margin: 0 }}>Atenção: a Gabi vai mover para a lixeira de {f.conta} os e-mails de lista que ela julgar inúteis, com alta confiança. Quem você já respondeu e seus VIPs nunca vão. Você restaura em Mensagens › Prioridades.</p>
                      <span style={{ display: "flex", gap: 8 }}>
                        <button className="btn btn-primary" disabled={ocupado} aria-label={`Confirmar lixeira de ${f.conta}`} onClick={async () => { if (await agir(`f${f.id}`, () => api.patch(`/api/v1/correio/fontes/${f.id}`, { lixeira: 1 }), "Lixeira ligada.", leitura.recarregar)) setConfirmando(null); }}>Confirmar</button>
                        <button className="btn btn-secondary" disabled={ocupado} onClick={() => setConfirmando(null)}>Cancelar</button>
                      </span>
                    </div>)}
                  {f.ultimo_erro && <p style={{ margin: 0, flexBasis: "100%", ...suave }}>Último erro: {f.ultimo_erro}</p>}
                  <Aviso erro={erros[`f${f.id}`]} />
                </li>))}
            </ul>)}
          <form style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "end" }} onSubmit={async (e) => {
            e.preventDefault();
            if (ocupado || !conta.trim()) return;
            if (await agir("geral", () => api.post("/api/v1/correio/fontes", { conta: conta.trim(), provedor: "google" }), "Conta cadastrada.", leitura.recarregar)) setConta("");
          }}>
            <label>Conta (e-mail do Google)<br /><input aria-label="Conta de e-mail" value={conta} onChange={(e) => setConta(e.target.value)} /></label>
            <button className="btn btn-primary" type="submit" disabled={ocupado}>Cadastrar conta</button>
          </form>
        </Bloco>
      )}
    </Painel>
  );
}

function Ajustes({ leitura, acao }: { leitura: Leitura<Parametros>; acao: Acao }) {
  const { ocupado, erros, agir } = acao;
  const [criterios, setCriterios] = useState<string | null>(null);
  const [vips, setVips] = useState<string | null>(null);
  const [limiar, setLimiar] = useState<string | null>(null);
  const [janela, setJanela] = useState<string | null>(null);
  const [retencao, setRetencao] = useState<string | null>(null);
  const [retMsg, setRetMsg] = useState<string | null>(null);
  const [palavras, setPalavras] = useState<string | null>(null);
  const [emAberto, setEmAberto] = useState<string | null>(null);
  const [alertas, setAlertas] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <Painel leitura={leitura} arquivo="correio-parametros">
      {(p) => (
        <Bloco titulo="Ajustes do e-mail">
          <Aviso erro={erros.ajustes} />
          <form style={{ display: "flex", flexDirection: "column", gap: 12 }} onSubmit={async (e) => {
            e.preventDefault();
            if (ocupado) return;
            const corpo: Partial<Parametros> = {};
            if (criterios !== null) corpo.criterios_emergencia = criterios;
            if (vips !== null) corpo.vips = vips.split("\n").map((x) => x.trim()).filter(Boolean);
            if (limiar !== null) { const v = decimal(limiar); if (!(v >= 0.7 && v <= 1)) { setMsg("Confiança da lixeira: informe um número de 0,7 a 1."); return; } corpo.lixeira_confianca = v; }
            if (janela !== null) { const v = inteiro(janela, 1, 60); if (v === null) { setMsg("Janela: informe um inteiro de 1 a 60 dias."); return; } corpo.janela_dias = v; }
            if (retencao !== null) { const v = inteiro(retencao, 1, 365); if (v === null) { setMsg("Retenção do trecho: informe um inteiro de 1 a 365 dias."); return; } corpo.retencao_dias = v; }
            if (retMsg !== null) { const v = inteiro(retMsg, 90, 3650); if (v === null) { setMsg("Guardar as mensagens: informe um inteiro de 90 a 3650 dias."); return; } corpo.retencao_msg_dias = v; }
            if (palavras !== null) corpo.palavras_protegidas = palavras.split("\n").map((x) => x.trim()).filter(Boolean);
            if (emAberto !== null) { const v = inteiro(emAberto, 1, 30); if (v === null) { setMsg("Dias em aberto: informe um inteiro de 1 a 30."); return; } corpo.dias_em_aberto = v; }
            if (alertas !== null) { const v = inteiro(alertas, 1, 50); if (v === null) { setMsg("Alertas por dia: informe um inteiro de 1 a 50."); return; } corpo.max_alertas_dia = v; }
            setMsg(null);
            if (Object.keys(corpo).length === 0) return;
            if (await agir("ajustes", () => api.put("/api/v1/correio/parametros", corpo), "Ajustes salvos.", leitura.recarregar)) { setCriterios(null); setVips(null); setLimiar(null); setJanela(null); setRetencao(null); setRetMsg(null); setPalavras(null); setEmAberto(null); setAlertas(null); }
          }}>
            <label>O que é emergencial para você<br />
              <textarea aria-label="Critérios de emergência" rows={4} style={{ width: "100%" }} value={criterios ?? p.criterios_emergencia} onChange={(e) => { setCriterios(e.target.value); setMsg(null); }} /></label>
            <label>VIPs (um e-mail por linha; nunca vão para a lixeira)<br />
              <textarea aria-label="VIPs" rows={4} style={{ width: "100%" }} value={vips ?? p.vips.join("\n")} onChange={(e) => { setVips(e.target.value); setMsg(null); }} /></label>
            <label>Palavras que protegem da lixeira (uma por linha; fatura, boleto, cobrança... nunca vão)<br />
              <textarea aria-label="Palavras protegidas" rows={5} style={{ width: "100%" }} value={palavras ?? p.palavras_protegidas.join("\n")} onChange={(e) => { setPalavras(e.target.value); setMsg(null); }} /></label>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "end" }}>
              <label>Dias em aberto na fila<br /><input inputMode="numeric" value={emAberto ?? String(p.dias_em_aberto)} onChange={(e) => { setEmAberto(e.target.value); setMsg(null); }} /></label>
              <label>Alertas por dia (máximo)<br /><input inputMode="numeric" value={alertas ?? String(p.max_alertas_dia)} onChange={(e) => { setAlertas(e.target.value); setMsg(null); }} /></label>
            </div>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "end" }}>
              <label>Confiança mínima da lixeira (0,7 a 1)<br /><input inputMode="decimal" value={limiar ?? String(p.lixeira_confianca).replace(".", ",")} onChange={(e) => { setLimiar(e.target.value); setMsg(null); }} /></label>
              <label>Janela de leitura (dias)<br /><input inputMode="numeric" value={janela ?? String(p.janela_dias)} onChange={(e) => { setJanela(e.target.value); setMsg(null); }} /></label>
              <label>Guardar o trecho por (dias)<br /><input inputMode="numeric" value={retencao ?? String(p.retencao_dias)} onChange={(e) => { setRetencao(e.target.value); setMsg(null); }} /></label>
              <label>Guardar as mensagens no brain por (dias, de 90 a 3650)<br /><input inputMode="numeric" value={retMsg ?? String(p.retencao_msg_dias)} onChange={(e) => { setRetMsg(e.target.value); setMsg(null); }} /></label>
              <button className="btn btn-primary" type="submit" disabled={ocupado}>Salvar ajustes</button>
            </div>
            {msg && <p role="alert" style={{ margin: 0, color: "var(--danger)" }}>Erro: {msg}</p>}
          </form>
        </Bloco>
      )}
    </Painel>
  );
}

/** Cadastros › E-mail: quais contas a Gabi lê e onde pode mover para a lixeira (duas chaves), critérios, VIPs e limiar. Assunto e remetente nunca vão para o console. */
export function CadastrosCorreio() {
  const fontes = useApi<{ fontes: Fonte[] }>("/api/v1/correio/fontes");
  const parametros = useApi<Parametros>("/api/v1/correio/parametros");
  const acao = useAcao();
  if ([fontes, parametros].some((l) => l.estado === "erro" && l.erro?.status === 403)) return <Vazio frase="Só o dono configura o e-mail." />;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <Contas leitura={fontes} acao={acao} />
      <Ajustes leitura={parametros} acao={acao} />
    </div>
  );
}
