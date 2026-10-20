# A receber e entradas previstas por mensagem (design)

Data: 20/10/2026 · Estado: aguardando revisão do dono · Relacionados: `gabi/dinheiro/projecao.py`, `esperados.py`, `agenda_financeira.py`, `gabi/mcp/`.

## Objetivo
1. Tela **Caixa › A receber**, espelho da "A pagar": o que deve entrar, por semana e origem, com atraso destacado.
2. O Ricardo manda "dia 10 entra 50000 no c6 pela venda do sofá" pelo Telegram/WhatsApp e a Gabi registra uma **entrada prevista** que entra na projeção, na agenda financeira e na tela.

Decisões do dono: registro **direto**, com **DESFAZER** (quem informa é ele; R1 vale para sugestões da Gabi, não para o que ele mesmo dita).

## Fora do escopo
Editar valor de uma entrada (cancela e registra de novo), entradas recorrentes manuais, envio de cobrança, qualquer escrita em conta bancária ou sistema externo.

## Dados
Migração nova (próximo número livre em `migrations/`): `entrada_prevista(id, dia text, valor_centavos int >0, conta_id int null, descricao text, estado check in ('prevista','recebida','cancelada') default 'prevista', lancamento_id int null, criada_em, criada_por, cancelada_em null, recebida_em null)`. Índice por (estado, dia).

## Serviço `gabi/dinheiro/a_receber.py`
`itens(con, hoje, ate) -> list[dict]` junta três origens, cada item com `origem` (`nota`|`aprendida`|`avulsa`), `dia`, `valor_centavos`, `quem`, `conta`, `atrasada`:
- `nota`: a previsão de NFS-e que a projeção já usa (`cobrar.previsao`: a_vencer e projetado).
- `aprendida`: `esperados.py` (recorrentes aprendidas; mostradas na tela e só no cenário "com recorrentes esperadas" da projeção, como hoje, para não contar em dobro com a NFS-e).
- `avulsa`: `entrada_prevista` em estado `prevista`.
Atrasada = dia < hoje e não recebida. Único ponto de leitura para tela, KPI `a_receber`, projeção e agenda financeira.

## Fechamento automático
Na rodada de captura, para cada `prevista` com `dia ≤ hoje+3`: um crédito real em conta liberada (a mesma `conta_id` se informada, qualquer uma se não), valor dentro de ±2%, data entre `dia−3` e `dia+30`, ainda não ligado a outra entrada. **Só fecha se o casamento for único**; vira `recebida` com `lancamento_id`. Ambíguo ou sem casamento: segue `prevista` (atrasada após o dia).

## Ferramentas MCP (escopo novo `entradas`)
- `entrada_prevista_registrar(dia: str ISO, valor: str decimal, conta: str|None, descricao: str) -> dict`: valida (valor > 0 e ≤ R$ 10.000.000, dia entre ontem e hoje+730, descrição 1–120 caracteres); resolve `conta` por nome contra as contas liberadas (ambígua ou inexistente → erro com as opções, sem gravar); idempotente: mesmo (dia, valor, conta, descrição) nos últimos 10 min devolve a existente. Resposta com id e texto pronto: "Registrei: 10/11, R$ 50.000,00, C6, venda do sofá. Responda DESFAZER para cancelar."
- `entrada_prevista_desfazer(id: int)`: só `prevista` → `cancelada`; `recebida`/`cancelada` → erro.
- `entrada_prevista_listar()`: as `prevista` e as últimas `recebida`/`cancelada` (30 dias).
Texto de terceiros nunca vira entrada: só o canal do dono, com token de escopo `entradas`. Auditoria: id e ação, nunca descrição nem valor.

## Skill do Hermes
`~/.hermes/skills/gabi-brain/references/entradas.md`: extrai dia/valor/conta/descrição; "dia N" sem mês = próxima ocorrência; ambiguidade (valor, data, conta) → pergunta curta antes de chamar; após registrar repete o texto devolvido; "desfazer" chama a ferramenta com o último id.

## Painel e integração
- `GET /api/v1/dinheiro/a-receber?ate=` (envelope, nível `boss`) e tela **Caixa › A receber** (semanas, origem, atraso, total); KPI `a_receber` do resumo passa a vir do serviço.
- `projecao.projetar` soma `nota` + `avulsa` nas entradas; `agenda_financeira` mostra as avulsas e as atrasadas; cenário "com recorrentes esperadas" inalterado.
- Cancelar também pelo painel (botão na linha avulsa).

## Testes
Serviço (3 origens, atraso, janela), fechamento (casa único, ambíguo, fora da janela, conta diferente), ferramentas (validações, idempotência, conta ambígua, desfazer, escopo), projeção com avulsa, rota e tela, e ponta a ponta: registrar → projeção → crédito real → `recebida`.

## Passos do dono depois de pronto
Dar o escopo `entradas` ao token do Hermes, incluir as 3 ferramentas no `tools.include` e reiniciar o gateway (como nas `financeiro_*`).
