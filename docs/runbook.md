# gabi.brain · Runbook
Convenção: `BANCO=/var/lib/gabi-brain/gabi.db`. Comandos como usuário `gabibrain` (`sudo -u gabibrain …`) e `PY=/opt/gabi-brain/venv/bin/python`.

## Subir e parar
- Status: `systemctl is-active gabi-brain-api` → `active`.
- Reiniciar: `sudo systemctl restart gabi-brain-api`. Parar: `sudo systemctl stop gabi-brain-api`.
- Logs: `journalctl -u gabi-brain-api -n 50 --no-pager`.
- Porta: `ss -ltn | grep 8080` → só `127.0.0.1:8080`. Se aparecer `0.0.0.0:8080`, **pare o serviço** e investigue.

## Acesso (quem entra)
- Listar: `$PY -m gabi.acesso --banco $BANCO listar`.
- Adicionar: `$PY -m gabi.acesso --banco $BANCO adicionar <login-tailscale> <pessoa_id> boss|familia_vip|terceiros`.
- Remover acesso: apagar a linha de `acesso` (sqlite3) e conferir `listar`. Sem login em `acesso`, a pessoa recebe 403.

## Revogar tudo (tokens de agentes)
- `curl -X POST http://127.0.0.1:8080/api/revogar-tudo -H 'Tailscale-User-Login: <seu-login>' -H 'Content-Type: application/json' -d '{"confirmo": true}'` → `{"revogados": N}`. Sem `confirmo: true` → 400 e nada muda.

## Carregar o staging
- `$PY -m gabi.importar --banco $BANCO --staging /home/ricardo/gabi-brain-migracao/staging` → imprime contagens. Pode rodar de novo: não duplica. Registra uma rodada `importacao-staging`.

## Backup e restauração
- Diário 03:30 (`gabi-brain-backup.timer`), com teste de restauração. À mão: `$PY -m gabi.backup --banco $BANCO --destino /var/backups/gabi-brain --testar`.
- Resultado: `gabi-brain-AAAA-MM-DD.sqlite` (600) e uma rodada `backup`. Falha de integridade → rodada `erro` e código de saída 1.
- **Restaurar:** `sudo systemctl stop gabi-brain-api`; copiar o backup desejado para `$BANCO`; apagar `gabi.db-wal` e `gabi.db-shm`; `sudo systemctl start gabi-brain-api`; conferir `/api/saude`.
- Cópia fora da VPS: puxar `/var/backups/gabi-brain/*.sqlite` para a máquina local com `scp` (a VPS não guarda a única cópia).

## Alertas
| Sinal | Significa | Ação |
|---|---|---|
| `/api/saude` com `db != "ok"` | banco corrompido | parar a API e restaurar o último backup |
| rodada `backup` com `status=erro` | backup ou restauração falhou | rodar à mão com `--testar` e ler a mensagem |
| `ultimo_backup` nulo ou com mais de 2 dias | timer parado | `systemctl status gabi-brain-backup.timer` |
| 403 para alguém que deveria entrar | login fora de `acesso` | `gabi.acesso adicionar` |

## Verificação dos comandos (08/10/2026, banco temporário)
`importar` 2× → 18 novas, depois 0 · `acesso adicionar/listar` ok (login normalizado em minúsculas) · `backup --testar` → arquivo 600 e contagens iguais às da origem · 2º backup no mesmo dia → "FALHOU", código 1 · rodadas `importacao-staging` e `backup` gravadas. Os comandos de `systemctl`, `ss` e `tailscale` só são verificados após a implantação (T0.8).
