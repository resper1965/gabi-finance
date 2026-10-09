import { Etiqueta } from "../../componentes/Etiqueta";
import { Painel } from "../../componentes/Painel";
import { dataCurta } from "../../lib/formato";
import { useApi } from "../../lib/useApi";

interface Item { id: number; remetente: string; assunto: string | null; recebido_em: string; relevante: number; motivo: string | null; estado: string; caixa: string }

/** Mensagens › E-mails: só cabeçalho e trecho; o corpo fica na caixa de origem. Expurgo só sugerido, nunca apagado aqui. */
export function Mensagens() {
  const leitura = useApi<{ itens: Item[]; expurgo_sugerido: number[] }>("/api/v1/mensagens");
  return (
    <Painel leitura={leitura} arquivo="mensagens">
      {(d) => (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {d.expurgo_sugerido.length > 0 && <p data-expurgo>{d.expurgo_sugerido.length} e-mails casam com uma regra de expurgo ligada por você. Nada foi apagado.</p>}
          {d.itens.length === 0 && <p style={{ color: "var(--ink2)" }}>Nenhum e-mail ainda. Libere uma caixa em Cadastros › Caixas de e-mail.</p>}
          {d.itens.map((m) => (
            <div key={m.id} data-mensagem style={{ border: "1px solid var(--color-divider)", padding: "8px 12px" }}>
              <strong>{m.assunto}</strong> {m.relevante ? <Etiqueta tipo="atencao" texto="importa" /> : null}
              <div style={{ fontSize: 13, color: "var(--ink2)" }}>{m.remetente} · {m.caixa} · {dataCurta(m.recebido_em.slice(0, 10))}{m.motivo ? ` · ${m.motivo}` : ""}</div>
            </div>))}
        </div>
      )}
    </Painel>
  );
}
