# ADR-003 · `tailscale serve` no lugar de Cloudflare Access e nginx
- **Contexto:** o handoff previa túnel Cloudflare + JWT. A VPS não tem cloudflared e já tem Tailscale (VPS, Windows, Android).
- **Decisão:** a API escuta em `127.0.0.1:8080`; `tailscale serve` dá TLS e injeta `Tailscale-User-Login`. O app só confia no cabeçalho vindo de `127.0.0.1`/`::1` e exige o login em `acesso`. nginx fica só para o Buzz.
- **Consequência:** nenhuma porta nova aberta (UFW intocado); quem não está no tailnet não alcança o app.
- **Quando reverter:** se o app precisar sair do tailnet (ex.: parceiro externo). Nunca usar `tailscale funnel`.
