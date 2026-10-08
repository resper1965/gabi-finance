# gabi.brain · STATUS (retomada rápida)
Atualizado: 09/10/2026. Se a máquina caiu, leia só este arquivo e `.superpowers/sdd/progress.md`.

## Onde estamos
- **Código da Fase 1 pronto e commitado** (HEAD `5219776`, 629 testes: `.venv/bin/pytest -q`). Nada instalado/ligado na VPS ainda.
- Repos: `/home/ricardo/gabi-brain` (app), `/home/ricardo/gabi-brain-migracao` (export/staging/congelar). Docs: `/home/ricardo/handoff/docs/superpowers/{specs,plans}/` (plano mestre com R1–R17, G1–G14).
- Painel: `painel/` (React). `npm run build` → `gabi/painel/`. Ver sem dado real: `python -m tools.demo 8099` (+ `python -m tools.capturas`, ver `docs/runbook.md#telas-dinheiro`).
- Cuidado: `pkill -f` mata o próprio shell; use PID guardado.

## Esperando o Ricardo (nesta ordem)
1. **G2** aprovar `gabi-brain-migracao/staging/RELATORIO.md`.
2. ~~**G1**~~ **FEITO 09/10/2026** (pacote gpg gerado, baixado e hash conferido, snapshot Contabo). Referência: `sudo bash gabi-brain-migracao/tools/exportar.sh` → scp para a máquina local → conferir hash → snapshot Contabo. Backup na VPS: `/var/backups/gabi-brain-migracao/2026-10-08/`.
3. **G14** aprovar capturas `docs/design/*-{prototipo,app}-*.png`, tela a tela.
4. **G3** login Tailscale (`boss`) + `tailscale serve`; ordem "congelar" dos timers do gabi-fin.
5. **G4** `MCPAI_KEY` em `/etc/gabi/brain.env` → ligar timers de captura. **G5** escolher contas do caixa único.
Depois: instalar (`deploy/instalar.sh`), importar staging, T1.14 (aceite com dados reais).

## Regras que não mudam
Não mexer em segredos (o Ricardo coloca). Nada no claude.ai. Dados nunca chumbados. Só desenvolver/validar com dado real fase a fase.
**Hermes+OpenRouter e desinstalar OpenClaw: SÓ depois de o gabi.brain inteiro terminar.**

## Pendências conhecidas (minors)
Ver `.superpowers/sdd/progress.md` (faixa sem "rodada das 07h", sino sem contador, custo em US$, Fase 2 em diante não iniciada).
