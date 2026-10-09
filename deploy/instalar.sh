#!/usr/bin/env bash
# Instala o gabi.brain (Fase 0). Idempotente. Só toca em: usuário gabibrain, /opt/gabi-brain,
# /var/lib/gabi-brain, /var/backups/gabi-brain e as unidades systemd. Não abre porta nenhuma.
# A API escuta em socket Unix (/run/gabi-brain/api.sock, pasta 0700): nenhuma porta TCP.
# Uso (root): bash deploy/instalar.sh --confirmo-backup-exportado
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "rode como root (sudo)"; exit 1; }
[ "${1:-}" = "--confirmo-backup-exportado" ] || {
  echo "Gate G1: confirme que o backup foi exportado e que existe snapshot da VPS."
  echo "Depois rode: bash deploy/instalar.sh --confirmo-backup-exportado"; exit 1; }

AQUI="$(cd "$(dirname "$0")/.." && pwd)"
id gabibrain >/dev/null 2>&1 || useradd --system --home-dir /var/lib/gabi-brain --shell /usr/sbin/nologin gabibrain
id gabibrain-fontes >/dev/null 2>&1 || useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin gabibrain-fontes
install -d -o gabibrain -g gabibrain -m 700 /var/lib/gabi-brain /var/lib/gabi-brain/bruto /var/lib/gabi-brain/locks /var/backups/gabi-brain
install -d -o root -g root -m 755 /opt/gabi-brain

rm -rf /opt/gabi-brain/gabi /opt/gabi-brain/migrations /opt/gabi-brain/seeds /opt/gabi-brain/tools
cp -r "$AQUI/gabi" "$AQUI/migrations" "$AQUI/seeds" /opt/gabi-brain/
# Utilitário de administração (seeds editáveis): só os carregadores de seeds, não o diretório tools inteiro.
install -d /opt/gabi-brain/tools && install -m 644 "$AQUI/tools/semear_categorias.py" "$AQUI/tools/semear_donos.py" "$AQUI/tools/marcar_padroes.py" /opt/gabi-brain/tools/
find /opt/gabi-brain -name __pycache__ -prune -exec rm -rf {} +
[ -d /opt/gabi-brain/venv ] || python3 -m venv /opt/gabi-brain/venv
# Só as dependências, com versão fixa; o código roda direto de /opt/gabi-brain (WorkingDirectory), sem pip install do projeto.
/opt/gabi-brain/venv/bin/pip install --quiet --require-virtualenv -r "$AQUI/requirements.lock"
chown -R root:root /opt/gabi-brain

install -m 644 "$AQUI"/deploy/gabi-brain-api.service "$AQUI"/deploy/gabi-brain-mcp.service "$AQUI"/deploy/gabi-brain-fontes.service "$AQUI"/deploy/gabi-brain-backup.service \
  "$AQUI"/deploy/gabi-brain-backup.timer "$AQUI"/deploy/gabi-brain-saldos.service "$AQUI"/deploy/gabi-brain-saldos.timer \
  "$AQUI"/deploy/gabi-brain-extratos.service "$AQUI"/deploy/gabi-brain-extratos.timer "$AQUI"/deploy/gabi-brain-notas.service \
  "$AQUI"/deploy/gabi-brain-avisos.service "$AQUI"/deploy/gabi-brain-avisos.timer "$AQUI"/deploy/gabi-brain-falha@.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now gabi-brain-fontes.service gabi-brain-api.service gabi-brain-mcp.service gabi-brain-backup.timer gabi-brain-avisos.timer
# enable --now não reinicia serviço já ativo: sem isto o código novo fica no disco e o processo segue com o antigo.
systemctl restart gabi-brain-fontes.service gabi-brain-api.service gabi-brain-mcp.service
# Os timers de captura (gabi-brain-saldos.timer, gabi-brain-extratos.timer) ficam instalados mas DESLIGADOS até você pôr a chave (G4).

echo "OK. Verifique:"
echo "  systemctl is-active gabi-brain-api            (esperado: active)"
echo "  ls -l /run/gabi-brain/api.sock                (esperado: srw------- gabibrain; pasta drwx------)"
echo "  ss -ltn | grep 8080                           (esperado: vazio — não há porta TCP)"
echo "Próximo passo (você): sudo tailscale serve --bg --https=443 unix:/run/gabi-brain/api.sock"
echo "Captura (depois do G4, com MCPAI_KEY em /etc/gabi/brain.env): sudo systemctl enable --now gabi-brain-saldos.timer gabi-brain-extratos.timer"
