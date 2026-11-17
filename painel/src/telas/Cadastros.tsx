import { Bloco } from "../componentes/Bloco";
import { Etiqueta } from "../componentes/Etiqueta";
import { Painel } from "../componentes/Painel";
import { api } from "../lib/api";
import { useToast } from "../lib/toast";
import { useApi } from "../lib/useApi";
import { CadastrosCobranca } from "./CadastrosCobranca";
import { CadastrosEquivalencias } from "./CadastrosEquivalencias";

interface Conta { id: number; apelido: string; instituicao: string; tipo: string; estado: string; limite: string | null; usuarios?: string[] }
interface Pessoa { id: string; nome: string; papel: string | null; dados: Record<string, unknown> }

const ESTADO: Record<string, string> = { sim: "entra no caixa único", nao: "fica de fora", a_decidir: "esperando você decidir" };

/** Fase 1: só as contas, para o Ricardo decidir quais entram no caixa único (G5). Demais cadastros chegam depois. */
export function Cadastros() {
  const leitura = useApi<{ itens: Conta[] }>("/api/v1/cadastros/contas");
  const pessoas = useApi<{ itens: Pessoa[] }>("/api/v1/cadastros/pessoas").env?.dados.itens ?? [];
  const avisar = useToast();
  const alternarUsuario = async (c: Conta, p: Pessoa) => {
    const atuais = c.usuarios ?? [];
    const novos = atuais.includes(p.id) ? atuais.filter((u) => u !== p.id) : [...atuais, p.id];
    try { await api.patch(`/api/v1/cadastros/contas/${c.id}`, { usuarios: novos }); avisar(novos.length ? `${c.apelido.trim()}: usado por ${novos.map((u) => pessoas.find((x) => x.id === u)?.nome ?? u).join(", ")}.` : `${c.apelido.trim()}: sem usuário definido.`); leitura.recarregar(); }
    catch (e) { avisar((e as Error).message); }
  };
  const decidir = async (c: Conta, estado: "sim" | "nao") => {
    try { await api.patch(`/api/v1/cadastros/contas/${c.id}`, { estado }); avisar(`Anotado: ${c.apelido} ${estado === "sim" ? "entra" : "não entra"} no caixa único.`); leitura.recarregar(); }
    catch (e) { avisar((e as Error).message); }
  };
  return (
    <Painel leitura={leitura} arquivo="contas conectadas">
      {(d) => (
        <div className="pilha" style={{ gap: 40, maxWidth: 1100 }}>
        <Bloco titulo="Contas" nota="conta nova só entra no caixa único depois que você decidir; marque quem usa cada cartão">
          <ul className="pauta">
            {d.itens.map((c) => (
              <li key={c.id} className="conta">
                <span className="pilha-curta" style={{ gap: 2 }}><span className="linha-titulo">{c.apelido}</span><span className="miudo">{c.instituicao} · {c.tipo}</span></span>
                <span><Etiqueta tipo={c.estado === "a_decidir" ? "conferir" : c.estado === "sim" ? "ok" : "parado"} texto={ESTADO[c.estado] ?? c.estado} /></span>
                <span role="group" aria-label={`Decisão sobre ${c.apelido.trim()}`} className="seg">
                  <button className="seg-opt" aria-pressed={c.estado === "sim"} disabled={c.estado === "sim"} onClick={() => decidir(c, "sim")}>Entra no caixa único</button>
                  <button className="seg-opt" aria-pressed={c.estado === "nao"} disabled={c.estado === "nao"} onClick={() => decidir(c, "nao")}>Não entra</button>
                </span>
                <div role="group" aria-label={`Quem usa ${c.apelido.trim()}`} className="fila conta-usuarios">
                  <span className="lanc-rotulo">Quem usa</span>
                  {pessoas.filter((p) => p.dados?.beneficiario !== false).map((p) => (
                    <button key={p.id} className="chip" aria-pressed={(c.usuarios ?? []).includes(p.id)} onClick={() => alternarUsuario(c, p)}>{p.nome.split(" ")[0]}</button>
                  ))}
                  {(c.usuarios ?? []).length === 0 && <span className="miudo">não definido (cada gasto vai para a fila)</span>}
                </div>
              </li>
            ))}
          </ul>
        </Bloco>
        <CadastrosEquivalencias />
        <CadastrosCobranca />
        </div>
      )}
    </Painel>
  );
}
