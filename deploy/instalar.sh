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

# Backup consistente do banco antes de trocar o código (API backup do sqlite3: a API pode estar escrevendo em WAL; nunca cp do arquivo).
# Na primeira instalação o banco não existe: pula sem erro.
if [ -f /var/lib/gabi-brain/gabi.db ]; then
  BKP_ANTES="/var/backups/gabi-brain/gabi.db.antes-instalar-$(date +%F-%H%M)"
  # Roda como o dono do banco, em leitura/escrita normal: uma conexão somente-leitura como root deixaria gabi.db-wal/-shm root:root e a API não gravaria mais.
  runuser -u gabibrain -- python3 - "$BKP_ANTES" <<'PY'
import os, sqlite3, sys
os.umask(0o077)
src = sqlite3.connect("/var/lib/gabi-brain/gabi.db")
dst = sqlite3.connect(sys.argv[1])
try:
    src.backup(dst)
    dst.execute("pragma journal_mode=delete")
    ok = dst.execute("pragma integrity_check").fetchone()[0]
except BaseException:
    dst.close()
    os.unlink(sys.argv[1])  # backup ruim não pode contar na retenção de 5
    raise
dst.close()
src.close()
if ok != "ok":
    os.unlink(sys.argv[1])  # idem
    sys.exit("backup antes de instalar falhou na integridade: " + ok)
PY
  chown gabibrain:gabibrain "$BKP_ANTES"
  chmod 600 "$BKP_ANTES"
  # Retenção: guarda os 5 mais recentes.
  ls -1t /var/backups/gabi-brain/gabi.db.antes-instalar-* | tail -n +6 | xargs -r rm -f
fi

# Troca sem janela vazia: monta a árvore nova em .novo e só então move pasta a pasta (o velho vai para .velho).
rm -rf /opt/gabi-brain/.novo /opt/gabi-brain/.velho
install -d /opt/gabi-brain/.novo /opt/gabi-brain/.velho
cp -r "$AQUI/gabi" "$AQUI/migrations" "$AQUI/seeds" /opt/gabi-brain/.novo/
# Utilitário de administração (seeds editáveis): carregadores de seeds, a correção de moeda e o comparador do G21, não o diretório tools inteiro.
install -d /opt/gabi-brain/.novo/tools && install -m 644 "$AQUI/tools/semear_categorias.py" "$AQUI/tools/semear_donos.py" "$AQUI/tools/marcar_padroes.py" "$AQUI/tools/corrigir_moeda.py" "$AQUI/tools/comparar_agenda.py" /opt/gabi-brain/.novo/tools/
for d in gabi migrations seeds tools; do
  if [ -e "/opt/gabi-brain/$d" ]; then
    mv "/opt/gabi-brain/$d" /opt/gabi-brain/.velho/
  fi
  mv "/opt/gabi-brain/.novo/$d" /opt/gabi-brain/
done
rm -rf /opt/gabi-brain/.novo /opt/gabi-brain/.velho
find /opt/gabi-brain -name __pycache__ -prune -exec rm -rf {} +
[ -d /opt/gabi-brain/venv ] || python3 -m venv /opt/gabi-brain/venv
# Só as dependências, com versão fixa; o código roda direto de /opt/gabi-brain (WorkingDirectory), sem pip install do projeto.
/opt/gabi-brain/venv/bin/pip install --quiet --require-virtualenv -r "$AQUI/requirements.lock"
chown -R root:root /opt/gabi-brain

install -m 644 "$AQUI"/deploy/gabi-brain-api.service "$AQUI"/deploy/gabi-brain-mcp.service "$AQUI"/deploy/gabi-brain-fontes.service "$AQUI"/deploy/gabi-brain-backup.service \
  "$AQUI"/deploy/gabi-brain-backup.timer "$AQUI"/deploy/gabi-brain-saldos.service "$AQUI"/deploy/gabi-brain-saldos.timer \
  "$AQUI"/deploy/gabi-brain-extratos.service "$AQUI"/deploy/gabi-brain-extratos.timer "$AQUI"/deploy/gabi-brain-notas.service \
  "$AQUI"/deploy/gabi-brain-notas.timer "$AQUI"/deploy/gabi-brain-avisos.service "$AQUI"/deploy/gabi-brain-avisos.timer "$AQUI"/deploy/gabi-brain-falha@.service "$AQUI"/deploy/gabi-brain-exportacao.service "$AQUI"/deploy/gabi-brain-exportacao.timer \
  "$AQUI"/deploy/gabi-brain-telegram.service "$AQUI"/deploy/gabi-brain-telegram.timer /etc/systemd/system/
# Units cortadas pela ADR-023 (22/10/2026) e pelo corte do gabi-finance (agenda, anexos, contatos, correio, documentos, teams): desliga e remove as que o instalador antigo deixou em /etc/systemd/system (idempotente; não apaga dado).
for u in gabi-brain-escuta.service gabi-brain-escuta.timer gabi-brain-escuta.path escuta-ouvinte.service gabi-brain-trabalho.service gabi-brain-trabalho.timer \
         gabi-brain-comprovantes.service gabi-brain-comprovantes.timer gabi-brain-exames.service gabi-brain-exames.timer \
         gabi-brain-reembolso-saude.service gabi-brain-reembolso-saude.timer \
         gabi-brain-agenda.service gabi-brain-agenda.timer gabi-brain-anexos.service gabi-brain-anexos.timer gabi-brain-contatos.service gabi-brain-contatos.timer \
         gabi-brain-correio.service gabi-brain-correio.timer gabi-brain-documentos.service gabi-brain-documentos.timer gabi-brain-teams.service gabi-brain-teams.timer; do
  systemctl disable --now "$u" 2>/dev/null || true
  rm -f "/etc/systemd/system/$u"
done
systemctl daemon-reload
systemctl enable --now gabi-brain-fontes.service gabi-brain-api.service gabi-brain-mcp.service gabi-brain-backup.timer gabi-brain-avisos.timer gabi-brain-notas.timer gabi-brain-exportacao.timer gabi-brain-telegram.timer
# enable --now não reinicia serviço já ativo: sem isto o código novo fica no disco e o processo segue com o antigo.
systemctl restart gabi-brain-fontes.service gabi-brain-api.service gabi-brain-mcp.service
# Os timers de captura (gabi-brain-saldos.timer, gabi-brain-extratos.timer) ficam instalados mas DESLIGADOS até você pôr a chave (G4).

echo "OK. Verifique:"
echo "  systemctl is-active gabi-brain-api            (esperado: active)"
echo "  ls -l /run/gabi-brain/api.sock                (esperado: srw------- gabibrain; pasta drwx------)"
echo "  ss -ltn | grep 8080                           (esperado: vazio — não há porta TCP)"
echo "Próximo passo (você): sudo tailscale serve --bg --https=443 unix:/run/gabi-brain/api.sock"
echo "Captura (depois do G4, com MCPAI_KEY em /etc/gabi/brain.env): sudo systemctl enable --now gabi-brain-saldos.timer gabi-brain-extratos.timer"
