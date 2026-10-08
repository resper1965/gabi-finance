#!/usr/bin/env bash
# Commita SÓ se a suíte inteira passar (código de saída do pytest, não do tail). Uso: tools/commitar.sh "mensagem"
set -u
cd "$(dirname "$0")/.."
.venv/bin/pytest -q > .superpowers/ultima-suite.txt 2>&1; rc=$?
tail -1 .superpowers/ultima-suite.txt
[ $rc -eq 0 ] || { echo "SEM COMMIT: suíte falhou (rc=$rc)"; grep -E "^FAILED|^ERROR" .superpowers/ultima-suite.txt | head; exit $rc; }
git add -A && git commit -qm "$1" && git log --oneline | head -1
