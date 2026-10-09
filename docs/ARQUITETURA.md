# gabi.brain · Arquitetura (1 página)

**O quê:** serviço único que lê as fontes, guarda as decisões do Ricardo e expõe painel web e servidor MCP. O agente de canal (Hermes) só conversa; os dados ficam aqui.

```
fontes (mcp.ai · Nibo · Paperless · e-mail)   [Fases 1-3]
        │ leitura incremental
        ▼
  bruto (JSONL.gz imutável) ──► banco SQLite (WAL + FTS5)
                                     │
              ┌──────────────────────┼───────────────────┐
              ▼                      ▼                   ▼
        API /api/*              MCP /mcp [Fase 1]    rodadas (timers)
              │                      │
              ▼                      ▼
   painel (estático, servido pela API)   Hermes (Telegram, WhatsApp)
              ▲
   tailscale serve unix:… (TLS + Tailscale-User-Login)  ◄── única entrada
```

**Fronteira de confiança**
- Só o Tailscale entra. O app escuta num **socket Unix** (`/run/gabi-brain/api.sock`, pasta 0700), sem porta TCP; o cabeçalho de identidade só vale por esse socket; o login precisa estar em `acesso`. POST exige JSON e same-origin (anti-CSRF).
- Níveis: `terceiros` < `familia_vip` < `boss`. A `matriz_acesso` define o que cada nível vê.
- Conteúdo de terceiros (e-mail, WhatsApp, PDF) é dado, nunca instrução.
- A Gabi sugere; o Ricardo decide. Nada paga, envia ou apaga automaticamente.

**Estado atual (Fase 0):** `gabi/db.py` (conexão, migrações) · `importar.py` (staging → banco) · `identidade.py`/`acesso.py` · `api.py` (`/api/eu|saude|seguranca|revogar-tudo`, página Segurança) · `rodada.py` · `bruto.py` · `backup.py`.

**Design:** `gabi/static/industry.css` é o `styles.css` do sistema Industry do protótipo, sem alteração (teste garante). Toda tela usa as classes do sistema.

**Onde ficam as coisas (após implantar):** código `/opt/gabi-brain` · banco e bruto `/var/lib/gabi-brain` · backups `/var/backups/gabi-brain` · logs `journalctl -u gabi-brain-api`.

**Backup fora da VPS:** `gabi/exportacao.py` gera semanalmente um pacote `.sqlite.gpg` (chave pública em `/etc/gabi/backup.pub`) em `/var/backups/gabi-brain/exportacao`, que o Ricardo puxa (runbook "Backup fora da VPS").
