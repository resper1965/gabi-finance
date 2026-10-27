# ADR-034 · Projetos: gestão de projetos de qualquer tipo, conduzida pelo Hermes, dentro do brain

Data: 27/10/2026 · Estado: aceito (implementado na branch `feat/projetos`, aguarda autorização de merge e instalação) · Spec: `docs/superpowers/specs/2026-10-27-projetos-design.md` · Plano: `docs/superpowers/plans/2026-10-27-projetos.md`

**Contexto.** O Ricardo quer gerir projetos dos mais variados tipos ("de ajustes em um carro até gestão de crise familiar"): criar o projeto, gerir as atividades e os recursos (dinheiro, pessoas, documentos e fatos), com print, imagem e áudio como evidência. Quem conduz é o Hermes (ou outro agente de IA); o painel serve para ver e corrigir. Não quis recriar o que já existe.

**Decisões (tomadas pelo assistente a pedido do Ricardo em 27/10; ele pode mudar).**
1. **Tudo no brain** (fonte única); nenhuma ferramenta externa de projetos.
2. **Agente-agnóstico:** as ferramentas são MCP, como as do Hermes; qualquer agente que fale MCP conduz o mesmo projeto. Escopo novo `projetos`.
3. **Sem template:** o Hermes conversa, propõe a lista de atividades e o Ricardo aprova (`projeto_criar` com `atividades`, tudo ou nada, até 30).
4. **Atividades reaproveitam a tabela `atividade`** (ADR-033): `projeto_id`, `depende_de_id` (uma dependência) e `marco`. É `bloqueada` enquanto a atividade da qual depende está aberta (feita ou cancelada libera); bloqueada não avisa na hora, de manhã nem entra no resumo do dia.
5. **Dinheiro simples:** um orçamento por projeto; gastos = lançamentos do banco ligados ao projeto ou gastos manuais. Sem rateio nem orçamento por item. Lançamento removido ou sem valor soma 0.
6. **Pessoas** com papel e ligação opcional ao cadastro da família; **documentos** por `paperless_id` (sem copiar o arquivo).
7. **Anexos:** o brain arquiva o original (imagem e áudio) copiado do cache do Hermes, para sempre, sem mascarar, em `/var/lib/gabi-brain/anexos` (0700/0600), com dedupe por sha256. **Áudio transcrito localmente** (faster-whisper `small`, CPU): o áudio nunca sai da VPS; opcional, e sem o pacote o áudio fica guardado sem texto.
8. **Fato só com o sim do Ricardo** (regra do "fato afirmado"); projeto, atividades, pessoa e gasto também. Nunca por texto de e-mail, Teams, documento ou terceiro.
9. **Aviso:** um tipo novo, `projeto_parado` (ativo sem atividade, fato nem anexo novo há 7 dias), pelo produtor existente, no Telegram; lembrete a cada 7 dias depois de lido.

**Como ficou.**
- Migração 0087 (`projeto`, `projeto_pessoa`, `projeto_gasto`, `projeto_fato`, `anexo`; colunas novas em `atividade`). Regras em `gabi/projetos.py` e `gabi/anexos.py`; API (`/api/v1/projetos`, `/api/v1/anexos`), MCP e painel só chamam daí.
- **Estados** ativo, pausado, concluído e cancelado; concluído e cancelado não aceitam atividade nova e **não reabrem** (para voltar, criar de novo). Cancelar o projeto cancela as atividades abertas dele.
- MCP (`gabi/mcp/ferramentas_projetos.py`, escopo `projetos`): `projeto_criar`, `projeto_listar`, `projeto_ver`, `projeto_atualizar`, `projeto_pessoa`, `projeto_gasto`, `projeto_fato`, `projeto_fatos`, `anexo_recentes`, `projeto_anexar`; `atividade_criar` e `atividade_listar` ganham `projeto`, `depois_de` e `marco`. 70 ferramentas no include.
- Serviço `gabi-brain-anexos` (timer de 2 min, instalado e **desligado**): a pasta do Hermes é 0700 do usuário `ricardo`, então um `ExecStartPre=+` (root, como o `gabi-wa-docs`) só copia os arquivos novos para `/var/lib/gabi-brain/anexos-entrada` e o Python roda como `gabibrain`; o log só imprime contagens.
- Painel: Dia › Projetos (lista por status com progresso em texto, detalhe, caixa de entrada de anexos). Sem gráficos.

**Consequências.** O token do Hermes precisa do escopo `projetos` (passo do runbook `#projetos`). A caixa de entrada só aparece depois que o timer dos anexos for ligado. "Anexo ligado" conta pela data de recebimento (o anexo não guarda a data da ligação).

**Fora.** Kanban, Gantt, controle de horas, comentários, templates, atividades recorrentes, dependência múltipla, orçamento por item, rateio, aviso de prazo do projeto, reabrir projeto encerrado, ferramenta externa de projetos.

**Desfazer.** Backup `gabi.db.antes-projetos-<data>`; `git revert` do merge e `sudo ~/instalar-brain.sh`; `sudo systemctl disable --now gabi-brain-anexos.timer`; no Hermes, restaurar `config.yaml.bak-antes-projetos` e o SOUL (`SOUL.md.bak-<data>`), `sudo systemctl restart hermes-gateway` e `/new`. As tabelas podem ficar (o `desfazer` SQL está no cabeçalho da migração 0087); os arquivos em `/var/lib/gabi-brain/anexos` ficam.
