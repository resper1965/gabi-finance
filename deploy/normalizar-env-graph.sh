#!/usr/bin/env bash
# Tira os espaços ao redor do '=' em /etc/gabi/graph-ness.env (o systemd não aceita "CHAVE =valor"). Só o dono roda: sudo ./normalizar-env-graph.sh
# Faz backup, mantém dono e modo e imprime SÓ os nomes das chaves, nunca os valores.
set -euo pipefail
ARQ=/etc/gabi/graph-ness.env
[ "$(id -u)" -eq 0 ] || { echo "rode com sudo" >&2; exit 1; }
[ -f "$ARQ" ] || { echo "não existe: $ARQ" >&2; exit 1; }
cp -p "$ARQ" "$ARQ.bak-$(date +%Y%m%d%H%M%S)"
sed -E -i 's/^([A-Za-z0-9_]+)[[:space:]]*=[[:space:]]*/\1=/' "$ARQ"
echo "chaves em $ARQ:"
sed -E 's/=.*//' "$ARQ" | grep -v '^[[:space:]]*$' || true
stat -c 'dono %U:%G modo %a' "$ARQ"
