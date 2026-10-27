# Atividades: recado ao Hermes vira to-do com aviso

Data: 27/10/2026 · Estado: desenho aprovado pelo Ricardo em 27/10 (conversa) · ADR a criar: 033

## O que o Ricardo disse
- Quer um to-do pessoal: deixa um recado num canal e o Hermes cria uma atividade.
- Depois de criada: lista no painel **mais aviso** no Telegram (decisão B).
- O recado é uma mensagem normal ao Hermes, no Telegram ou no WhatsApp, sem canal novo (decisão A).
- Avisos: no horário dito, uma vez de manhã no dia do vencimento, e um resumo diário com tudo que está aberto, inclusive o sem data (decisão B). Sem insistência diária.

## Fora do escopo (de propósito)
Google Tasks, Microsoft To Do e Linear; atividades recorrentes; insistir todo dia em atividade vencida; reaproveitar o módulo Trabalho (cortado na ADR-023) e a tabela `tarefa` da migração 0015.

## Modelo (migração 0086)
`atividade(id, texto not null, vence_em text null, tem_hora int not null default 0, status text not null default 'aberta' check (status in ('aberta','feita','cancelada')), origem text not null, criada_em, concluida_em null)`.
- `vence_em`: ISO em UTC; `tem_hora=0` significa "o dia todo" (guarda o dia de Brasília às 00:00 BRT).
- `origem`: `hermes` ou `painel` (a ferramenta do MCP não sabe se o recado veio do Telegram ou do WhatsApp).
- Sem tabela de avisos nova: reaproveita `aviso` (ver abaixo).

## Regras (`gabi/atividades.py`, novo; usado pela API e pelo MCP)
- `criar(...)`: texto não vazio (até 500 caracteres); data no passado é recusada com mensagem clara (o Hermes pergunta). Se já existe atividade **aberta** com o mesmo texto e o mesmo vencimento, devolve a existente com `ja_existia: true` (o Hermes repetir a chamada depois de um erro não duplica).
- `listar(con, status='aberta')`: vencidas primeiro, depois por vencimento, sem data por último.
- `concluir`, `cancelar` (só de `aberta`; idempotentes), `adiar(con, id, vence_em, tem_hora)`: reabre o aviso do novo horário.
- Data vaga ("semana que vem"): o Hermes escolhe a segunda-feira e diz qual escolheu; a ferramenta só recebe data resolvida. Fuso: America/Sao_Paulo.
- Toda mudança grava linha em `decisao` (padrão das outras ferramentas de escrita).

## Avisos (reuso de `gabi/avisos.py` + `gabi/telegram.py`)
O produtor já roda a cada 15 min (`gabi-brain-avisos.timer`) e o Telegram entrega o que ele grava. Entram três tipos novos, um aviso por (tipo, chave) por dia (regra existente):
- `atividade_hora`: atividade com hora que chegou ao horário (precisão de até 15 min, a cadência do timer). Chave = id + vencimento.
- `atividade_hoje`: atividade com vencimento hoje, no 1º ciclo depois das 07:00 BRT. Chave = id.
- `atividade_resumo`: um por dia, no 1º ciclo depois das 07:00 BRT, listando vencidas, vencem hoje e abertas sem data (até 15 linhas, "e mais N"). Não sai se não houver nada aberto.
- Texto em pt-BR em `rotas/avisos.descrever`; payload leva só o texto da atividade e datas.
- Aviso obsoleto (atividade já feita, cancelada ou adiada) fecha sem enviar, como `triar` já faz para os outros tipos.
- O WhatsApp não recebe aviso (hoje só o Telegram entrega).

## Hermes
Cinco ferramentas no MCP: `atividade_criar`, `atividade_listar`, `atividade_concluir`, `atividade_adiar`, `atividade_cancelar`.
- Criar não pede confirmação antes (reversível); confirma numa linha com a data que entendeu.
- Escopo novo no token do Hermes (`atividades`); entram no include do `config.yaml` e no SOUL (frase curta: recado de lembrete ou tarefa vira atividade; nunca "a Gabi cria").
- Runbook `#atividades`: backup do banco e do `config.yaml`, instalar, include, SOUL, restart do `hermes-gateway`, `/new` no Telegram e no WhatsApp.

## API e painel
- `GET /api/v1/atividades?status=`, `POST /atividades`, `POST /atividades/{id}/concluir|cancelar`, `PATCH /atividades/{id}` (adiar).
- Tela **Atividades** (grupo Dia, logo depois de Envios): lista agrupada em Vencidas, Hoje, Próximas, Sem data; campo para nova atividade; botões feita, adiar (hoje, amanhã, escolher data) e excluir (cancelar). Segue a navegação e o tema atuais; sem gráficos.

## Erros e segurança
- Texto da atividade é dado do Ricardo: nunca mascarado (privacidade é dele), mas nunca vai para log.
- Falha de entrega do Telegram: o mecanismo atual reavalia na rodada seguinte, dentro da janela de 2 dias.
- A ferramenta recusa texto vazio, data passada sem hora explícita e id inexistente, com mensagem que o Hermes repete ao Ricardo.

## Testes (primeiro)
Modelo e regras (criar, listar, ordem, concluir, adiar, idempotência); produtor de avisos com relógio injetado (antes e depois do horário, 07:00 BRT, dedupe do dia, obsoleto); `descrever`; rotas; ferramentas MCP e escopo do token; painel (vitest) para a tela. Meta: verde no `pytest -q` e no `npx vitest run && npm run build`.

## Entrega
Branch `feat/atividades`, ADR-033, BACKLOG (item novo), runbook `#atividades`. Nada é mergeado nem instalado sem o ok explícito do Ricardo.
