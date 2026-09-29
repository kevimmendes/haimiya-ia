#!/usr/bin/env bash
#
# Haimiya IA — lançador para Linux
#
#   ./run_ia.sh          modo interativo (escolhe o modo no arranque)
#   ./run_ia.sh 1        escuta contínua
#   ./run_ia.sh 2        apenas quando chamares pelo nome
#
set -euo pipefail

cd "$(dirname "$0")"

VERDE='\033[0;32m'
VERMELHO='\033[0;31m'
SEM='\033[0m'

erro() { printf "${VERMELHO}[x]${SEM} %s\n" "$1" >&2; exit 1; }

[ -d ".venv" ] && source .venv/bin/activate

[ -f ".env" ] || erro "Falta o .env. Corre primeiro:  ./setup_linux.sh"

if [ -t 0 ] && [ -t 1 ]; then
    export PYTHONIOENCODING=utf-8
    export PYTHONUNBUFFERED=1
else
    exec 2>&1
fi

# O pygame abre o mixer de áudio; sem PulseAudio/PipeWire isto rebenta.
export SDL_AUDIODRIVER="${SDL_AUDIODRIVER:-pulse}"

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
    erro "Python 3.10+ é necessário."
fi

python3 run.py "$@"
