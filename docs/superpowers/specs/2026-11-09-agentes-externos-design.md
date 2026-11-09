# Agentes externos: painel de chaves e receitas de conexão (ADR-036)

Data: 09/11/2026 · Status: spec para revisão do Ricardo · Caminho: arquitetural

## Objetivo
Ricardo quer conectar ao gabi.brain os **seus próprios** agentes (Claude Code, Cursor, Codex CLI etc.) nas **suas máquinas**, sem usar o terminal da VPS para emitir chaves. Sucesso = emitir, ajustar e revogar uma chave pelo painel, copiar uma receita pronta para o cliente escolhido e ver que a chamada funcionou.

## Decisões do Ricardo (09/11)
- **Quem conecta:** só agentes dele, dentro da Tailscale. Nada novo exposto na internet. OpenAI API e outros agentes em nuvem (exigem URL pública) ficam **fora**, e a tela diz isso.
- **Permissões:** toda chave nova nasce com os **mesmos escopos do Hermes** (`ESCOPOS_HERMES`, sem `sensivel`); ele desmarca o que não quiser. Sem perfis prontos.

## O que já existe (reaproveitar, não duplicar)
- MCP em `/mcp` (Streamable HTTP, 71 ferramentas), auth Bearer, escopos por ferramenta (`ESCOPOS_FERRAMENTAS`).
- Tokens: `gabi/mcp/tokens.py` (`emitir`, `validar`, `revogar`, `definir_escopos`, `listar`); o banco guarda só o SHA-256; a tabela `token_agente`.
- Auditoria: `chamada_mcp` (token, ferramenta, escopo, status).
- Alcance: `https://gabi-brain.tail985643.ts.net:8443` → 127.0.0.1:8081, só tailnet (já configurado).
- Hoje a gestão de tokens é só por CLI (`python -m gabi.mcp.tokens`).

## Fora do escopo (YAGNI, ADR-023: um mês de uso antes de crescer)
Validade de chave, limite de chamadas, lista de ferramentas por chave, OAuth no MCP, URL pública, chaves para outras pessoas, perfis de permissão, ferramentas MCP novas (a contagem de 71 não muda).

## Design

### 1. Tela Gabi › Agentes (painel)
- Lista de chaves: nome, escopos, criada em, **último uso**, chamadas nos últimos 7 dias, estado (ativa/revogada; revogadas esmaecidas). O token do Hermes aparece como linha normal.
- **Nova chave:** pede o nome (obrigatório) e vem com os escopos de `ESCOPOS_HERMES` marcados; `sensivel` desmarcado. Ao emitir, a chave aparece **uma única vez** com botão copiar; fechar a janela a esconde para sempre.
- Por linha: **editar escopos** (não muda o segredo), **revogar** (confirmação), **rotacionar** (emite nova com os mesmos escopos e revoga a antiga, mostrando a nova uma vez).
- Revogar ou rotacionar o token do Hermes exige confirmação reforçada (derruba Telegram e WhatsApp até o `config.yaml` receber a nova).
- Ver chamadas recentes de uma chave (ferramenta, status, quando; nunca argumentos nem resultados).

### 2. API (`gabi/rotas/agentes.py`)
| Rota | Função |
|---|---|
| `GET /agentes` | lista chaves com último uso e contagem de 7 dias (de `chamada_mcp`); **nunca** devolve segredo nem hash |
| `POST /agentes` | `{nome, escopos}` → emite; a resposta traz a chave uma vez |
| `PATCH /agentes/{id}/escopos` | troca escopos de chave ativa |
| `POST /agentes/{id}/revogar` | revoga |
| `POST /agentes/{id}/rotacionar` | emite com os mesmos escopos, revoga a antiga |
| `GET /agentes/{id}/chamadas` | últimas 50 chamadas |
| `GET /agentes/conexao` | URL do MCP (parâmetro `mcp.url`, padrão `https://gabi-brain.tail985643.ts.net:8443/mcp`) e escopos padrão |

Tudo chama `gabi/mcp/tokens.py`; nenhuma regra de segurança é reescrita. Cada emitir, editar, revogar e rotacionar grava uma linha em `decisao` (sem o segredo). Validação de nome e escopos igual à do CLI (`ESCOPOS`). Migração: nenhuma esperada (usa `token_agente`, `chamada_mcp`, `parametro`); se faltar coluna para "último uso", é derivado de `max(quando)` em `chamada_mcp`, sem coluna nova.

### 3. Receitas
Cartões copiáveis na própria tela, com a URL real do MCP. A chave real só é preenchida logo após emitir; fora disso aparece `<SUA_CHAVE>`. Toda receita recomenda variável de ambiente em vez de gravar a chave em arquivo.
- **Claude Code:** `claude mcp add --transport http gabi-brain <url> --header "Authorization: Bearer $GABI_BRAIN_TOKEN"`.
- **Cursor:** `mcp.json` com `url` e `headers`.
- **Codex CLI:** `config.toml` com `url` e `bearer_token_env_var`.
- **Claude Desktop / VS Code / Gemini CLI:** config nativa quando existir, senão ponte `mcp-remote`.
- **Teste de 1 linha** em todas: pedir ao agente para chamar `ferramentas_ver`.
- **Não suportado:** OpenAI API e agentes em nuvem (precisam de URL pública).
- A sintaxe de cada cliente é **conferida na documentação atual** durante a implementação (muda com frequência); a data da conferência vai no runbook.

### 4. Segurança
- A tailnet continua sendo a porta; a chave continua obrigatória; o segredo nunca é gravado nem devolvido depois da emissão.
- Nada sai para fora sem o clique do Ricardo em Envios (R1, R2); nada de pagar, apagar, aprovar por MCP além do que o Hermes já faz hoje.
- Escrita por agente externo = a do Hermes; fica em `chamada_mcp` com o nome da chave.
- Chave vazada: revogar tem efeito imediato (`validar` já filtra `revogado_em`).
- Risco aceito pelo Ricardo: escopos de escrita por padrão em chaves externas.

### 5. Testes e documentação
- pytest: emitir mostra a chave uma vez; listar nunca a devolve; editar escopos e revogar; rotacionar; escopo inválido e nome vazio rejeitados; último uso e contagem; `decisao` gravada sem segredo; chave revogada deixa de autenticar no MCP.
- vitest: a lista, o diálogo de nova chave (padrão do Hermes, sem `sensivel`), exibição única, receitas sem chave real quando não recém-emitida.
- Docs: seção "Agentes externos" no runbook, `docs/api.md` e `openapi.json`, ADR-036, linha no BACKLOG.
- Antes de instalar: `cd painel && npm run build` e conferir `gabi/painel/`; instalar só com o ok do Ricardo.

## Numeração e ordem
Este trabalho é o **ADR-036**. A branch parada `feat/projetos-melhorias` (ADR-035 no plano) passa a **ADR-037** quando for retomada. Não cria ferramenta MCP, então a contagem de 71 não muda.

## Critério de aceite
Pelo painel: emitir uma chave "teste", colar a receita do Claude Code em outra máquina da tailnet, o agente chama `ferramentas_ver` e a chamada aparece em Agentes; revogar a chave e a chamada seguinte falha com `nao_autenticado`.
