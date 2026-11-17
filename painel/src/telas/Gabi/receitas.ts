/** Receitas de conexão por cliente MCP (ADR-036). Função pura: sem chave recente, usa o marcador <SUA_CHAVE>.
 * Sintaxe conferida na documentação oficial de cada cliente em 2026-11-09 (fontes no runbook, seção Agentes externos). */
export interface Receita { id: string; titulo: string; texto: string; nota?: string }

export const MARCADOR_CHAVE = "<SUA_CHAVE>";
const TESTE = "Teste: peça ao agente \"chame a ferramenta ferramentas_ver\"; ele deve listar as ferramentas liberadas pelos escopos da chave.";
// Com chave real, nunca embute a chave numa linha colada no shell (iria para o histórico): pede num prompt silencioso.
const ENV = (chave: string | null) => chave ? "read -rs GABI_FINANCE_TOKEN; export GABI_FINANCE_TOKEN   # cole a chave no prompt (não aparece)" : `export GABI_FINANCE_TOKEN="${MARCADOR_CHAVE}"`;

export function receitas(url: string, chave: string | null): Receita[] {
  const k = chave ?? MARCADOR_CHAVE;
  const http = url.startsWith("http:");
  const permitir = http ? ',\n        "--allow-http"' : "";
  const lista: Receita[] = [
    {
      id: "claude-code", titulo: "Claude Code",
      texto: `${ENV(chave)}\nclaude mcp add --transport http gabi-finance ${url} --header "Authorization: Bearer $GABI_FINANCE_TOKEN"\n\n# ${TESTE}`,
      nota: "O comando grava o valor do cabeçalho na configuração do Claude Code (o shell expande a variável). Para não gravar a chave, use um .mcp.json com \"headers\": {\"Authorization\": \"Bearer ${GABI_FINANCE_TOKEN}\"} e \"type\": \"http\".",
    },
    {
      id: "cursor", titulo: "Cursor",
      texto: `${ENV(chave)}\n\n# ~/.cursor/mcp.json (ou .cursor/mcp.json no projeto)\n{\n  "mcpServers": {\n    "gabi-finance": {\n      "url": "${url}",\n      "headers": {\n        "Authorization": "Bearer \${env:GABI_FINANCE_TOKEN}"\n      }\n    }\n  }\n}\n\n# ${TESTE}`,
      nota: "Abra o Cursor a partir de um terminal com a variável definida.",
    },
    {
      id: "codex", titulo: "Codex CLI",
      texto: `${ENV(chave)}\n\n# ~/.codex/config.toml\n[mcp_servers.gabi-finance]\nurl = "${url}"\nbearer_token_env_var = "GABI_FINANCE_TOKEN"\n\n# ${TESTE}`,
    },
    {
      id: "claude-desktop", titulo: "Claude Desktop (via mcp-remote)",
      texto: `# claude_desktop_config.json\n{\n  "mcpServers": {\n    "gabi-finance": {\n      "command": "npx",\n      "args": [\n        "-y",\n        "mcp-remote",\n        "${url}",\n        "--header",\n        "Authorization:Bearer \${GABI_FINANCE_TOKEN}"${permitir}\n      ],\n      "env": { "GABI_FINANCE_TOKEN": "${k}" }\n    }\n  }\n}\n\n# ${TESTE}`,
      nota: "O Claude Desktop não lê variáveis do terminal, então aqui a chave fica no arquivo de configuração. Sem espaço depois de \"Authorization:\" de propósito (evita erro de parsing). Reinicie o Claude Desktop depois de editar.",
    },
    {
      id: "vscode", titulo: "VS Code (Copilot)",
      texto: `# .vscode/mcp.json\n{\n  "inputs": [\n    { "type": "promptString", "id": "gabi-token", "description": "Chave do agente na Gabi", "password": true }\n  ],\n  "servers": {\n    "gabi-finance": {\n      "type": "http",\n      "url": "${url}",\n      "headers": { "Authorization": "Bearer \${input:gabi-token}" }\n    }\n  }\n}\n\n# ${TESTE}`,
      nota: `O VS Code pergunta a chave na primeira vez e a guarda em local seguro; nada de chave no arquivo. Cole ${chave ? "a chave acima" : MARCADOR_CHAVE} quando ele pedir.`,
    },
    {
      id: "gemini", titulo: "Gemini CLI",
      texto: `${ENV(chave)}\ngemini mcp add --transport http --header "Authorization: Bearer $GABI_FINANCE_TOKEN" gabi-finance ${url}\n\n# ${TESTE}`,
      nota: "Sintaxe do comando conferida na documentação; ela não confirma expansão de variáveis dentro de \"headers\" no settings.json, então o comando grava o valor expandido na configuração do Gemini.",
    },
    {
      id: "nao-suportado", titulo: "Não suportado",
      texto: "OpenAI API e agentes em nuvem (rodam fora do seu computador) precisam de uma URL pública. A Tailscale não alcança esses serviços, e a Gabi não é exposta à internet. Sem receita por enquanto.",
    },
  ];
  const aviso = "Se a URL for http e o cliente recusar, use o mcp-remote como no Claude Desktop.";
  if (http) for (const r of lista) if (["claude-code", "cursor", "codex"].includes(r.id)) r.nota = r.nota ? `${r.nota} ${aviso}` : aviso;
  return lista;
}
