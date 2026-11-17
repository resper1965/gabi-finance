import { useState } from "react";
import { Bloco } from "../componentes/Bloco";
import { api } from "../lib/api";
import { useToast } from "../lib/toast";
import { useApi } from "../lib/useApi";

interface Pendente { origem_pluggy: string; lancamentos: number }
interface Categoria { id: number; nome: string; pai_id: number | null }


/** Categorias que o banco usa e ainda não têm equivalência na nossa: as de mais lançamentos primeiro.
 *  Escolher aqui é aprovar (R1): a próxima rodada classifica os lançamentos com essa categoria, com origem "banco". */
export function CadastrosEquivalencias() {
  const pendentes = useApi<{ itens: Pendente[] }>("/api/v1/cadastros/categorias/equivalencias/pendentes");
  const categorias = useApi<{ itens: Categoria[] }>("/api/v1/cadastros/categorias");
  const avisar = useToast();
  const [escolha, setEscolha] = useState<Record<string, string>>({});
  const opcoes = (categorias.env?.dados.itens ?? []).filter((c) => c.pai_id !== null);  // grupos (sem pai) não recebem lançamentos
  const itens = pendentes.env?.dados.itens ?? [];

  const salvar = async (p: Pendente) => {
    const id = Number(escolha[p.origem_pluggy]);
    if (!id) return;
    try {
      await api.put("/api/v1/cadastros/categorias/equivalencias", { origem_pluggy: p.origem_pluggy, categoria_id: id });
      avisar(`Anotado: "${p.origem_pluggy}" agora vai para ${opcoes.find((c) => c.id === id)?.nome}.`);
      pendentes.recarregar();
    } catch (x) { avisar((x as Error).message); }
  };

  return (
    <Bloco titulo="Categorias do banco" nota="as que ainda não têm equivalência na nossa">
      <section role="region" aria-label="Categorias do banco sem equivalência">
        {itens.length === 0 && <p className="suave">Todas as categorias que o banco usa já têm equivalência.</p>}
        <ul className="pauta">
        {itens.map((p) => (
          <li key={p.origem_pluggy} className="cadastro-linha">
            <span className="pilha-curta" style={{ gap: 2 }}><span className="forte">{p.origem_pluggy}</span><span className="miudo">{p.lancamentos} lançamentos</span></span>
            <select aria-label={`Categoria para ${p.origem_pluggy}`} value={escolha[p.origem_pluggy] ?? ""} onChange={(x) => setEscolha({ ...escolha, [p.origem_pluggy]: x.target.value })}>
              <option value="">escolher…</option>
              {opcoes.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
            </select>
            <button className="btn btn-sm" aria-label={`Salvar ${p.origem_pluggy}`} disabled={!escolha[p.origem_pluggy]} onClick={() => salvar(p)}>Salvar</button>
          </li>
        ))}
        </ul>
      </section>
    </Bloco>
  );
}
