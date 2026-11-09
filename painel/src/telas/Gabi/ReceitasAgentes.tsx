/** Cartões de receita de conexão por cliente, com botão Copiar. A chave só entra se vier de `chave` (recém-emitida). */
import { useState } from "react";
import { Bloco } from "../../componentes/Bloco";
import { receitas } from "./receitas";

function Cartao({ id, titulo, texto, nota }: { id: string; titulo: string; texto: string; nota?: string }) {
  const [msg, setMsg] = useState<string | null>(null);
  const copiar = async () => {
    try { await navigator.clipboard.writeText(texto); setMsg("Copiada"); } catch { setMsg("Não consegui copiar; selecione o texto."); }
  };
  const copiavel = id !== "nao-suportado";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, borderTop: "1px solid var(--color-divider)", padding: "10px 0" }}>
      <strong>{titulo}</strong>
      {copiavel
        ? <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-all", userSelect: "all", fontSize: 12.5 }}>{texto}</pre>
        : <p style={{ margin: 0 }}>{texto}</p>}
      {nota && <span style={{ fontSize: 12.5, color: "var(--ink2)" }}>{nota}</span>}
      {copiavel && <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button className="btn btn-secondary" style={{ minHeight: 32 }} aria-label={`Copiar receita ${titulo}`} onClick={() => void copiar()}>Copiar</button>
        {msg && <span role="status" style={{ fontSize: 12.5 }}>{msg}</span>}
      </span>}
    </div>
  );
}

export function ReceitasAgentes({ url, chave }: { url: string; chave: string | null }) {
  return (
    <Bloco titulo="Como conectar" nota={chave ? "As receitas abaixo já trazem a chave recém-emitida; ao fechar o aviso ela some." : "Emita ou rotacione uma chave para as receitas virem preenchidas; por ora usam <SUA_CHAVE>."}>
      {receitas(url, chave).map((r) => <Cartao key={r.id} {...r} />)}
    </Bloco>
  );
}
