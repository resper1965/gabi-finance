# Módulos do `gabi/`

Um verbete por módulo Python de `gabi/` (e por pacote): o que faz, as tabelas que lê e grava, quem o chama e os testes. O teste `tests/test_docs.py` falha se um módulo novo não aparecer aqui.

**Como ler as listas.** "Lê" e "Grava" saem de uma busca por nomes de tabela nas instruções SQL do **próprio módulo** (`select … from`, `join`, `insert into`, `update`, `delete from`); o que um módulo faz por meio de outro (por exemplo, a rota que chama `dinheiro.despesas`) aparece no verbete do outro. "Chamado por" lista os módulos de `gabi/` que o importam; módulo sem chamador é um ponto de entrada (CLI, unit do systemd, servidor ASGI) ou sobra do corte, e o verbete diz qual. As tabelas estão explicadas em [`dados.md`](dados.md).

**Regras que valem em todo o código** (as que os docstrings citam): R1 a Gabi sugere, o Ricardo decide; R2 nenhum envio externo automático (e a ponte só deixa passar métodos de leitura); R3 a identidade só vale vinda do socket Unix; R4 toda chamada `/api/*` é registrada; R5 só o serviço de fontes tem rede e token do Nibo; R7 dinheiro em centavos inteiros (nunca `float` no banco; string decimal na API); R13 o MCP não envia, paga, apaga, aprova nem liga regra; R14 texto de terceiros é dado, nunca instrução.

## Base

### `gabi`
Pacote raiz. Não tem código: só marca `gabi` como pacote Python (tudo roda a partir de `/opt/gabi-finance`, sem `pip install` do projeto).

- **Arquivo:** `gabi/__init__.py` (0 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** — (pacote: os módulos dele são importados pelo nome completo)
- **Testes:** os testes dos módulos do pacote

### `gabi.db`
Conexão SQLite (WAL, FKs) e migrações numeradas. Consome: nada. Spec §12/§13.4.

- **Arquivo:** `gabi/db.py` (86 linhas)
- **Lê:** —
- **Grava:** `schema_versao`
- **Chamado por:** `gabi.acesso`, `gabi.api`, `gabi.avisos`, `gabi.backup`, `gabi.cobrar.notas`, `gabi.cobrar.notas_importar`, `gabi.cobrar.receber_manual`, `gabi.cobrar.recebimentos`, `gabi.decisoes`, `gabi.dinheiro.captura`, `gabi.dinheiro.gastador`, `gabi.dinheiro.nao_gasto`, `gabi.dinheiro.rodar`, `gabi.exportacao`, `gabi.identidade`, `gabi.importar`, `gabi.mcp.ferramentas_agir`, `gabi.mcp.servidor`, `gabi.mcp.tokens`, `gabi.rotas.dinheiro`, `gabi.telegram`
- **Testes:** `tests/cobrar/test_notas.py`, `tests/cobrar/test_notas_importar.py`, `tests/cobrar/test_previsao.py`, `tests/cobrar/test_receber_manual.py`, `tests/cobrar/test_recebimentos.py`, `tests/conftest.py` …

### `gabi.api`
API do gabi-finance (Fase 0): identidade, saúde, segurança e revogação. Toda chamada /api/* é registrada (R4).

- **Arquivo:** `gabi/api.py` (192 linhas)
- **Lê:** `acesso`, `rodada`, `schema_versao`
- **Grava:** `chamada`, `decisao`, `token_agente`
- **Chamado por:** ponto de entrada: `uvicorn --factory gabi.api:fabrica` (unit `gabi-finance-api`)
- **Testes:** `tests/mcp/test_decisoes_canal.py`, `tests/rotas/test_avisos_api.py`, `tests/rotas/test_cadastros_api.py`, `tests/rotas/test_cobrar_api.py`, `tests/rotas/test_dinheiro_api.py`, `tests/rotas/test_gastos_api.py` …

### `gabi.identidade`
Identidade pelo cabeçalho do `tailscale serve` (Tailscale-User-Login). R3: só vale vindo do socket Unix do serviço.

- **Arquivo:** `gabi/identidade.py` (91 linhas)
- **Lê:** `acesso`, `matriz_acesso`
- **Grava:** —
- **Chamado por:** `gabi.acesso`, `gabi.api`, `gabi.rotas.agentes`, `gabi.rotas.avisos`, `gabi.rotas.cadastros`, `gabi.rotas.cobrar`, `gabi.rotas.contagens`, `gabi.rotas.decisoes`, `gabi.rotas.despesas`, `gabi.rotas.dinheiro`, `gabi.rotas.gastos`
- **Testes:** `tests/test_identidade.py`, `tests/test_matriz_acesso.py`

### `gabi.acesso`
Cadastro de quem pode acessar (login Tailscale -> pessoa + nível). Uso: python -m gabi.acesso adicionar|listar.

- **Arquivo:** `gabi/acesso.py` (49 linhas)
- **Lê:** —
- **Grava:** `acesso`, `decisao`
- **Chamado por:** CLI: `python -m gabi.acesso` (adicionar e listar quem entra)
- **Testes:** `tests/mcp/test_decisoes_canal.py`, `tests/rotas/test_avisos_api.py`, `tests/rotas/test_cadastros_api.py`, `tests/rotas/test_cobrar_api.py`, `tests/rotas/test_dinheiro_api.py`, `tests/rotas/test_gastos_api.py` …

### `gabi.envelope`
Envelope de toda resposta de leitura: `dados_ate` vem da última rodada CONFERIDA, não da última tentativa (R4/Review 4).

- **Arquivo:** `gabi/envelope.py` (141 linhas)
- **Lê:** `parametro`, `rodada`
- **Grava:** —
- **Chamado por:** `gabi.avisos`, `gabi.mcp.ferramentas_dia`, `gabi.mcp.servidor`, `gabi.rotas.agentes`, `gabi.rotas.avisos`, `gabi.rotas.cadastros`, `gabi.rotas.cobrar`, `gabi.rotas.contagens`, `gabi.rotas.decisoes`, `gabi.rotas.despesas`, `gabi.rotas.dinheiro`, `gabi.rotas.gastos`
- **Testes:** `tests/dinheiro/test_conferencia.py`, `tests/dinheiro/test_rodar.py`, `tests/test_envelope.py`

### `gabi.rodada`
Registro de rodadas: cada captura/importação/backup vira uma linha consultável. Consome: db.

- **Arquivo:** `gabi/rodada.py` (34 linhas)
- **Lê:** —
- **Grava:** `rodada`
- **Chamado por:** `gabi.backup`, `gabi.cobrar.notas_importar`, `gabi.dinheiro.captura`, `gabi.exportacao`, `gabi.importar`
- **Testes:** `tests/test_api.py`, `tests/test_rodada.py`

### `gabi.bruto`
Arquivo bruto imutável: JSONL comprimido por dia e fonte, base para reconstruir o banco (spec §13.2).

- **Arquivo:** `gabi/bruto.py` (29 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.dinheiro.captura`
- **Testes:** `tests/dinheiro/test_moeda.py`, `tests/test_bruto.py`

### `gabi.backup`
Backup do banco com integrity_check e teste de restauração (spec §13.3). Consome: db, rodada.

- **Arquivo:** `gabi/backup.py` (96 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.exportacao`
- **Testes:** `tests/test_backup_banco.py`, `tests/test_deploy.py`

### `gabi.exportacao`
Exportação semanal do banco, criptografada com a chave pública do Ricardo, para ele puxar para fora da VPS (G17). Consome: backup (backup_db, testar_restauracao), rodada. Nunca deixa cópia em claro na pasta de saída.

- **Arquivo:** `gabi/exportacao.py` (71 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** unit `gabi-finance-exportacao` (`python -m gabi.exportacao`)
- **Testes:** `tests/test_deploy.py`, `tests/test_exportacao.py`

### `gabi.hoje`
'Hoje' do Ricardo: sempre Brasília, nunca o relógio do servidor (que roda em CEST).

- **Arquivo:** `gabi/hoje.py` (9 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.backup`, `gabi.dinheiro.analise`, `gabi.dinheiro.caixa`, `gabi.dinheiro.despesas`, `gabi.exportacao`, `gabi.importar`, `gabi.mcp.ferramentas_despesas`, `gabi.rotas.despesas`
- **Testes:** `tests/test_hoje.py`

### `gabi.mascara`
Máscara de CPF/documentos: mantém só os 2 últimos dígitos e a pontuação. Portado do repositório de migração (revisado).

- **Arquivo:** `gabi/mascara.py` (33 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.dinheiro.modelo`
- **Testes:** `tests/test_mascara.py`

### `gabi.agentes`
Chaves de agentes externos do MCP (ADR-036): regras por cima de gabi/mcp/tokens.py. O segredo só sai em criar/rotacionar, uma vez; nada aqui devolve hash.

- **Arquivo:** `gabi/agentes.py` (110 linhas)
- **Lê:** `chamada_mcp`, `token_agente`
- **Grava:** `decisao`
- **Chamado por:** `gabi.rotas.agentes`
- **Testes:** `tests/test_agentes.py`

### `gabi.decisoes`
Canal de decisão: perguntas com opções numeradas que o Ricardo responde pelo Telegram/WhatsApp (o Hermes só apresenta e repassa o número). R1: a Gabi pergunta, o Ricardo decide. R2: nada é enviado daqui. `efeito` vem de uma lista FECHADA e validada; nunca código livre. Responder grava a decisão (origem 'canal') e aplica o efeito na mesma transação; só uma resposta por pergunta.

- **Arquivo:** `gabi/decisoes.py` (148 linhas)
- **Lê:** `pessoa`
- **Grava:** `conta`, `decisao`, `lancamento`, `pergunta`
- **Chamado por:** `gabi.dinheiro.sugestoes_agenda`, `gabi.dinheiro.sugestoes_dono`, `gabi.mcp.ferramentas_dec`, `gabi.mcp.ferramentas_dia`, `gabi.rotas.decisoes`
- **Testes:** `tests/decisoes/test_decisoes.py`, `tests/dinheiro/test_sugestoes_agenda.py`, `tests/dinheiro/test_sugestoes_dono.py`, `tests/mcp/test_dia.py`

### `gabi.avisos`
Produtor de avisos financeiros: grava em `aviso` o que o Ricardo precisa saber (rodada parada, conta atrasada, assinatura cancelada e cobrada, o que vence hoje, serviço que falhou). No gabi-finance só há avisos do dinheiro (agenda, atividades, projetos, Teams, documentos e Hermes saíram). Consome: db (rodada, compromisso, assinatura, lancamento, aviso). Só grava; entregar é outra etapa.

- **Arquivo:** `gabi/avisos.py` (300 linhas)
- **Lê:** `assinatura`, `compromisso`, `conciliacao`, `conferencia`, `conta`, `lancamento`, `parametro`, `rodada`
- **Grava:** `aviso`
- **Chamado por:** `gabi.agentes`, `gabi.telegram`
- **Testes:** `tests/dinheiro/test_moeda.py`, `tests/test_avisos.py`, `tests/test_avisos_antecipados.py`, `tests/test_telegram.py`

### `gabi.telegram`
Entrega dos avisos ao Telegram (G15): DESLIGADA por padrão. Só envia se TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID estiverem no ambiente (/etc/gabi-finance/telegram.env, colocado pelo Ricardo: é a exceção à R2). Envia o texto em pt-BR do aviso (só nome, valor e datas: nunca CPF, conta ou chave PIX), no máximo 10 por rodada, só os dos últimos 2 dias e ainda não lidos, em ordem de criação; marca `telegram_em` somente depois do 200. Aviso obsoleto (condição já resolvida) não é enviado: fecha sem mandar. O token nunca entra na mensagem nem no log. Uso: python -m gabi.telegram (timer). Consome: aviso, rotas.avisos.descrever.

- **Arquivo:** `gabi/telegram.py` (75 linhas)
- **Lê:** —
- **Grava:** `aviso`
- **Chamado por:** unit `gabi-finance-telegram` (`python -m gabi.telegram`)
- **Testes:** `tests/test_avisos.py`, `tests/test_deploy.py`, `tests/test_telegram.py`

### `gabi.dia`
Bloco de dinheiro do dia (`hoje(con, agora) -> {"dinheiro": ...}`), lido só de tabelas prontas. **Sem chamador hoje:** sobrou do corte (a rota `/hoje` saiu; o resumo da manhã usa `dinheiro.agenda_financeira`). Fica por decisão do spec e tem teste próprio.

- **Arquivo:** `gabi/dia.py` (18 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** nenhum módulo de `gabi/` o importa hoje (sobra do corte)
- **Testes:** `tests/test_dia.py`

### `gabi.importar`
Carga única do staging (Plano 1) no banco: pessoas, empresas, compromissos, conciliação, faturas, contas e cadastros de compromissos. Idempotente e numa só transação. Depois da migração 0091 não lê mais pets, lista de números autorizados nem memória de conversas. CLI: `python -m gabi.importar --banco ... --staging ...`; sem chamador no código.

- **Arquivo:** `gabi/importar.py` (150 linhas)
- **Lê:** `compromisso_linha`
- **Grava:** —
- **Chamado por:** CLI: `python -m gabi.importar` (carga única do staging); nenhum módulo o importa
- **Testes:** `tests/test_importar.py`

## Dinheiro (`gabi/dinheiro`)

### `gabi.dinheiro`
Pacote do núcleo financeiro: captura do Open Finance, conciliação, compromissos (A pagar), regras, projeção de caixa, gastos, assinaturas e despesas.

- **Arquivo:** `gabi/dinheiro/__init__.py` (0 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** — (pacote: os módulos dele são importados pelo nome completo)
- **Testes:** os testes dos módulos do pacote

### `gabi.dinheiro.agenda_financeira`
Agenda financeira em mensagem: o que vence, o que está atrasado e a previsão do saldo (diária curta e semanal de 30 dias). Só lê; sem rede nem modelo. A previsão é a do painel (`projecao.projetar`): saídas dos compromissos e entradas só das NFS-e previstas. Consome: contas_pagar (contas_a_pagar, caixa_unico), projecao, avisos (CONFIRMADO via conciliacao).

- **Arquivo:** `gabi/dinheiro/agenda_financeira.py` (189 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.dinheiro.fechamento`, `gabi.dinheiro.sugestoes_dono`, `gabi.mcp.ferramentas_dia`, `gabi.mcp.servidor`
- **Testes:** `tests/dinheiro/test_agenda_financeira.py`, `tests/dinheiro/test_esperados.py`, `tests/evals/test_mensagens.py`

### `gabi.dinheiro.analise`
Análises do caixa (recorrentes, previsão, gastos, vazamentos). Portado do gabi-fin/finlib.py SEM alterar a lógica.

- **Arquivo:** `gabi/dinheiro/analise.py` (142 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.dinheiro.agenda_financeira`, `gabi.dinheiro.desvio`, `gabi.mcp.servidor`, `gabi.rotas.dinheiro`, `gabi.rotas.gastos`
- **Testes:** `tests/dinheiro/test_golden_analise.py`

### `gabi.dinheiro.assinaturas`
Assinaturas a revisar vindas de CATEGORIA (além das que o detector de recorrentes acha). Consome: db (lancamento, categoria).

- **Arquivo:** `gabi/dinheiro/assinaturas.py` (57 linhas)
- **Lê:** `categoria`, `lancamento`
- **Grava:** —
- **Chamado por:** `gabi.rotas.gastos`
- **Testes:** `tests/dinheiro/test_assinaturas.py`

### `gabi.dinheiro.caixa`
Funções puras de análise financeira, portadas do gabi-fin/finlib.py SEM alterar a lógica (R: Ponytail).

- **Arquivo:** `gabi/dinheiro/caixa.py` (102 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.dinheiro.analise`, `gabi.dinheiro.assinaturas`, `gabi.dinheiro.captura`, `gabi.dinheiro.conciliacao`, `gabi.dinheiro.contas_pagar`, `gabi.dinheiro.desvio`, `gabi.dinheiro.emissores`, `gabi.dinheiro.modelo`, `gabi.dinheiro.nao_gasto`
- **Testes:** `tests/dinheiro/test_golden_caixa.py`

### `gabi.dinheiro.captura`
Captura do Open Finance (mcp.ai): contas, saldos, lançamentos e faturas -> banco. Leitura incremental (R11).

- **Arquivo:** `gabi/dinheiro/captura.py` (400 linhas)
- **Lê:** —
- **Grava:** `captura_conta`, `conciliacao`, `conta`, `conta_estado`, `fatura`, `lancamento`, `parametro`, `rodada`, `saldo`
- **Chamado por:** `gabi.dinheiro.rodar`
- **Testes:** `tests/dinheiro/test_captura.py`, `tests/dinheiro/test_moeda.py`, `tests/dinheiro/test_rodar.py`

### `gabi.dinheiro.classificar`
Classificação em cascata de um lançamento (spec: regra -> equivalência do banco -> cache -> modelo).

- **Arquivo:** `gabi/dinheiro/classificar.py` (192 linhas)
- **Lê:** `categoria`, `compromisso`, `compromisso_padrao`, `conciliacao`, `conta`, `equivalencia_categoria`, `pessoa`, `regra`
- **Grava:** `decisao`, `lancamento`, `sugestao`
- **Chamado por:** `gabi.dinheiro.para_quem_fila`, `gabi.dinheiro.rodar`
- **Testes:** `tests/dinheiro/test_classificar.py`, `tests/dinheiro/test_condicao.py`, `tests/dinheiro/test_para_quem_certeiro.py`, `tests/rotas/test_cadastros_api.py`

### `gabi.dinheiro.compromissos`
Compromissos do mes corrente e do seguinte: linhas da planilha + documentos abertos + faturas de cartao.

- **Arquivo:** `gabi/dinheiro/compromissos.py` (205 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.dinheiro.conciliacao`, `gabi.dinheiro.contas_pagar`, `gabi.dinheiro.despesas`, `gabi.dinheiro.planilha`
- **Testes:** `tests/dinheiro/test_despesas.py`

### `gabi.dinheiro.conciliacao`
Conciliação: marca cada compromisso como pago, aberto, atrasado ou a_conferir casando com o extrato.

- **Arquivo:** `gabi/dinheiro/conciliacao.py` (224 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.avisos`, `gabi.dinheiro.agenda_financeira`, `gabi.dinheiro.contas_pagar`
- **Testes:** `tests/dinheiro/test_conciliacao.py`

### `gabi.dinheiro.condicao`
Condição opcional de uma regra: só vale se o lançamento também confere em conta, faixa de valor e/ou dia da semana. JSON: {"conta_id": [1, 2], "valor_min": 1000, "valor_max": 5000, "dias_semana": [5, 6]}. Valor em centavos, absoluto (entrada e saída); 0 = segunda … 6 = domingo. Todas as chaves presentes precisam conferir. Consome: nada (puro).

- **Arquivo:** `gabi/dinheiro/condicao.py` (47 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.dinheiro.classificar`, `gabi.dinheiro.regras`
- **Testes:** `tests/dinheiro/test_condicao.py`

### `gabi.dinheiro.conferencia`
Conferência de uma rodada de captura (ADR-023, substitui as heurísticas do ADR-009): SÓ INFORMA, não trava o `dados_ate`. A rodada vale (`conferida=1`) quando terminou ok e sem aviso. Por conta bancária fica uma linha `saldo_final`: a variação do saldo entre o último fechamento de dia e o atual comparada à soma dos lançamentos postados. Divergência vira o aviso `saldo_divergente` (avisos.py), nunca bloqueio.

- **Arquivo:** `gabi/dinheiro/conferencia.py` (57 linhas)
- **Lê:** `conta`, `lancamento`, `saldo`
- **Grava:** `conferencia`, `rodada`
- **Chamado por:** `gabi.dinheiro.rodar`
- **Testes:** `tests/dinheiro/test_conferencia.py`

### `gabi.dinheiro.consultas`
Consultas de leitura compartilhadas pela API HTTP e pelo servidor MCP (uma lógica só, dois transportes).

- **Arquivo:** `gabi/dinheiro/consultas.py` (135 linhas)
- **Lê:** `categoria`, `conta`, `empresa`, `lancamento`, `pessoa`
- **Grava:** —
- **Chamado por:** `gabi.mcp.servidor`, `gabi.rotas.contagens`, `gabi.rotas.dinheiro`, `gabi.rotas.gastos`
- **Testes:** `tests/dinheiro/test_moeda.py`, `tests/dinheiro/test_rumo.py`

### `gabi.dinheiro.contas_pagar`
Compromissos do mês (gerar + conciliar), contas a pagar e caixa único. Consome: dinheiro.{repositorio,compromissos,conciliacao,caixa}.

- **Arquivo:** `gabi/dinheiro/contas_pagar.py` (137 linhas)
- **Lê:** `compromisso`, `compromisso_linha`, `conta`, `fatura`, `lancamento`, `saldo`
- **Grava:** `decisao`, `valor_do_mes`
- **Chamado por:** `gabi.dia`, `gabi.dinheiro.agenda_financeira`, `gabi.dinheiro.despesas`, `gabi.dinheiro.fechamento`, `gabi.dinheiro.projecao`, `gabi.dinheiro.rodar`, `gabi.mcp.servidor`, `gabi.rotas.cadastros`, `gabi.rotas.contagens`, `gabi.rotas.dinheiro`, `gabi.rotas.gastos`
- **Testes:** `tests/dinheiro/test_contas_pagar.py`, `tests/dinheiro/test_despesas.py`, `tests/dinheiro/test_pipeline_compromissos.py`

### `gabi.dinheiro.despesas`
Despesas (fixas e avulsas): regras de criar, listar, mudar, dispensar, encerrar e excluir sobre `compromisso_linha`. Chamado pela API, pelo painel e pelo MCP.

- **Arquivo:** `gabi/dinheiro/despesas.py` (435 linhas)
- **Lê:** `compromisso`, `conciliacao`
- **Grava:** `compromisso_linha`, `decisao`, `valor_do_mes`
- **Chamado por:** `gabi.mcp.ferramentas_despesas`, `gabi.rotas.cadastros`, `gabi.rotas.despesas`
- **Testes:** `tests/dinheiro/test_despesas.py`

### `gabi.dinheiro.despesas_empresa`
Despesas de empresa pagas no PF, por mês: o que o Ricardo pode cobrar da ness/IONIC ou lançar na PJ (ele mesmo; nada é enviado, R2). Substitui o reembolso PJ, a cobrança e o lote do Nibo (ADR-023). Consome: lancamento, conta, empresa.

- **Arquivo:** `gabi/dinheiro/despesas_empresa.py` (24 linhas)
- **Lê:** `conta`, `empresa`, `lancamento`
- **Grava:** —
- **Chamado por:** `gabi.mcp.servidor`
- **Testes:** `tests/dinheiro/test_despesas_empresa.py`

### `gabi.dinheiro.desvio`
Desvio do normal (AR8): um recorrente cujo valor deste mês foge do que ele costuma ser. Consome: analise (recorrentes), caixa.

- **Arquivo:** `gabi/dinheiro/desvio.py` (44 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.dinheiro.agenda_financeira`
- **Testes:** `tests/dinheiro/test_desvio.py`

### `gabi.dinheiro.emissores`
Regras por emissor (quem paga cada conta): chaves normalizadas. Portado do gabi-fin/emissores.py SEM alterar a lógica.

- **Arquivo:** `gabi/dinheiro/emissores.py` (55 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.dinheiro.compromissos`
- **Testes:** `tests/dinheiro/test_golden_emissores_extrator.py`

### `gabi.dinheiro.esperados`
Entradas esperadas: aprende o normal de cada pagador pelos últimos 5 meses (média, valor típico, dia costumeiro) e diz o que já deveria ter caído e não caiu. Só lê; não grava nem envia (R1/R2). Nada de pagador chumbado: tudo vem do extrato. Consome: lancamento, conta.

- **Arquivo:** `gabi/dinheiro/esperados.py` (86 linhas)
- **Lê:** `conta`, `lancamento`
- **Grava:** —
- **Chamado por:** `gabi.cobrar.a_receber`, `gabi.dinheiro.agenda_financeira`
- **Testes:** `tests/dinheiro/test_esperados.py`

### `gabi.dinheiro.favorecidos`
Sugestões de regra por favorecido de PIX enviado. Consome: db (lancamento, regra, sugestao), regras.criar_sugestao.

- **Arquivo:** `gabi/dinheiro/favorecidos.py` (47 linhas)
- **Lê:** `lancamento`, `regra`, `sugestao`
- **Grava:** —
- **Chamado por:** `gabi.dinheiro.classificar`
- **Testes:** `tests/dinheiro/test_favorecidos.py`

### `gabi.dinheiro.fechamento`
Fechamento do dia (H3), sem modelo: gastos de hoje (total e os 3 maiores), baixas confirmadas hoje e o que ficou atrasado. Só contas liberadas. Só lê; o texto sai pronto para o celular (até 5 linhas) e vazio de movimento vira uma frase só. Consome: lancamento, conta, contas_pagar.

- **Arquivo:** `gabi/dinheiro/fechamento.py` (37 linhas)
- **Lê:** `conta`, `lancamento`
- **Grava:** —
- **Chamado por:** `gabi.mcp.servidor`
- **Testes:** `tests/dinheiro/test_fechamento.py`

### `gabi.dinheiro.gastador`
Quem gastou: o portador da conta (conta.usuarios), separado de "para quem" (de quem é o gasto).

- **Arquivo:** `gabi/dinheiro/gastador.py` (125 linhas)
- **Lê:** `conta`, `pessoa`
- **Grava:** `gastador_regra`, `lancamento`
- **Chamado por:** `gabi.dinheiro.captura`, `gabi.mcp.ferramentas_agir`, `gabi.rotas.cadastros`, `gabi.rotas.dinheiro`
- **Testes:** `tests/dinheiro/test_captura.py`, `tests/dinheiro/test_gastador.py`, `tests/rotas/test_dinheiro_api.py`

### `gabi.dinheiro.modelo`
Passo opcional de modelo da classificação (lotes, teto de custo em `parametro`, texto de terceiros como dado, CPF mascarado). **Dormente em produção:** o cliente do modelo era injetado pela ponte do OpenRouter, que saiu no corte, então nada chama o modelo. A parte que ainda roda é a leitura do gasto do dia e do mês em `custo_modelo`, usada pelo cartão "Custo da Gabi" do painel (`GET /api/v1/custo`).

- **Arquivo:** `gabi/dinheiro/modelo.py` (189 linhas)
- **Lê:** `categoria`, `custo_modelo`, `lancamento`, `parametro`, `pessoa`
- **Grava:** `sugestao`
- **Chamado por:** `gabi.rotas.gastos`
- **Testes:** `tests/dinheiro/test_modelo.py`

### `gabi.dinheiro.moeda`
Valor de um lançamento em reais, a partir da transação crua do mcp.ai. Função pura, usada pela captura e por tools.corrigir_moeda.

- **Arquivo:** `gabi/dinheiro/moeda.py` (53 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.dinheiro.captura`
- **Testes:** `tests/dinheiro/test_moeda.py`

### `gabi.dinheiro.nao_gasto`
O que não é gasto: ajusta a natureza do lançamento depois do caixa.natureza (que fica intocado, provado pelo golden).

- **Arquivo:** `gabi/dinheiro/nao_gasto.py` (119 linhas)
- **Lê:** `conta`, `empresa`, `fatura`
- **Grava:** `lancamento`
- **Chamado por:** `gabi.dinheiro.captura`, `gabi.mcp.ferramentas_agir`, `gabi.rotas.dinheiro`
- **Testes:** `tests/dinheiro/test_nao_gasto.py`

### `gabi.dinheiro.olhar_a_frente`
Olhar à frente (ADR-037), parte financeira: o que vai virar problema nos próximos dias, só de tabelas locais (sem rede, sem modelo, sem gravar). Caixa projetado que fica negativo e a receber atrasado há 10 dias ou mais. Veio de gabi/antecipar.py; documentos e atividades saíram no corte do gabi-finance. Consome: dinheiro.projecao, cobrar.a_receber. O resumo da manhã só ganha o bloco quando há alerta.

- **Arquivo:** `gabi/dinheiro/olhar_a_frente.py` (62 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.mcp.ferramentas_dia`
- **Testes:** `tests/dinheiro/test_olhar_a_frente.py`

### `gabi.dinheiro.para_quem_fila`
Rodada única da fila de "para quem": sugestão pendente que hoje passa no critério certeiro (classificar.para_quem_certeiro) é aplicada e fechada ("aplicada sozinha"); a de lançamento que a Gabi já preencheu com a mesma pessoa também fecha; as demais seguem pendentes (ADR-023). Idempotente: só olha pendentes. Consome: sugestao, lancamento.

- **Arquivo:** `gabi/dinheiro/para_quem_fila.py` (23 linhas)
- **Lê:** `lancamento`
- **Grava:** `sugestao`
- **Chamado por:** `gabi.dinheiro.rodar`
- **Testes:** `tests/dinheiro/test_para_quem_certeiro.py`

### `gabi.dinheiro.planilha`
Validação das abas de compromissos (Compromissos, Parâmetros, Valores do mês). Portado do gabi-fin/planilha.py SEM alterar a lógica.

- **Arquivo:** `gabi/dinheiro/planilha.py` (300 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.dinheiro.despesas`, `gabi.dinheiro.repositorio`, `gabi.importar`
- **Testes:** `tests/dinheiro/test_golden_planilha.py`

### `gabi.dinheiro.previstas`
Feriados nacionais e dia útil, portados do gabi-fin/previstas.py SEM alterar a lógica.

- **Arquivo:** `gabi/dinheiro/previstas.py` (52 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.dinheiro.compromissos`
- **Testes:** `tests/dinheiro/test_golden_previstas.py`

### `gabi.dinheiro.projecao`
Saldo projetado do caixa, dia a dia: saldo de hoje (contas BANK liberadas) + entradas previstas − saídas previstas. Consome: contas_pagar (caixa_unico, faturas_abertas), cobrar.previsao, db (compromisso, fatura).

- **Arquivo:** `gabi/dinheiro/projecao.py` (60 linhas)
- **Lê:** `compromisso`, `fatura`
- **Grava:** —
- **Chamado por:** `gabi.dinheiro.agenda_financeira`, `gabi.dinheiro.olhar_a_frente`, `gabi.rotas.dinheiro`
- **Testes:** `tests/dinheiro/test_projecao.py`

### `gabi.dinheiro.regras`
Regras e sugestões (R1): a Gabi sugere; só o Ricardo, ao aprovar, faz uma regra nascer ativa e valer no passado e no futuro.

- **Arquivo:** `gabi/dinheiro/regras.py` (228 linhas)
- **Lê:** —
- **Grava:** `decisao`, `lancamento`, `regra`, `sugestao`
- **Chamado por:** `gabi.dinheiro.classificar`, `gabi.dinheiro.favorecidos`, `gabi.mcp.ferramentas_prop`, `gabi.mcp.ferramentas_ver`, `gabi.rotas.dinheiro`
- **Testes:** `tests/dinheiro/test_condicao.py`, `tests/dinheiro/test_regras.py`, `tests/rotas/test_contagens.py`, `tests/rotas/test_dinheiro_api.py`

### `gabi.dinheiro.repositorio`
Ponte entre o banco e gerar/conciliar. TODO o SQL da conciliação vive aqui.

- **Arquivo:** `gabi/dinheiro/repositorio.py` (242 linhas)
- **Lê:** `categoria`, `conta`, `conta_estado`, `fatura`, `lancamento`, `pessoa`, `saldo`
- **Grava:** `compromisso`, `compromisso_linha`, `conciliacao`, `parametro`, `valor_do_mes`
- **Chamado por:** `gabi.dinheiro.agenda_financeira`, `gabi.dinheiro.contas_pagar`, `gabi.dinheiro.despesas`, `gabi.dinheiro.nao_gasto`, `gabi.dinheiro.rodar`, `gabi.importar`, `gabi.mcp.servidor`, `gabi.rotas.dinheiro`, `gabi.rotas.gastos`
- **Testes:** `tests/dinheiro/cenarios.py`, `tests/dinheiro/test_despesas.py`, `tests/dinheiro/test_golden_analise.py`, `tests/dinheiro/test_pipeline_compromissos.py`, `tests/dinheiro/test_rodar.py`, `tests/rotas/test_cadastros_api.py` …

### `gabi.dinheiro.rodar`
Rodadas do dinheiro: extratos (captura -> conferência -> classificação -> compromissos) e saldos (de hora em hora).

- **Arquivo:** `gabi/dinheiro/rodar.py` (124 linhas)
- **Lê:** `conta`
- **Grava:** —
- **Chamado por:** units `gabi-finance-extratos` e `gabi-finance-saldos` (`python -m gabi.dinheiro.rodar`)
- **Testes:** `tests/dinheiro/test_rodar.py`, `tests/test_deploy.py`

### `gabi.dinheiro.rumo`
Rumo (T4.3): mês a mês, quanto entrou, quanto saiu, quanto sobrou, quanto se gastou (e com quem/em qual frente) e qual é o patrimônio. Só SQL, sem DuckDB (ADR-004). - entradas/saídas/poupança: lançamentos de natureza 'caixa' (inclui 'caixa+custo') das contas LIBERADAS (estado 'sim'), como o caixa único. - gasto: `natureza like '%custo%'`, a mesma definição da tela Gastos (consultas.custos), por pessoa (`para_quem`) e por frente. - patrimônio: soma do último saldo de cada conta BANK liberada até o fim do mês; None enquanto não houver nenhum saldo. Valores em centavos inteiros (R7). Consome: lancamento, conta, saldo.

- **Arquivo:** `gabi/dinheiro/rumo.py` (46 linhas)
- **Lê:** `conta`, `lancamento`, `saldo`
- **Grava:** —
- **Chamado por:** `gabi.rotas.gastos`
- **Testes:** `tests/dinheiro/test_rumo.py`

### `gabi.dinheiro.sugestoes_agenda`
Transforma evento de agenda que se repete todo mês no mesmo dia e fala de pagar em PERGUNTA do canal de decisão. Lê `agenda_evento` e `agenda_fonte`, que **ficam congeladas** na cópia do banco (nada mais as alimenta depois do corte): as sugestões de agenda financeira degradam até a etapa 3 decidir uma fonte. Ver `docs/operacao.md`.

- **Arquivo:** `gabi/dinheiro/sugestoes_agenda.py` (68 linhas)
- **Lê:** `agenda_evento`, `agenda_fonte`, `compromisso_linha`, `conta`, `pergunta`
- **Grava:** —
- **Chamado por:** `gabi.dinheiro.rodar`
- **Testes:** `tests/dinheiro/test_sugestoes_agenda.py`

### `gabi.dinheiro.sugestoes_dono`
Pergunta de dono (D5): fornecedor com gasto sem "para quem" vira pergunta no canal de decisão, um fornecedor por vez, até `MAX_ABERTAS` abertas. R1: só pergunta; o Ricardo escolhe a pessoa (ou deixa para depois). Resposta preenche SÓ os lançamentos ainda sem dono, com origem 'voce'. As opções são as pessoas mais usadas nos lançamentos já classificados (nada chumbado). Consome: lancamento, conta, pessoa, decisoes.

- **Arquivo:** `gabi/dinheiro/sugestoes_dono.py` (47 linhas)
- **Lê:** `conta`, `lancamento`, `pergunta`, `pessoa`
- **Grava:** —
- **Chamado por:** `gabi.dinheiro.rodar`
- **Testes:** `tests/dinheiro/test_sugestoes_dono.py`

### `gabi.dinheiro.valor`
Dinheiro em centavos inteiros (R7): nunca float no banco; na API, string decimal "1234.56". Consome: nada.

- **Arquivo:** `gabi/dinheiro/valor.py` (48 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.avisos`, `gabi.cobrar.receber_manual`, `gabi.dia`, `gabi.dinheiro.captura`, `gabi.dinheiro.compromissos`, `gabi.dinheiro.consultas`, `gabi.dinheiro.contas_pagar`, `gabi.dinheiro.despesas`, `gabi.dinheiro.moeda`, `gabi.dinheiro.repositorio`, `gabi.mcp.ferramentas_agir`, `gabi.mcp.ferramentas_despesas`, `gabi.mcp.ferramentas_ver`, `gabi.mcp.servidor`, `gabi.rotas.cadastros`, `gabi.rotas.cobrar`, `gabi.rotas.dinheiro`, `gabi.rotas.gastos`
- **Testes:** `tests/dinheiro/cenarios.py`, `tests/dinheiro/test_golden_analise.py`, `tests/dinheiro/test_valor.py`, `tests/rotas/test_gastos_api.py`

## A receber (`gabi/cobrar`)

### `gabi.cobrar`
Pacote do que a Gabi tem a receber: notas fiscais (Nibo), previsão de entradas, recebimentos e valores a receber ditados pelo Ricardo.

- **Arquivo:** `gabi/cobrar/__init__.py` (0 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** — (pacote: os módulos dele são importados pelo nome completo)
- **Testes:** os testes dos módulos do pacote

### `gabi.cobrar.a_receber`
A receber no mês e se já entrou: uma só consulta, SEM rede, SÓ leitura (R1/R2). Consome: dinheiro.esperados, db (nota_fiscal, recebimento_nota, receber_manual).

- **Arquivo:** `gabi/cobrar/a_receber.py` (91 linhas)
- **Lê:** `conta`, `lancamento`, `nota_fiscal`, `receber_manual`, `receber_manual_proposta`, `recebimento_nota`
- **Grava:** —
- **Chamado por:** `gabi.dinheiro.olhar_a_frente`, `gabi.mcp.ferramentas_ver`, `gabi.rotas.cobrar`
- **Testes:** `tests/cobrar/test_receber_manual.py`

### `gabi.cobrar.cadastro`
Leitura dos cadastros de empresa que a cobrança usa (relação: contratante, pj_titular ou outra; e-mail de cobrança). Só leitura.

- **Arquivo:** `gabi/cobrar/cadastro.py` (18 linhas)
- **Lê:** `empresa`
- **Grava:** —
- **Chamado por:** nenhum módulo de `gabi/` o importa hoje (só o teste o usa)
- **Testes:** `tests/cobrar/test_nibo.py`

### `gabi.cobrar.notas`
Histórico das NFS-e emitidas (fonte: Nibo, só leitura). Grava metadados em `nota_fiscal` e guarda PDF/XML em pasta própria.

- **Arquivo:** `gabi/cobrar/notas.py` (107 linhas)
- **Lê:** —
- **Grava:** `nota_fiscal`
- **Chamado por:** `gabi.cobrar.notas_importar`
- **Testes:** `tests/cobrar/test_notas.py`

### `gabi.cobrar.notas_importar`
Importa as NFS-e do Nibo para `nota_fiscal` e guarda PDF/XML em /var/lib/gabi-finance/notas. Uso: python -m gabi.cobrar.notas_importar [--desde AAAA-MM-DD]. O Nibo é lido pela ponte (GABI_FONTES_SOCKET): este processo não tem o token (R5). Consome: cobrar.notas, rodada, fontes.ambiente.

- **Arquivo:** `gabi/cobrar/notas_importar.py` (46 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** unit `gabi-finance-notas` (`python -m gabi.cobrar.notas_importar`)
- **Testes:** `tests/cobrar/test_notas_importar.py`

### `gabi.cobrar.previsao`
Previsão de caixa (entradas) a partir das NFS-e importadas do Nibo. Consome: db (nota_fiscal).

- **Arquivo:** `gabi/cobrar/previsao.py` (83 linhas)
- **Lê:** `nota_fiscal`, `recebimento_nota`
- **Grava:** —
- **Chamado por:** `gabi.dinheiro.projecao`, `gabi.rotas.cobrar`
- **Testes:** `tests/cobrar/test_previsao.py`, `tests/cobrar/test_recebimentos.py`

### `gabi.cobrar.receber_manual`
A receber manual: valor que o Ricardo diz no chat (ou no painel) que vai receber, fora das notas. Consome: dinheiro.valor, db, cobrar.util, cobrar.recebimentos (_norm).

- **Arquivo:** `gabi/cobrar/receber_manual.py` (157 linhas)
- **Lê:** `conta`, `lancamento`
- **Grava:** `decisao`, `receber_manual`, `receber_manual_proposta`, `recebimento_nota`
- **Chamado por:** `gabi.dinheiro.rodar`, `gabi.mcp.ferramentas_agir`, `gabi.mcp.ferramentas_despesas`, `gabi.rotas.cobrar`
- **Testes:** `tests/cobrar/test_receber_manual.py`, `tests/cobrar/test_recebimentos.py`, `tests/mcp/test_ver.py`, `tests/rotas/test_cobrar_api.py`

### `gabi.cobrar.recebimentos`
Casamento de recebimentos: crédito em conta BANK liberada no caixa único com o valor LÍQUIDO de uma NFS-e autorizada. Consome: db (nota_fiscal, lancamento, conta, recebimento_nota).

- **Arquivo:** `gabi/cobrar/recebimentos.py` (77 linhas)
- **Lê:** `conta`, `lancamento`, `nota_fiscal`, `receber_manual`
- **Grava:** `decisao`, `receber_manual_proposta`, `recebimento_nota`
- **Chamado por:** `gabi.cobrar.receber_manual`, `gabi.dinheiro.rodar`, `gabi.rotas.cobrar`
- **Testes:** `tests/cobrar/test_receber_manual.py`, `tests/cobrar/test_recebimentos.py`, `tests/cobrar/test_util.py`, `tests/rotas/test_cobrar_api.py`

### `gabi.cobrar.util`
Formatação e relógio compartilhados pelos módulos de gabi/cobrar.

- **Arquivo:** `gabi/cobrar/util.py` (10 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.cobrar.receber_manual`, `gabi.cobrar.recebimentos`
- **Testes:** `tests/cobrar/test_util.py`

## Fontes e ponte (`gabi/fontes`)

### `gabi.fontes`
Pacote dos clientes das fontes externas (mcp.ai e Nibo) e da ponte que isola o token do Nibo.

- **Arquivo:** `gabi/fontes/__init__.py` (0 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** — (pacote: os módulos dele são importados pelo nome completo)
- **Testes:** os testes dos módulos do pacote

### `gabi.fontes._http`
HTTP mínimo compartilhado pelos clientes novos: (metodo, url, corpo, cabecalhos) -> (status, json). Nunca registra cabeçalhos (R5).

- **Arquivo:** `gabi/fontes/_http.py` (56 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.fontes.mcpai`, `gabi.fontes.nibo`, `gabi.fontes.nibo_escrita`
- **Testes:** `tests/conftest.py`, `tests/fontes/test_http.py`

### `gabi.fontes.ambiente`
Fábricas das fontes externas a partir do ambiente (R5: só variáveis de ambiente; nenhuma credencial no código ou no banco). `None` = fonte não configurada (a API responde 503 `fonte_indisponivel`). Consome: fontes.nibo_escrita, fontes.ponte.

- **Arquivo:** `gabi/fontes/ambiente.py` (17 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.api`, `gabi.cobrar.notas_importar`, `gabi.fontes.servico`
- **Testes:** `tests/fontes/test_ponte.py`

### `gabi.fontes.mcpai`
Cliente REST da mcp.ai (Open Finance, Pluggy): só leitura. Docs: docs/fontes/mcpai.md.

- **Arquivo:** `gabi/fontes/mcpai.py` (132 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.dinheiro.rodar`
- **Testes:** `tests/fontes/test_mcpai.py`

### `gabi.fontes.nibo`
Cliente REST do Nibo (API Empresa), SOMENTE LEITURA. Docs: docs/fontes/nibo.md.

- **Arquivo:** `gabi/fontes/nibo.py` (129 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.cobrar.notas_importar`, `gabi.fontes.nibo_escrita`, `gabi.fontes.ponte`
- **Testes:** `tests/cobrar/test_nibo.py`, `tests/cobrar/test_notas_importar.py`, `tests/fontes/test_ponte.py`

### `gabi.fontes.nibo_escrita`
Subclasse do cliente do Nibo que a fábrica `fontes.ambiente` instancia como a fonte `nibo`. A ponte só deixa passar métodos de leitura (R2); a classe fica porque trocar por `Nibo` mudaria comportamento financeiro (decisão da Task 1 do corte).

- **Arquivo:** `gabi/fontes/nibo_escrita.py` (67 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.fontes.ambiente`
- **Testes:** `tests/cobrar/test_nibo.py`, `tests/cobrar/test_nibo_escrita.py`

### `gabi.fontes.ponte`
Ponte Unix entre a API/MCP (sem rede) e o serviço de fontes (com rede, dono do token do Nibo). Uma requisição por conexão: JSON de uma linha {"fonte", "metodo", "args", "kwargs"} -> {"ok": valor} | {"erro": {"tipo", "msg"}}. `bytes` viaja como {"__b64__": ...}. Só métodos da lista branca; `preparar_usuario` (token admin) nunca atravessa a ponte. R5: nenhum token ou cabeçalho trafega aqui; o servidor devolve só o tipo e a mensagem do erro. Consome: fontes.nibo.

- **Arquivo:** `gabi/fontes/ponte.py` (137 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.fontes.ambiente`, `gabi.fontes.servico`
- **Testes:** `tests/cobrar/test_nibo.py`, `tests/fontes/test_ponte.py`

### `gabi.fontes.servico`
Serviço de fontes: único processo com rede e token do Nibo (arquivo de ambiente, R5). A API e o MCP (sem rede) falam com ele pelo socket Unix da ponte. Uso: python -m gabi.fontes.servico --socket CAMINHO.

- **Arquivo:** `gabi/fontes/servico.py` (22 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** unit `gabi-finance-fontes` (`python -m gabi.fontes.servico`)
- **Testes:** `tests/test_deploy.py`

## Servidor MCP (`gabi/mcp`)

### `gabi.mcp`
Pacote do servidor MCP (as ferramentas que o Hermes e outros agentes chamam).

- **Arquivo:** `gabi/mcp/__init__.py` (0 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** — (pacote: os módulos dele são importados pelo nome completo)
- **Testes:** os testes dos módulos do pacote

### `gabi.mcp.ferramentas_agir`
Ferramentas MCP de escrita direta que o Ricardo pede no chat (Onda 3), só as financeiras: a receber manual, marcar gasto, assinaturas, quem gastou e reembolso. Só a pedido explícito dele; nunca a partir de texto de terceiros (R14). A `decisao` leva só contagem ou id. Consome: cobrar.receber_manual, dinheiro.{gastador,nao_gasto}.

- **Arquivo:** `gabi/mcp/ferramentas_agir.py` (206 linhas)
- **Lê:** `empresa`, `pessoa`
- **Grava:** `assinatura`, `decisao`, `lancamento`
- **Chamado por:** `gabi.mcp.servidor`
- **Testes:** `tests/mcp/test_agir.py`

### `gabi.mcp.ferramentas_dec`
Ferramentas MCP do canal de decisão (escopo `decisoes`): listar perguntas abertas e registrar a resposta do Ricardo. R1: a única escrita é gravar a escolha que ele deu (um número) numa pergunta que a própria Gabi criou; o efeito vem da lista fechada de gabi.decisoes e não existe ferramenta para criar pergunta nem para escolher efeito pelo canal. Texto de terceiros nunca vira opção. Consome: decisoes.

- **Arquivo:** `gabi/mcp/ferramentas_dec.py` (26 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.mcp.servidor`
- **Testes:** `tests/mcp/test_decisoes_canal.py`

### `gabi.mcp.ferramentas_despesas`
Ferramentas MCP de despesas fixas e avulsas (ADR-032): listar, criar, mudar daqui em diante, mexer num mês (valor, data, dispensar), encerrar e excluir. Só a pedido explícito do Ricardo no chat, depois de mostrar o que muda e ouvir o sim; nunca a partir de texto de e-mail, Teams ou documento (R14). As regras moram em `dinheiro.despesas` (`quem` e `origem` 'hermes'); aqui só a resolução do nome, o valor ditado e o `desfazer`. Não existe reabrir despesa encerrada: para voltar, cria de novo. Consome: dinheiro.despesas, cobrar.receber_manual (valor_ditado).

- **Arquivo:** `gabi/mcp/ferramentas_despesas.py` (185 linhas)
- **Lê:** `compromisso`
- **Grava:** —
- **Chamado por:** `gabi.mcp.servidor`
- **Testes:** `tests/mcp/test_despesas_mcp.py`

### `gabi.mcp.ferramentas_dia`
Ferramentas MCP do dia: o resumo da manhã financeiro (escopo `trabalho`) e o `olhar_a_frente` financeiro (escopo `fin`). SÓ LEITURA; nenhuma ferramenta envia, apaga ou confirma (R1/R2/R14). Consome: dinheiro.agenda_financeira, dinheiro.olhar_a_frente, decisoes, envelope; recebe `executar` do servidor. Agenda e e-mail saíram no corte do gabi-finance.

- **Arquivo:** `gabi/mcp/ferramentas_dia.py` (63 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.mcp.ferramentas_ver`, `gabi.mcp.servidor`
- **Testes:** `tests/dinheiro/test_olhar_a_frente.py`, `tests/mcp/test_dia.py`

### `gabi.mcp.ferramentas_prop`
Ferramentas MCP de PROPOSTAS financeiras (só criam sugestão) e o `ErroFerramenta` comum às ferramentas.

- **Arquivo:** `gabi/mcp/ferramentas_prop.py` (42 linhas)
- **Lê:** `lancamento`
- **Grava:** —
- **Chamado por:** `gabi.mcp.ferramentas_agir`, `gabi.mcp.ferramentas_dec`, `gabi.mcp.ferramentas_despesas`, `gabi.mcp.servidor`
- **Testes:** `tests/mcp/test_propostas.py`

### `gabi.mcp.ferramentas_ver`
Ferramentas MCP de leitura da Onda 2, só as financeiras: a receber, avisos, regras, decisões e empresas. Só leitura; nada é escrito além de `chamada_mcp`.

- **Arquivo:** `gabi/mcp/ferramentas_ver.py` (134 linhas)
- **Lê:** `aviso`, `decisao`, `empresa`, `regra`
- **Grava:** —
- **Chamado por:** `gabi.mcp.servidor`
- **Testes:** `tests/mcp/test_ver.py`

### `gabi.mcp.servidor`
Servidor MCP do gabi-finance (Streamable HTTP, sem estado): ferramentas financeiras, por token com escopo.

- **Arquivo:** `gabi/mcp/servidor.py` (264 linhas)
- **Lê:** —
- **Grava:** `chamada_mcp`
- **Chamado por:** `gabi.agentes`
- **Testes:** `tests/mcp/test_agir.py`, `tests/mcp/test_confiabilidade.py`, `tests/mcp/test_decisoes_canal.py`, `tests/mcp/test_despesas_mcp.py`, `tests/mcp/test_dia.py`, `tests/mcp/test_fabrica.py` …

### `gabi.mcp.tokens`
Tokens de agentes do MCP: o token aparece UMA vez (ao emitir); o banco guarda só o SHA-256. Escopos limitam as ferramentas.

- **Arquivo:** `gabi/mcp/tokens.py` (89 linhas)
- **Lê:** —
- **Grava:** `token_agente`
- **Chamado por:** `gabi.agentes`, `gabi.mcp.servidor`
- **Testes:** `tests/mcp/test_agir.py`, `tests/mcp/test_confiabilidade.py`, `tests/mcp/test_decisoes_canal.py`, `tests/mcp/test_despesas_mcp.py`, `tests/mcp/test_olhar_a_frente_mcp.py`, `tests/mcp/test_propostas.py` …

## Rotas HTTP (`gabi/rotas`)

### `gabi.rotas`
Pacote das rotas HTTP `/api/v1/*` que o painel usa. Todas são montadas por `gabi/api.py`.

- **Arquivo:** `gabi/rotas/__init__.py` (0 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** — (pacote: os módulos dele são importados pelo nome completo)
- **Testes:** os testes dos módulos do pacote

### `gabi.rotas.agentes`
Agentes externos (/api/v1/agentes, ADR-036): chaves do MCP — listar, criar, trocar escopos, revogar, rotacionar, chamadas e dados de conexão.

- **Arquivo:** `gabi/rotas/agentes.py` (94 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.api`
- **Testes:** `tests/rotas/test_agentes_api.py`

### `gabi.rotas.avisos`
Avisos para o Ricardo (/api/v1/avisos): o que o produtor (gabi/avisos.py) gravou e ainda não foi lido. Só o boss. Título e texto saem do servidor em pt-BR, para o painel e o canal mostrarem a mesma coisa. Consome: aviso, decisao.

- **Arquivo:** `gabi/rotas/avisos.py` (106 linhas)
- **Lê:** —
- **Grava:** `aviso`, `decisao`
- **Chamado por:** `gabi.api`, `gabi.mcp.ferramentas_ver`, `gabi.telegram`
- **Testes:** `tests/dinheiro/test_moeda.py`, `tests/mcp/test_ver.py`, `tests/rotas/test_avisos_api.py`, `tests/test_avisos.py`, `tests/test_avisos_antecipados.py`

### `gabi.rotas.cadastros`
Cadastros (/api/v1/cadastros/{tipo}): empresas, contas, pessoas, compromissos e categorias (+ equivalência de categorias).

- **Arquivo:** `gabi/rotas/cadastros.py` (564 linhas)
- **Lê:** `lancamento`, `pessoa`
- **Grava:** `categoria`, `compromisso_linha`, `conta`, `decisao`, `equivalencia_categoria`, `parametro`
- **Chamado por:** `gabi.api`, `gabi.decisoes`
- **Testes:** `tests/rotas/test_cadastros_api.py`

### `gabi.rotas.cobrar`
Rotas de Cobrar: o que vou receber (previsão, notas, a receber, recebimentos). Só o Ricardo (boss). Nada é enviado (R2). Reembolso PJ, lote do Nibo, comprovantes, rascunho de cobrança e pedidos saíram (ADR-023). Consome: cobrar.*.

- **Arquivo:** `gabi/rotas/cobrar.py` (156 linhas)
- **Lê:** `lancamento`, `nota_fiscal`, `recebimento_nota`
- **Grava:** —
- **Chamado por:** `gabi.api`
- **Testes:** `tests/rotas/test_cobrar_api.py`

### `gabi.rotas.contagens`
Contadores do sino e do menu do painel: quantos itens pedem uma decisão do Ricardo, por área. Reusa as consultas das próprias telas (sem SQL novo), para o número nunca divergir da lista. Consome sugestao, contas_pagar, cartões, assinaturas e lançamentos a indicar (quem gastou).

- **Arquivo:** `gabi/rotas/contagens.py` (32 linhas)
- **Lê:** `aviso`, `conta`, `lancamento`, `sugestao`
- **Grava:** —
- **Chamado por:** `gabi.api`
- **Testes:** `tests/rotas/test_dinheiro_api.py`

### `gabi.rotas.decisoes`
Canal de decisão (/api/v1/decisoes): criar e listar perguntas com opções numeradas. Só o boss. Quem responde é o Ricardo, pelo canal (ferramenta MCP `decisao_responder`); a API só cria a pergunta e deixa ler o estado. Consome: decisoes.

- **Arquivo:** `gabi/rotas/decisoes.py` (37 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.api`
- **Testes:** `tests/mcp/test_decisoes_canal.py`

### `gabi.rotas.despesas`
Despesas (/api/v1/despesas): criar fixa ou avulsa, mudar daqui em diante, mexer num mês, dispensar, encerrar e excluir.

- **Arquivo:** `gabi/rotas/despesas.py` (125 linhas)
- **Lê:** —
- **Grava:** —
- **Chamado por:** `gabi.api`
- **Testes:** `tests/rotas/test_dinheiro_api.py`

### `gabi.rotas.dinheiro`
Rotas /api/v1 da Fase 1 (Dinheiro): caixa, contas a pagar, lançamentos, sugestões, regras, fontes. Só boss (Fase 4 abre por matriz).

- **Arquivo:** `gabi/rotas/dinheiro.py` (435 linhas)
- **Lê:** `compromisso`, `conferencia`, `conta`, `pessoa`, `regra`, `rodada`, `saldo`, `sugestao`
- **Grava:** `lancamento`
- **Chamado por:** `gabi.api`, `gabi.mcp.ferramentas_ver`, `gabi.mcp.servidor`, `gabi.rotas.agentes`, `gabi.rotas.avisos`, `gabi.rotas.cadastros`, `gabi.rotas.cobrar`, `gabi.rotas.contagens`, `gabi.rotas.decisoes`, `gabi.rotas.despesas`, `gabi.rotas.gastos`
- **Testes:** `tests/rotas/test_dinheiro_api.py`

### `gabi.rotas.gastos`
Rotas /api/v1 de análise de gastos: semanas, destino (para onde vai), cartões, parcelas, assinaturas e custo do modelo.

- **Arquivo:** `gabi/rotas/gastos.py` (338 linhas)
- **Lê:** `categoria`, `conta`, `fatura`, `lancamento`, `parametro`, `saldo`
- **Grava:** `assinatura`
- **Chamado por:** `gabi.api`, `gabi.rotas.contagens`, `gabi.rotas.dinheiro`
- **Testes:** `tests/rotas/test_gastos_api.py`

