#!/usr/bin/env bash
# Instala deploy/hermes/SOUL.md (fonte única) em ~/.hermes/SOUL.md, como o usuário atual (ricardo), sem sudo.
# Se já existe um SOUL diferente, guarda backup SOUL.md.bak-AAAA-MM-DD-HHMM antes de sobrescrever.
# Não reinicia o gateway: só imprime o lembrete.
set -euo pipefail
origem="$(cd "$(dirname "$0")" && pwd)/hermes/SOUL.md"
destino_dir="$HOME/.hermes"
destino="$destino_dir/SOUL.md"
[ -f "$origem" ] || { echo "não achei $origem" >&2; exit 1; }
mkdir -p "$destino_dir"
if [ -f "$destino" ] && ! cmp -s "$origem" "$destino"; then
  backup="$destino.bak-$(date +%F-%H%M)"
  cp -p "$destino" "$backup"
  echo "backup: $backup"
fi
cp "$origem" "$destino"
echo "SOUL instalado em $destino"
echo "Falta reiniciar o gateway: sudo systemctl restart hermes-gateway"
