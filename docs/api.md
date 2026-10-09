# API do gabi.brain (gerado do código; não editar à mão)

Erros: `{"erro": <codigo>, "mensagem": <pt-BR>}` com `requisicao_invalida` (400), `nao_autenticado` (401), `sem_escopo`/`nao_permitido` (403), `nao_encontrado` (404), `conflito`/`confirmacao_divergente` (409), `tipo_invalido` (415). Dinheiro: string decimal ("1234.56"), saída negativa. Toda leitura de dinheiro traz o envelope `{dados_ate, desatualizado, proxima_rodada, fontes, dados}` (dados_ate = última rodada CONFERIDA; proxima_rodada = próxima captura agendada, UTC).

## REST (`/api/...`, só por `tailscale serve`; nível `boss` salvo indicação)

| Método | Rota | O que faz |
|---|---|---|
| GET | `/api/eu` | Quem sou eu: login, pessoa e nível de acesso. |
| POST | `/api/revogar-tudo` | Revoga todos os tokens de agentes. Exige o corpo {"confirmo": true}. |
| GET | `/api/saude` | Saúde do banco, versão do esquema, última rodada e contagem de cada tabela. |
| GET | `/api/seguranca` | Acessos, tokens de agentes ativos, chamadas em 24 h e último backup. |
| GET | `/api/v1/assinaturas` | Assinaturas detectadas, com os sinais: nova, reajustou, cobrada depois de cancelar. |
| PATCH | `/api/v1/assinaturas/{aid}` | Muda o status da assinatura e o lembrete até cancelar. |
| GET | `/api/v1/cadastros/categorias/equivalencias` | Equivalência entre a categoria do banco (Pluggy) e a nossa. |
| PUT | `/api/v1/cadastros/categorias/equivalencias` | Cria ou troca uma equivalência de categoria. |
| DELETE | `/api/v1/cadastros/categorias/equivalencias/{origem}` | Remove uma equivalência de categoria. |
| GET | `/api/v1/cadastros/pessoas/{pid}/cpf` | Documentos da pessoa (sempre mascarados); a consulta fica auditada. |
| GET | `/api/v1/cadastros/{tipo}` | Lista um cadastro: empresas, contas, pessoas, compromissos ou categorias. |
| POST | `/api/v1/cadastros/{tipo}` | Cria um item de cadastro. |
| DELETE | `/api/v1/cadastros/{tipo}/{id_}` | Exclusão lógica de um item de cadastro (nada é apagado). |
| GET | `/api/v1/cadastros/{tipo}/{id_}` | Um item de cadastro. |
| PATCH | `/api/v1/cadastros/{tipo}/{id_}` | Atualiza campos de um item de cadastro. |
| GET | `/api/v1/caixa/resumo` | KPIs do caixa único, série de saldo (passado e projeção) e o que pede a sua atenção. |
| GET | `/api/v1/caixa/semanas` | Semanas (passado real e projeção): entradas e saídas por categoria e saldo. |
| GET | `/api/v1/cartoes` | Cartões: fatura aberta, % do limite, série de 12 meses e categorias. |
| GET | `/api/v1/contagens` | Itens que pedem decisão por área do menu (caixa, gastos, regras) e o total do sino. |
| GET | `/api/v1/contas-pagar` | Contas agrupadas: atrasadas, hoje, próximas, adiante, débito automático, a conferir e pagas. |
| POST | `/api/v1/contas-pagar/{id_compromisso}/paga` | Baixa manual de um compromisso (vale só se não houver lançamento no extrato). |
| GET | `/api/v1/custo` | Custo do modelo (OpenRouter) no dia e no mês contra o teto. |
| GET | `/api/v1/destino` | Para onde vai o dinheiro: origem, categoria e destino, com comparação ao período anterior. |
| GET | `/api/v1/destino/agrupado` | Para onde vai o dinheiro agrupado por categoria, pessoa ou fornecedor (abas Fornecedores e Por pessoa). |
| GET | `/api/v1/fontes` | Estado de cada fonte: ok, nao_conferida, erro ou parada. |
| GET | `/api/v1/lancamentos` | Lançamentos paginados, com filtros e a origem de cada classificação. |
| POST | `/api/v1/lancamentos/lote` | Muda vários lançamentos de uma vez; criar_regra cria uma regra por estabelecimento. |
| PATCH | `/api/v1/lancamentos/{lid}` | Muda categoria, para quem, empresa ou frente de um lançamento (a origem vira 'voce'). |
| GET | `/api/v1/parcelas` | Parcelas: comprometido por mês e andamento de cada compra parcelada. |
| GET | `/api/v1/regras` | Regras de classificação. |
| PATCH | `/api/v1/regras/{rid}` | Liga ou desliga uma regra; ligar aplica ao passado. |
| GET | `/api/v1/rodadas` | Últimas rodadas de ingestão e se foram conferidas. |
| GET | `/api/v1/sugestoes` | Sugestões da Gabi (padrão: pendentes), com o impacto de cada regra. |
| POST | `/api/v1/sugestoes/{sid}/aprovar` | Aprova uma sugestão; sugestão de regra cria a regra ATIVA e a aplica ao passado. |
| POST | `/api/v1/sugestoes/{sid}/rejeitar` | Rejeita uma sugestão (nada é criado). |

## MCP (`/mcp`, Streamable HTTP, `Authorization: Bearer <token>`; só leitura)

| Ferramenta | Escopo | Entrada | O que faz |
|---|---|---|---|
| `financeiro_contas_a_pagar` | `fin` | ate | Contas atrasadas (com dias de atraso), do dia e dos próximos 7 dias. `ate` (AAAA-MM-DD) corta o que vence depois. |
| `financeiro_lancamentos` | `fin` | ate, categoria, conta, de, empresa, limite, para_quem, texto | Lançamentos (mais recentes primeiro). Datas AAAA-MM-DD; `limite` até 200. Cada item traz de onde veio cada classificação (origens). |
| `financeiro_para_onde_vai` | `fin` | periodo, por | Para onde foi o dinheiro: periodo = mes | semana | 12m; por = categoria | pessoa | fornecedor. Traz % do total e variação contra o período anterior. |
| `financeiro_saldo` | `fin` | conta | Saldo do caixa único (só as contas que o Ricardo liberou) e faturas de cartão em aberto. `conta` filtra pelo apelido. |

Não existem ferramentas de enviar, pagar, apagar, aprovar nem ligar regra (R13).
