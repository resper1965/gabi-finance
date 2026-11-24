import { useState } from "react";
import { BellRing, OctagonAlert } from "lucide-react";
import { Achados } from "../../componentes/Achados";
import { Etiqueta } from "../../componentes/Etiqueta";
import { Vazio } from "../../componentes/Estados";
import { Painel } from "../../componentes/Painel";
import { useCelular } from "../../componentes/Shell";
import { Valor } from "../../componentes/Valor";
import { api } from "../../lib/api";
import { dataCurta, mesCurto, num } from "../../lib/formato";
import { useToast } from "../../lib/toast";
import { FONTE } from "../../lib/proveniencia";
import { useApi } from "../../lib/useApi";

interface Ass {
  id: number; nome: string; mensal: string; anual: string; meses_vistos: number; status: string; no_rol?: boolean; lembrar_ate_cancelar: boolean; ativa?: boolean;
  reembolso?: { id: string; nome: string } | null;
  serie_12m: { mes: string; total: string }[]; desde: string | null; ultimo: string | null; total_12m: string;
  sinais: { nova: boolean; reajustou: { antes: string; agora: string } | null; cobrada_depois_de_cancelar: boolean };
}
const STATUS: [string, string][] = [["a_conferir", "a conferir"], ["manter", "manter"], ["cancelar", "cancelar"], ["nao_assinatura", "não é assinatura"], ["encerrada", "encerrada"]];

function Barras({ serie, largura }: { serie: Ass["serie_12m"]; largura: number }) {
  const topo = Math.max(1, ...serie.map((m) => num(m.total)));
  return (
    <span style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 24 }}>
      {serie.map((m) => <span key={m.mes} title={`${mesCurto(m.mes)}: ${m.total}`} style={{ width: largura, height: Math.max(1, (num(m.total) / topo) * 22), background: num(m.total) ? "var(--tinta-2)" : "var(--regra)" }} />)}
    </span>
  );
}

export function Assinaturas() {
  const celular = useCelular();
  const leitura = useApi<{ itens: Ass[]; total_mensal: string; alerta_forte: boolean }>("/api/v1/assinaturas");
  const empresas = useApi<{ itens: { id: string; nome: string }[] }>("/api/v1/cadastros/empresas").env?.dados.itens ?? [];
  const avisar = useToast();
  const [filtro, setFiltro] = useState("rol");
  const [marcadas, setMarcadas] = useState<number[]>([]);
  const [novo, setNovo] = useState("");
  const mudar = async (ids: number[], corpo: Record<string, unknown>, texto: string) => {
    try { for (const id of ids) await api.patch(`/api/v1/assinaturas/${id}`, corpo); avisar(texto); setMarcadas([]); setNovo(""); leitura.recarregar(); }
    catch (e) { avisar((e as Error).message); }
  };
  return (
    <Painel leitura={leitura} arquivo="assinaturas detectadas">
      {(d) => {
        // "não é assinatura" e "encerrada" saem do rol: somem da lista padrão, dos totais e dos alertas (ficam no filtro do próprio status, para desfazer)
        const rol = d.itens.filter((a) => a.no_rol !== false);
        const linhas = filtro === "rol" ? rol : d.itens.filter((a) => a.status === filtro);
        const total12 = rol.reduce((s, a) => s + num(a.total_12m), 0);
        const aConferir = d.itens.filter((a) => a.status === "a_conferir").length;
        const flags = (a: Ass) => (
          <div className="fila" style={{ gap: 4, marginTop: 4 }}>
            {a.ativa === false && <Etiqueta tipo="conferir" texto="parou de cobrar" />}
            {a.sinais.nova && <Etiqueta tipo="atencao" texto="nova" />}
            {a.sinais.reajustou && <Etiqueta tipo="atencao" texto={`reajustou ${a.sinais.reajustou.antes} → ${a.sinais.reajustou.agora}`} />}
            {a.sinais.cobrada_depois_de_cancelar && <Etiqueta tipo="erro" texto="cobrada depois de cancelar" />}
          </div>
        );
        const status = (a: Ass, alto: number) => (
          <select aria-label={`Status de ${a.nome}`} value={a.status} data-status={a.status} className="status-assinatura" onChange={(e) => mudar([a.id], { status: e.target.value }, `Anotado: ${a.nome} marcada por você.`)}
            style={{ minHeight: alto }}>
            {STATUS.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
          </select>
        );
        const reembolso = (a: Ass, alto: number) => (
          <select aria-label={`Reembolso de ${a.nome}`} value={a.reembolso?.id ?? ""} className="campo-sm" style={{ minHeight: alto }}
            onChange={(e) => mudar([a.id], { empresa_id: e.target.value || null },
              e.target.value ? `Anotado: as cobranças de ${a.nome} entram como reembolso da ${empresas.find((x) => String(x.id) === e.target.value)?.nome ?? e.target.value}.` : `Anotado: ${a.nome} volta a ser pessoal.`)}>
            <option value="">pessoal</option>
            {empresas.map((x) => <option key={x.id} value={String(x.id)}>reembolso: {x.nome}</option>)}
          </select>
        );
        const lembrar = (a: Ass) => a.status === "cancelar" && (
          <button className={celular ? "btn" : "btn btn-ghost btn-sm"} style={celular ? { minHeight: 44 } : undefined} onClick={() => mudar([a.id], { lembrar_ate_cancelar: !a.lembrar_ate_cancelar }, a.lembrar_ate_cancelar ? "Anotado: parei de lembrar." : "Anotado: eu lembro você até cancelar.")}>
            {a.lembrar_ate_cancelar ? <><BellRing size={14} strokeWidth={1.8} aria-hidden="true" />Gabi lembra até cancelar</> : "Pedir à Gabi para lembrar até cancelar"}
          </button>
        );
        return (
          <div className="pilha" style={{ gap: 32, maxWidth: 1120 }}>
            <Achados itens={[
              { codigo: "AS-01", rotulo: "Recorrente por mês", fontes: [FONTE.extrato()], base: "valor atual de cada assinatura no rol", valor: <Valor valor={d.total_mensal} />,
                prova: <span>{rol.filter((a) => a.ativa !== false).length} assinaturas ativas</span> },
              { codigo: "AS-02", rotulo: "Em 12 meses", fontes: [FONTE.extrato()], base: "débitos das assinaturas do rol nos últimos 12 meses", valor: <Valor valor={total12} />, prova: "débitos dos últimos 12 meses" },
              { codigo: "AS-03", rotulo: "A conferir", fontes: [FONTE.extrato()], estado: aConferir ? "a_conferir" : undefined, base: "recorrências detectadas que você ainda não marcou",
                valor: <span className="num">{aConferir}</span>, prova: `${rol.filter((a) => a.sinais.nova).length} novas` },
            ]} />
            {rol.filter((a) => a.sinais.cobrada_depois_de_cancelar).map((a) => (
              <div key={a.id} role="alert" className="quadro" data-tom="erro">
                <OctagonAlert size={20} strokeWidth={1.7} aria-hidden="true" />
                <div className="pilha-curta cresce" style={{ gap: 4 }}>
                  <span className="fila"><Etiqueta tipo="erro" texto="divergente" /><strong>Cobrada depois de marcada para cancelar</strong></span>
                  <span>{a.nome} debitou <Valor valor={a.mensal} />{a.ultimo ? ` em ${dataCurta(a.ultimo)}` : ""}. Você marcou "cancelar", então o cancelamento não chegou ao fornecedor.</span>
                </div>
                {lembrar(a)}
              </div>
            ))}
            <section className="secao" aria-label="Assinaturas">
            <div className="secao-cab"><h2>Assinaturas</h2><span className="secao-nota">o status é seu; a Gabi só detecta a recorrência</span></div>
            <div className="rolagem-x">
              <div role="group" aria-label="Filtrar por status" className="seg">
                {([["rol", "No rol"], ...STATUS] as const).map(([v, r]) => (
                  <button key={v} className="seg-opt" aria-pressed={filtro === v} onClick={() => setFiltro(v)}>{r}</button>
                ))}
              </div>
            </div>
            <div role="group" aria-label="Edição em lote" className="lote" data-ativo={marcadas.length > 0}>
              {marcadas.length === 0 && <span className="miudo">Marque várias assinaturas para mudar o status de uma vez.</span>}
              {marcadas.length > 0 && <>
                <strong className="num">{marcadas.length} selecionadas</strong>
                <select aria-label="Novo status" value={novo} onChange={(e) => setNovo(e.target.value)} className="campo-sm"><option value="">Novo status…</option>{STATUS.map(([v, r]) => <option key={v} value={v}>{r}</option>)}</select>
                <span className="cresce" />
                <button className="btn btn-ghost btn-sm" onClick={() => setMarcadas([])}>Limpar</button>
                <button className="btn btn-primary btn-sm" disabled={!novo} onClick={() => mudar(marcadas, { status: novo }, `${marcadas.length} assinaturas marcadas por você.`)}>Aplicar</button>
              </>}
            </div>
            {!celular ? (
              <div className="tabela-rolagem">
              <table className="tabela">
                <thead><tr><th style={{ width: 32 }}><span className="sr-only">Selecionar</span></th><th>Assinatura</th><th className="num">Valor atual</th><th>Desde · último</th><th>Débitos (12 meses)</th><th className="num">12 meses</th><th>Status</th><th>Reembolso por</th></tr></thead>
                <tbody>{linhas.map((a) => (
                  <tr key={a.id} data-assinatura={a.id} data-marcado={marcadas.includes(a.id)}>
                    <td><input type="checkbox" aria-label={`Selecionar ${a.nome}`} checked={marcadas.includes(a.id)} onChange={(e) => setMarcadas(e.target.checked ? [...marcadas, a.id] : marcadas.filter((x) => x !== a.id))} /></td>
                    <td style={{ maxWidth: 320 }}><div className="forte">{a.nome}</div>{flags(a)}</td>
                    <td className="num forte"><Valor valor={a.mensal} /></td>
                    <td className="mono suave" style={{ whiteSpace: "nowrap" }}>{a.desde ? dataCurta(a.desde) : "—"}<br />{a.ultimo ? dataCurta(a.ultimo) : "—"}</td>
                    <td><Barras serie={a.serie_12m} largura={7} /></td>
                    <td className="num"><Valor valor={a.total_12m} /></td>
                    <td><div className="pilha-curta" style={{ gap: 4, alignItems: "flex-start" }}>{status(a, 30)}{lembrar(a)}</div></td>
                    <td>{reembolso(a, 30)}</td>
                  </tr>))}</tbody>
              </table>
              </div>
            ) : (
              <ul className="pauta">{linhas.map((a) => (
                <li key={a.id} data-assinatura={a.id} data-marcado={marcadas.includes(a.id)} className="pilha-curta">
                  <div className="fila-entre" style={{ flexWrap: "nowrap" }}>
                    <label className="opcao forte">
                      <input type="checkbox" checked={marcadas.includes(a.id)} onChange={(e) => setMarcadas(e.target.checked ? [...marcadas, a.id] : marcadas.filter((x) => x !== a.id))} style={{ width: 20, height: 20 }} />{a.nome}
                    </label>
                    <span className="linha-valor"><Valor valor={a.mensal} /></span>
                  </div>
                  {flags(a)}
                  <div className="fila-entre" style={{ alignItems: "flex-end" }}><Barras serie={a.serie_12m} largura={8} /><span className="miudo">12 meses <strong style={{ color: "var(--tinta)" }}><Valor valor={a.total_12m} /></strong></span></div>
                  {status(a, 44)}{reembolso(a, 44)}{lembrar(a)}
                </li>))}
              </ul>
            )}
            {linhas.length === 0 && <Vazio frase={filtro === "rol" ? "Nenhuma assinatura no rol. A Gabi lista aqui o que debita todo mês." : "Nenhuma assinatura com esse status."} />}
            <p className="miudo">Barras: o total debitado em cada um dos últimos 12 meses. "Reembolso por": as cobranças dos últimos 12 meses e as novas entram nas despesas daquela empresa (o que você marcou à mão num lançamento não muda).</p>
            </section>
          </div>
        );
      }}
    </Painel>
  );
}
