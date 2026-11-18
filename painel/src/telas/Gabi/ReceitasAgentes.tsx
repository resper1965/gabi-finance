/** Cartões de receita de conexão por cliente, com botão Copiar. A chave só entra se vier de `chave` (recém-emitida). */
import { useState } from "react";
import { Copy } from "lucide-react";
import { Bloco } from "../../componentes/Bloco";
import { receitas } from "./receitas";

function Cartao({ id, titulo, texto, nota }: { id: string; titulo: string; texto: string; nota?: string }) {
  const [msg, setMsg] = useState<string | null>(null);
  const copiar = async () => {
    try { await navigator.clipboard.writeText(texto); setMsg("Copiada"); } catch { setMsg("Não consegui copiar; selecione o texto."); }
  };
  const copiavel = id !== "nao-suportado";
  return (
    <details className="receita" open={id === "claude-code" || undefined}>
      <summary><strong>{titulo}</strong></summary>
      <div className="pilha-curta" style={{ gap: 8, paddingTop: 8 }}>
        {copiavel
          ? <pre className="codigo">{texto}</pre>
          : <p>{texto}</p>}
        {nota && <span className="miudo" style={{ maxWidth: "80ch" }}>{nota}</span>}
        {copiavel && <span className="fila">
          <button className="btn btn-sm" aria-label={`Copiar receita ${titulo}`} onClick={() => void copiar()}><Copy size={14} strokeWidth={1.8} aria-hidden="true" />Copiar</button>
          {msg && <span role="status" className="miudo">{msg}</span>}
        </span>}
      </div>
    </details>
  );
}

export function ReceitasAgentes({ url, chave }: { url: string; chave: string | null }) {
  return (
    <Bloco titulo="Como conectar" nota={chave ? "As receitas abaixo já trazem a chave recém-emitida; ao fechar o aviso ela some." : "Emita ou rotacione uma chave para as receitas virem preenchidas; por ora usam <SUA_CHAVE>."}>
      <div className="pauta">{receitas(url, chave).map((r) => <Cartao key={r.id} {...r} />)}</div>
    </Bloco>
  );
}
