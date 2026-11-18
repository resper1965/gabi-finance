#!/usr/bin/env bash
# Instala o gabi-finance. Idempotente. Só toca em: usuários gabifinance e gabifinance-fontes, /opt/gabi-finance, /var/lib/gabi-finance,
# /var/backups/gabi-finance, /etc/gabi-finance (pasta vazia, 0755) e as unidades systemd gabi-finance-*. Não toca no serviço anterior (a produção que ele substitui) nem abre porta nenhuma.
# As unidades ficam INSTALADAS E DESLIGADAS: quem liga é a virada (docs/virada.md), depois da conferência lado a lado com o serviço anterior.
# A API escuta em socket Unix (/run/gabi-finance/api.sock, pasta 0700): nenhuma porta TCP.
# Uso (root): bash deploy/instalar.sh --confirmo-backup-exportado
set -euo pipefail
# um umask 077 herdado deixava o código ilegível para o usuário do serviço (18/11/2026)
umask 022
[ "$(id -u)" = 0 ] || { echo "rode como root (sudo)"; exit 1; }
[ "${1:-}" = "--confirmo-backup-exportado" ] || {
  echo "Gate G1: confirme que o backup foi exportado e que existe snapshot da VPS."
  echo "Depois rode: bash deploy/instalar.sh --confirmo-backup-exportado"; exit 1; }

AQUI="$(cd "$(dirname "$0")/.." && pwd)"
id gabifinance >/dev/null 2>&1 || useradd --system --home-dir /var/lib/gabi-finance --shell /usr/sbin/nologin gabifinance
id gabifinance-fontes >/dev/null 2>&1 || useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin gabifinance-fontes
install -d -o gabifinance -g gabifinance -m 700 /var/lib/gabi-finance /var/lib/gabi-finance/bruto /var/lib/gabi-finance/locks /var/backups/gabi-finance
install -d -o root -g root -m 755 /opt/gabi-finance /etc/gabi-finance

# Backup consistente do banco antes de trocar o código (API backup do sqlite3: a API pode estar escrevendo em WAL; nunca cp do arquivo).
# Na primeira instalação o banco não existe: pula sem erro.
if [ -f /var/lib/gabi-finance/gabi.db ]; then
  BKP_ANTES="/var/backups/gabi-finance/gabi.db.antes-instalar-$(date +%F-%H%M)"
  # Roda como o dono do banco, em leitura/escrita normal: uma conexão somente-leitura como root deixaria gabi.db-wal/-shm root:root e a API não gravaria mais.
  runuser -u gabifinance -- python3 - "$BKP_ANTES" <<'PY'
import os, sqlite3, sys
os.umask(0o077)
src = sqlite3.connect("/var/lib/gabi-finance/gabi.db")
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
  chown gabifinance:gabifinance "$BKP_ANTES"
  chmod 600 "$BKP_ANTES"
  # Retenção: guarda os 5 mais recentes.
  ls -1t /var/backups/gabi-finance/gabi.db.antes-instalar-* | tail -n +6 | xargs -r rm -f
fi

# Troca sem janela vazia: monta a árvore nova em .novo e só então move pasta a pasta (o velho vai para .velho).
rm -rf /opt/gabi-finance/.novo /opt/gabi-finance/.velho
install -d /opt/gabi-finance/.novo /opt/gabi-finance/.velho
cp -r "$AQUI/gabi" "$AQUI/migrations" "$AQUI/seeds" /opt/gabi-finance/.novo/
# Utilitários de administração (seeds editáveis): carregadores de seeds, a correção de moeda, o comparador do G21 e a conferência da virada, não o diretório tools inteiro.
install -d /opt/gabi-finance/.novo/tools && install -m 644 "$AQUI/tools/semear_categorias.py" "$AQUI/tools/semear_donos.py" "$AQUI/tools/marcar_padroes.py" "$AQUI/tools/corrigir_moeda.py" "$AQUI/tools/comparar_agenda.py" "$AQUI/tools/conferir_virada.py" /opt/gabi-finance/.novo/tools/
for d in gabi migrations seeds tools; do
  if [ -e "/opt/gabi-finance/$d" ]; then
    mv "/opt/gabi-finance/$d" /opt/gabi-finance/.velho/
  fi
  mv "/opt/gabi-finance/.novo/$d" /opt/gabi-finance/
done
rm -rf /opt/gabi-finance/.novo /opt/gabi-finance/.velho
find /opt/gabi-finance -name __pycache__ -prune -exec rm -rf {} +
[ -d /opt/gabi-finance/venv ] || python3 -m venv /opt/gabi-finance/venv
# Só as dependências, com versão fixa; o código roda direto de /opt/gabi-finance (WorkingDirectory), sem pip install do projeto.
/opt/gabi-finance/venv/bin/pip install --quiet --require-virtualenv -r "$AQUI/requirements.lock"
chown -R root:root /opt/gabi-finance

install -m 644 "$AQUI"/deploy/gabi-finance-api.service "$AQUI"/deploy/gabi-finance-mcp.service "$AQUI"/deploy/gabi-finance-fontes.service "$AQUI"/deploy/gabi-finance-backup.service \
  "$AQUI"/deploy/gabi-finance-backup.timer "$AQUI"/deploy/gabi-finance-saldos.service "$AQUI"/deploy/gabi-finance-saldos.timer \
  "$AQUI"/deploy/gabi-finance-extratos.service "$AQUI"/deploy/gabi-finance-extratos.timer "$AQUI"/deploy/gabi-finance-notas.service \
  "$AQUI"/deploy/gabi-finance-notas.timer "$AQUI"/deploy/gabi-finance-avisos.service "$AQUI"/deploy/gabi-finance-avisos.timer "$AQUI"/deploy/gabi-finance-falha@.service "$AQUI"/deploy/gabi-finance-exportacao.service "$AQUI"/deploy/gabi-finance-exportacao.timer \
  "$AQUI"/deploy/gabi-finance-telegram.service "$AQUI"/deploy/gabi-finance-telegram.timer /etc/systemd/system/
systemctl daemon-reload
# Nada é ligado aqui (nem enable, nem start, nem restart): a virada liga na ordem certa (docs/virada.md). Uma reinstalação por cima de um
# gabi-finance já ligado também não reinicia nada; depois dela rode `systemctl restart gabi-finance-fontes gabi-finance-api gabi-finance-mcp`.

echo "OK: gabi-finance instalado; nenhuma unidade foi ligada."
echo "Conferir as unidades instaladas:  systemctl list-unit-files 'gabi-finance-*'   (esperado: todas disabled)"
echo "Próximo passo (você): siga docs/virada.md (tokens em /etc/gabi-finance/, banco copiado, conferência, ligar)."
