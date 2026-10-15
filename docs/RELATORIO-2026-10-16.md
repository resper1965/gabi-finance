# Relatório da sessão de 16/10/2026 (gabi.brain + Hermes)
Escrito após uma queda de energia. **Se a máquina cair de novo, leia este arquivo e `docs/BACKLOG.md`.** Memória do projeto: `~/.claude/projects/-home-ricardo/memory/` (índice `MEMORY.md`).

## 1. Resumo
A sessão começou com três queixas: **saldos/resumos faltando, WhatsApp em inglês e mensagens mal formatadas**. Ao longo dela surgiram: o backlog completo, a avaliação do Hermes, a falta da **agenda financeira**, o **recebível atrasado do Matheus**, o mapa de **quem paga o Ricardo** e a ideia de aprender o "normal" por **5 meses de média e regularidade**.

## 2. Diagnósticos (causa real)
| Queixa | Causa | Estado |
|---|---|---|
| WhatsApp em inglês | Hermes sem `display.language` (mensagens fixas em inglês) e `stt.language: en` | ✅ corrigido (pt), gateway reiniciado; backup `~/.hermes/config.yaml.bak-2026-10-16-idioma` |
| Resumo ilegível | `resumo_manha` montava um texto corrido de 5 linhas | ✅ blocos 💰 Financeiro / 📅 Agenda / 📧 E-mail; instalado |
| Saldos faltando | o provedor (`openfinance_list_accounts`) devolve só parte das contas (4 a 17 de 17) | ✅ código com retry (3 tentativas, junta por conta); aviso "incompleta" em `rodada.erro`. O caixa soma a última leitura de cada conta, então o efeito era de atualidade, não de saldo errado |
| "Falta de agenda financeira" | em 11/10 os alertas do OpenClaw foram desligados; o substituto no Hermes só diz "atrasadas, sai hoje, saldo" | 🔧 desenho B aprovado em 16/10 |
| Matheus não pagou | o brain não tem "a receber" cadastrado, só NFS-e da Bekaa e reembolsos | 🔧 desenho do "a receber" (ver §4) |
| Adiantamento Sirlene e Contabilidade | existem só como eventos da agenda do Google (dias 20 e 15), não como compromissos. **A Contabilidade era HOJE (15/10 em Brasília)**; o Adiantamento é 20/10 | ⏸ cadastrar (dados do Ricardo) |
| XP Investimentos "parada" | a conexão saiu do mcp.ai em 11/10; a conta 10 segue `sim` e conta como fonte ativa | ⏸ Ricardo: pôr conta 10 em `nao` no painel |

## 3. Feito e instalado nesta sessão
- Idioma pt no Hermes. Resumo da manhã em blocos (instalado em produção). `docs/BACKLOG.md` (fonte única). Pontos de `STATUS.md` e `PENDENCIAS-RICARDO.md` apontando para ele.
- Retry dos saldos (código e testes; instalação registrada na seção 6).
- Testes: suíte completa 2081 passando antes do retry; 2 testes antigos do resumo da agenda atualizados; `tests/dinheiro` 435 verdes depois do retry.
- Perfil de 5 meses (script descartável de leitura) sobre créditos e débitos reais.

## 4. Decisões (e o que ficou aberto)
- **Aprovado:** agenda financeira **B** (diária curta: atrasadas, hoje, 3 dias com previsão do saldo; segunda: 30 dias); pausar o resumo semanal de domingo; previsão diária conservadora (só saídas, aviso de "entradas esperadas não contadas"); opção C do backlog (núcleo + "Depois").
- **Direção nova do Ricardo:** o brain deve **aprender o normal** de pagadores e favorecidos por **média e regularidade de 5 meses** (em vez de cadastro manual de cada linha). Isto vira o "a receber" automático (§5).
- **Aberto (precisa do Ricardo):** quem é o pagador do contrato ORM da família Reis (candidato: X2 Intermediações, R$ 10.208, 2 meses de histórico, **não confirmado**) e o que são as camadas da NESS; escopo dos comprovantes (A automático nas conversas, B só encaminhado, C ambos) e se a escuta lê as mensagens enviadas por ele; **H0** (restringir ferramentas do WhatsApp/Telegram, ligar `write_approval` de skills e memória, terminal em Docker) **não aprovado**; conta 10 → `nao`.

## 5. Perfil de 5 meses: o que os dados mostram
Regra usada (descartável): grupo regular = presente em ≥ 4 dos 5 meses, variação do valor (cv) < 0,20 e dia com espalhamento ≤ 7.
- **Regulares:** IONIC R$ 22.261,22 (dia ~5, C6); FGV R$ 9.204,69 (dia ~25, Itaú); Barra do Pará R$ 3.660,15 (dia ~8, C6).
- **"Semi" porque várias camadas se misturam:** NESS (cv 0,32 a 0,62; três faixas de valor e dias) e Bekaa (cv 0,31). Para aprender o normal, o agrupamento precisa **separar por faixa de valor/conta**, não só pelo nome.
- **Irregulares (poucos meses):** X2 Intermediações (2 meses: não há "normal" ainda), Twyn.
- **Limitação do levantamento de débitos:** a primeira passada filtrou `natureza='caixa'` e só trouxe débitos automáticos; os Pix a pessoas (Sirlene etc.) ficam em outras naturezas. O perfil real de pagamentos deve partir dos **compromissos** do brain e dos débitos por favorecido, sem esse filtro.

## 6. Erros meus nesta sessão (para não repetir)
- Instalei com a suíte rodada com `-x` e li o código de saída do `tail` como sucesso: havia 1 falha (doc gerada de `docs/api.md`). Corrigido; **regra: ler o resumo do pytest antes de afirmar verde ou instalar.**
- Disse que o saldo "ficava incompleto" com a lista parcial; o caixa soma a última leitura de cada conta, então o efeito era só de atualidade.

- Respondi que a Contabilidade era "ontem" porque usei a data do servidor (CEST, 16/10 de madrugada); para o Ricardo ainda era 15/10 (BRT). **Regra: "hoje" é sempre a data de Brasília; o servidor está 3 a 5 h adiantado.** O código do brain já usa BRT (verificado no resumo real).

## 7. Melhorias sugeridas (por retorno)
1. **Perfil de normalidade como módulo do brain** (`gabi/dinheiro/perfil.py`): média, regularidade, dia típico, classe (regular/semi/irregular) por pagador e favorecido, com faixas de valor; alimenta "a receber" e alertas de desvio (atrasou, valor diferente). Dado calculado, nada chumbado.
2. **"A receber" detectado + cobrança com anuência:** atraso sobre o normal aprendido → aviso e **rascunho** da cobrança (R2 intacta). Depois, envio com aprovação por e-mail como exceção com ADR novo.
3. **Compromissos a partir da agenda:** eventos "Pagar…/Adiantamento…" viram **sugestões** de compromisso (aprovadas por ele).
4. **Cron `no_agent` do Hermes** para resumo e agenda financeira (sem modelo). Pendente verificar se o script alcança o MCP com o token.
5. **H0:** ferramentas por canal, `write_approval`, terminal em Docker (hoje o WhatsApp e o Telegram têm `terminal`, `write_file` e `execute_code`).
6. **Canal de reserva** (ntfy/SMS) para avisos de crise quando o Telegram/WhatsApp cair.
7. **Evals de mensagem** (resumo, fechamento, avisos) com exemplos fixos, em vez de só inspeção visual.
8. **Checklist de "pronto" antes de instalar:** suíte inteira lida, `docs/api.md` regerado, painel `vitest` verde.

## 8. Próximos passos, na ordem
1. Instalar o retry dos saldos. 2. Agenda financeira B (módulo + ferramenta MCP + testes) e pausar o resumo de domingo no Hermes. 3. Perfil de 5 meses como módulo. 4. Com as respostas do Ricardo: "a receber" (Matheus/ORM, camadas da NESS), comprovantes, H0, conta 10.
