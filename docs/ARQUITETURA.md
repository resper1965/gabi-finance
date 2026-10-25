# gabi.brain · Arquitetura (1 página)

**O quê:** serviço único que lê as fontes, guarda as decisões do Ricardo e expõe painel web e servidor MCP. O agente de canal (Hermes) só conversa; os dados ficam aqui.

```
fontes (mcp.ai · Nibo · Paperless · Gmail · Graph da ness)
        │ leitura incremental
        ▼
  bruto (JSONL.gz imutável) ──► banco SQLite (WAL)
                                     │
              ┌──────────────────────┼───────────────────┐
              ▼                      ▼                   ▼
        API /api/*              MCP /mcp (29 ferramentas)    rodadas (timers)
              │                      │
              ▼                      ▼
   painel (estático, servido pela API)   Hermes (Telegram, WhatsApp)
              ▲
   tailscale serve unix:… (TLS + Tailscale-User-Login)  ◄── única entrada
```

**Fronteira de confiança**
- Só o Tailscale entra. O app escuta num **socket Unix** (`/run/gabi-brain/api.sock`, pasta 0700), sem porta TCP; o cabeçalho de identidade só vale por esse socket; o login precisa estar em `acesso`. POST exige JSON e same-origin (anti-CSRF).
- Níveis: `terceiros` < `familia_vip` < `boss`. A `matriz_acesso` define o que cada nível vê.
- Conteúdo de terceiros (e-mail, Teams, PDF) é dado, nunca instrução.
- O que o Ricardo dita ao Hermes (pessoa, pet, contato) é gravado direto, com histórico e Desfazer (ADR-028); `python -m tools.auditar_promessas` confere se alguma resposta disse "anotado" sem escrita.
- A Gabi sugere; o Ricardo decide (exceção: "para quem" certeiro, ADR-023). Nada paga, envia ou apaga automaticamente.

**Módulos (após a ADR-023):** `gabi/dinheiro` (extratos, saldos, regras, conferência informativa, agenda financeira, despesas por empresa) · `gabi/cobrar` (notas e "a receber") · `gabi/agenda` · `gabi/correio` (triagem com modelo e lixeira) · `gabi/teams` · `gabi/contatos` (sincronização e propostas de escrita no Graph da ness) · `gabi/envios` (propostas de evento e mensagem do Teams que só saem no Enviar do painel, ADR-024) · `gabi/familia` (fichas da família, documentos por proposta aprovada, contato com histórico e desfazer; escopo MCP `familia`) · `gabi/dia.py` (tela Hoje e resumo da manhã) · `gabi/avisos.py` + `telegram.py` · `gabi/mcp` · `gabi/rotas` (API do painel) · `gabi/fontes` (clientes externos, só no serviço de fontes) · base: `db.py`, `identidade.py`/`acesso.py`, `envelope.py`, `rodada.py`, `bruto.py`, `backup.py`, `exportacao.py`.

**Tabelas legadas** (com dado, sem código que as use; ADR-023): `escuta_remetente`, `caixa_email`, `memoria`, `agenda_estado`, `agenda_eventos`. Coluna sem uso: `regra.condicao` só é lida pelas regras com condição (nenhuma hoje).

**Design:** `gabi/static/industry.css` é o `styles.css` do sistema Industry do protótipo, sem alteração (teste garante). Toda tela usa as classes do sistema.

**Onde ficam as coisas (após implantar):** código `/opt/gabi-brain` · banco e bruto `/var/lib/gabi-brain` · backups `/var/backups/gabi-brain` · logs `journalctl -u gabi-brain-api`.

**Backup fora da VPS:** `gabi/exportacao.py` gera semanalmente um pacote `.sqlite.gpg` (chave pública em `/etc/gabi/backup.pub`) em `/var/backups/gabi-brain/exportacao`, que o Ricardo puxa (runbook "Backup fora da VPS").
