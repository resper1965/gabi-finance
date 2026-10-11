# OpenRouter (modelo) e envio ao Paperless pela ponte

Só o serviço `gabi-brain-fontes` tem rede e a chave (R5). API, MCP e escuta chamam pela ponte Unix (`GABI_FONTES_SOCKET`):

- `PonteModelo(socket).completar(prompt, *, forte) -> (texto, custo_usd)`, mesmo contrato de `gabi.dinheiro.modelo.ModeloCliente`.
- `Ponte(socket, "paperless").enviar(conteudo, nome, tags)`: toda etiqueta tem de começar com `gabi:` (rejeitada antes de qualquer rede).

## Variáveis (arquivo `/etc/gabi/openrouter.env`, que o Ricardo coloca; `EnvironmentFile=-` opcional)
| Variável | Para quê | Padrão |
|---|---|---|
| `OPENROUTER_API_KEY` | chave do OpenRouter | sem ela a fonte `openrouter` fica "não configurada" (`configurada()` = falso) e `completar` levanta `ErroOpenRouter` tipado (o chamador trata como "sem modelo") |
| `OPENROUTER_MODEL_FAST` | modelo rápido/barato | `deepseek/deepseek-v4-flash` |
| `OPENROUTER_MODEL_STRONG` | modelo forte (repetição de baixa confiança) | `anthropic/claude-sonnet-5.5` |

## Tetos (no serviço de fontes; falham seguro)
| Variável | Padrão | Efeito |
|---|---|---|
| `OPENROUTER_MAX_TOKENS_FAST` / `_STRONG` | 1024 / 2048 | `max_tokens` enviado em cada chamada |
| `OPENROUTER_MAX_PROMPT_CHARS` | 50000 | maior prompt aceito; acima, `ErroOpenRouter("prompt grande demais")` antes de qualquer rede |
| `OPENROUTER_TETO_DIA_USD` | 3.0 | gasto diário (dia em America/Sao_Paulo); se gasto + reserva da chamada passar do teto, `ErroOpenRouter("teto diário")`. 0 bloqueia tudo |
| `OPENROUTER_MAX_CHAMADAS_MIN` | 30 | chamadas por minuto (relógio monotônico); acima, `ErroOpenRouter("muitas chamadas")`. 0 bloqueia tudo |

O contador do teto diário fica na memória: **reiniciar o serviço o zera**. Por isso, defina também um **limite de crédito na própria chave** no painel do OpenRouter (o teto real).

Reserva: antes de cada chamada o serviço reserva, sob trava, o pior caso (`max_tokens` x preço de saída + prompt a len/3 tokens x preço de entrada, no mínimo `OPENROUTER_CUSTO_PADRAO_USD`) e recusa se gasto + reserva passar do teto (vale para chamadas paralelas). Sucesso troca a reserva pelo custo real; falha depois do envio (erro HTTP, 200 sem texto, timeout) mantém a reserva cobrada, porque pode ter sido faturada; recusa antes da rede não cobra. Sem `completion_tokens` mas com `prompt_tokens`, a saída é estimada em `max_tokens`. Valores não numéricos, NaN/inf ou negativos caem no padrão (0 só vale nos dois tetos acima).

## Custo e segredos
- Chamada: `POST https://openrouter.ai/api/v1/chat/completions` com `usage: {include: true}`; o custo (USD) vem de `usage.cost`.
- Se `usage.cost` faltar, for inválido, NaN, negativo ou zero, o custo é **estimado** por `prompt_tokens` e `completion_tokens` vezes o preço por milhão (`OPENROUTER_PRECO_ENTRADA_USD_M` padrão 3.0; `OPENROUTER_PRECO_SAIDA_USD_M` padrão 15.0, pessimistas de propósito). Sem tokens também, vale `OPENROUTER_CUSTO_PADRAO_USD` (padrão 0.05). O custo devolvido numa chamada bem-sucedida nunca é 0, e é o mesmo valor somado ao teto diário.
- A chave nunca entra em log nem em erro: falhas viram só `OpenRouter -> <status>` ou o nome do tipo da exceção (sem exceção encadeada); o corpo de erro HTTP não é lido. Prompts e respostas não são logados.
