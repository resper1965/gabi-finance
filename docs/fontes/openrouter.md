# OpenRouter (modelo) e envio ao Paperless pela ponte

Só o serviço `gabi-brain-fontes` tem rede e a chave (R5). API, MCP e escuta chamam pela ponte Unix (`GABI_FONTES_SOCKET`):

- `PonteModelo(socket).completar(prompt, *, forte) -> (texto, custo_usd)`, mesmo contrato de `gabi.dinheiro.modelo.ModeloCliente`.
- `Ponte(socket, "paperless").enviar(conteudo, nome, tags)`: toda etiqueta tem de começar com `gabi:` (rejeitada antes de qualquer rede).

## Variáveis (arquivo `/etc/gabi/openrouter.env`, que o Ricardo coloca; `EnvironmentFile=-` opcional)
| Variável | Para quê | Padrão |
|---|---|---|
| `OPENROUTER_API_KEY` | chave do OpenRouter | sem ela, `completar` levanta `ErroOpenRouter("chave ausente")` (o chamador trata como "sem modelo") |
| `OPENROUTER_MODEL_FAST` | modelo rápido/barato | `deepseek/deepseek-v4-flash` |
| `OPENROUTER_MODEL_STRONG` | modelo forte (repetição de baixa confiança) | `anthropic/claude-sonnet-5.5` |

## Custo e segredos
- Chamada: `POST https://openrouter.ai/api/v1/chat/completions` com `usage: {include: true}`; o custo (USD) vem de `usage.cost`. Se ausente ou inválido, o custo é **0.0** (nunca é erro; o teto do orçamento então subconta, conferir no painel do OpenRouter).
- A chave nunca entra em log nem em erro: falhas viram só `OpenRouter -> <status>` ou o nome do tipo da exceção; o corpo de erro HTTP não é lido. Prompts e respostas não são logados.
