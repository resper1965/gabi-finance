#!/usr/bin/env bash
# Instala o gabi.brain (Fase 0). Idempotente. Só toca em: usuário gabibrain, /opt/gabi-brain,
# /var/lib/gabi-brain, /var/backups/gabi-brain e 3 unidades systemd. Não abre porta nenhuma.
# Uso (root): bash deploy/instalar.sh --confirmo-backup-exportado
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "rode como root (sudo)"; exit 1; }
[ "${1:-}" = "--confirmo-backup-exportado" ] || {
  echo "Gate G1: confirme que o backup foi exportado e que existe snapshot da VPS."
  echo "Depois rode: bash deploy/instalar.sh --confirmo-backup-exportado"; exit 1; }

AQUI="$(cd "$(dirname "$0")/.." && pwd)"
id gabibrain >/dev/null 2>&1 || useradd --system --home-dir /var/lib/gabi-brain --shell /usr/sbin/nologin gabibrain
install -d -o gabibrain -g gabibrain -m 700 /var/lib/gabi-brain /var/backups/gabi-brain
install -d -o root -g root -m 755 /opt/gabi-brain

rm -rf /opt/gabi-brain/gabi /opt/gabi-brain/migrations
cp -r "$AQUI/gabi" "$AQUI/migrations" "$AQUI/pyproject.toml" /opt/gabi-brain/
find /opt/gabi-brain -name __pycache__ -prune -exec rm -rf {} +
[ -d /opt/gabi-brain/venv ] || python3 -m venv /opt/gabi-brain/venv
/opt/gabi-brain/venv/bin/pip install --quiet /opt/gabi-brain
chown -R root:root /opt/gabi-brain

install -m 644 "$AQUI"/deploy/gabi-brain-api.service "$AQUI"/deploy/gabi-brain-backup.service \
  "$AQUI"/deploy/gabi-brain-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now gabi-brain-api.service gabi-brain-backup.timer

echo "OK. Verifique:"
echo "  systemctl is-active gabi-brain-api            (esperado: active)"
echo "  ss -ltn | grep 8080                           (esperado: só 127.0.0.1:8080)"
echo "Próximo passo (você): sudo tailscale serve --bg --https=443 http://127.0.0.1:8080"
