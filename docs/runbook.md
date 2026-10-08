# gabi.brain · Runbook
Convenção: `BANCO=/var/lib/gabi-brain/gabi.db`. Comandos como usuário `gabibrain` (`sudo -u gabibrain …`) e `PY=/opt/gabi-brain/venv/bin/python`.

## Subir e parar
- Status: `systemctl is-active gabi-brain-api` → `active`.
- Reiniciar: `sudo systemctl restart gabi-brain-api`. Parar: `sudo systemctl stop gabi-brain-api`.
- Logs: `journalctl -u gabi-brain-api -n 50 --no-pager`.
- Socket: `ls -ld /run/gabi-brain` → `drwx------ gabibrain`; `ss -ltn | grep 8080` → **vazio** (não há porta TCP). Se aparecer qualquer `:8080`, **pare o serviço** e investigue.
- Chamar a API à mão (como root ou `gabibrain`): `curl --unix-socket /run/gabi-brain/api.sock http://localhost/api/eu -H 'Tailscale-User-Login: <login>'`.

## Acesso (quem entra)
- Listar: `$PY -m gabi.acesso --banco $BANCO listar`.
- Adicionar: `$PY -m gabi.acesso --banco $BANCO adicionar <login-tailscale> <pessoa_id> boss|familia_vip|terceiros`.
- Remover acesso: apagar a linha de `acesso` (sqlite3) e conferir `listar`. Sem login em `acesso`, a pessoa recebe 403.

## Revogar tudo (tokens de agentes)
- `curl --unix-socket /run/gabi-brain/api.sock -X POST http://localhost/api/revogar-tudo -H 'Tailscale-User-Login: <seu-login>' -H 'Content-Type: application/json' -d '{"confirmo": true}'` → `{"revogados": N}`. Sem `confirmo: true` → 400 e nada muda.

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

## Servidor MCP e tokens de agentes (Fase 1)
- O MCP escuta **só em 127.0.0.1:8081** (`gabi-brain-mcp.service`), Streamable HTTP em `/mcp`, e exige `Authorization: Bearer <token>`. Para agentes fora da VPS (Claude Code no seu Windows): `sudo tailscale serve --bg --https=8443 http://127.0.0.1:8081` (TLS na rede privada; o token continua obrigatório).
- Emitir (o token aparece **uma vez**; o banco guarda só o hash): `sudo -u gabibrain /opt/gabi-brain/venv/bin/python -m gabi.mcp.tokens emitir hermes fin` (escopos: `fin,docs,trabalho,pedidos,propostas,sensivel`). Você cola o token no agente; eu não o vejo.
- Listar: `... -m gabi.mcp.tokens listar` · Revogar um: `... revogar <id>` · Revogar todos: `POST /api/revogar-tudo` (ver acima).
- Cada chamada fica em `chamada_mcp` (token, ferramenta, escopo, status `ok|sem_escopo|erro|nao_autenticado`). Para ver: `sqlite3 $BANCO "select quando, ferramenta, status from chamada_mcp order by id desc limit 20"`.
- Só existem ferramentas de **leitura** (`docs/api.md#mcp`). Não há como enviar, pagar, apagar, aprovar nem ligar regra por MCP (R13).
- Se um agente receber `sem_escopo`, o token não tem o escopo da ferramenta: emita outro com o escopo certo (não amplie o de outro agente).
