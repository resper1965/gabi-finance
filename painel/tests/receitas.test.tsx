import { render, screen } from "@testing-library/react";
import { receitas } from "../src/telas/Gabi/receitas";
import { ReceitasAgentes } from "../src/telas/Gabi/ReceitasAgentes";

const URL = "https://gabi.exemplo/mcp";
const por = (id: string, chave: string | null = null) => receitas(URL, chave).find((r) => r.id === id)!;

test("sem chave recente usa <SUA_CHAVE> e nunca um segredo", () => {
  const tudo = receitas(URL, null).map((r) => r.texto).join("\n");
  expect(tudo).toContain("<SUA_CHAVE>");
  expect(tudo).not.toMatch(/gb_/);
});
test("com chave recente preenche só a receita e a variável de ambiente", () => {
  const r = por("claude-code", "gb_abc");
  expect(r.texto).toContain("read -rs GABI_BRAIN_TOKEN; export GABI_BRAIN_TOKEN");
  expect(r.texto).not.toContain("<SUA_CHAVE>");
  expect(r.texto).not.toContain("gb_abc");
  expect(por("claude-desktop", "gb_abc").texto).toContain('"GABI_BRAIN_TOKEN": "gb_abc"');
  expect(receitas(URL, null).map((x) => x.texto).join("")).not.toContain("gb_abc");
});
test("Claude Code usa claude mcp add --transport http com header Authorization Bearer", () => {
  expect(por("claude-code").texto).toMatch(/claude mcp add --transport http gabi-brain https:\/\/gabi\.exemplo\/mcp --header "Authorization: Bearer \$GABI_BRAIN_TOKEN"/);
});
test("Cursor traz url e headers", () => {
  const t = por("cursor").texto;
  expect(t).toContain(`"url": "${URL}"`);
  expect(t).toContain('"headers"');
  expect(t).toContain("${env:GABI_BRAIN_TOKEN}");
});
test("Codex usa bearer_token_env_var", () => {
  expect(por("codex").texto).toContain('bearer_token_env_var = "GABI_BRAIN_TOKEN"');
});
test("toda receita inclui o teste ferramentas_ver", () => {
  for (const r of receitas(URL, null).filter((x) => x.id !== "nao-suportado")) expect(r.texto).toContain("ferramentas_ver");
});
test("aviso de não suportado cita OpenAI API e nuvem", () => {
  const t = por("nao-suportado").texto;
  expect(t).toMatch(/OpenAI API/);
  expect(t).toMatch(/nuvem/);
  expect(t).toMatch(/URL pública/);
});
test("a URL vem do /conexao", () => {
  expect(receitas("https://outra.ts.net/mcp", null).every((r) => r.id === "nao-suportado" || r.texto.includes("https://outra.ts.net/mcp"))).toBe(true);
  render(<ReceitasAgentes url="https://outra.ts.net/mcp" chave={null} />);
  expect(screen.getAllByText(/https:\/\/outra\.ts\.net\/mcp/).length).toBeGreaterThan(0);
});
test("URL http ganha --allow-http no mcp-remote", () => {
  expect(receitas("http://100.1.2.3:8000/mcp", null).find((r) => r.id === "claude-desktop")!.texto).toContain("--allow-http");
  expect(por("claude-desktop").texto).not.toContain("--allow-http");
});
test("todas as receitas usam o nome gabi-brain", () => {
  const tudo = receitas(URL, null).map((r) => r.texto).join("\n").split(URL).join("");
  expect(tudo).not.toMatch(/\bgabi\b(?!-)/);
  expect(por("codex").texto).toContain("[mcp_servers.gabi-brain]");
  expect(por("cursor").texto).toContain('"gabi-brain"');
  expect(por("gemini").texto).toContain(`gabi-brain ${URL}`);
});
test("URL http ganha nota de mcp-remote em Claude Code, Cursor e Codex; https não", () => {
  const h = receitas("http://100.1.2.3:8000/mcp", null);
  for (const id of ["claude-code", "cursor", "codex"]) expect(h.find((r) => r.id === id)!.nota).toMatch(/mcp-remote/);
  for (const id of ["claude-code", "cursor", "codex"]) expect(por(id).nota ?? "").not.toMatch(/mcp-remote/);
});
