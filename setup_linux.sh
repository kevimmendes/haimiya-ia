#!/usr/bin/env bash
#
# Haimiya IA — instalador para Linux
#
# Instala as libs de sistema que o pip não traz, cria um venv e instala
# as dependências Python. Pode correr várias vezes sem quebrar nada.
#
#   ./setup_linux.sh
#
set -euo pipefail

VERDE='\033[0;32m'
AMARELO='\033[0;33m'
VERMELHO='\033[0;31m'
SEM='\033[0m'

info()  { printf "${VERDE}[+]${SEM} %s\n" "$1"; }
aviso() { printf "${AMARELO}[!]${SEM} %s\n" "$1"; }
erro()  { printf "${VERMELHO}[x]${SEM} %s\n" "$1" >&2; }

cd "$(dirname "$0")"

# ---------------------------------------------------------------- detetar distro
detetar_pacotes() {
    if command -v apt-get >/dev/null 2>&1; then
        echo "apt"
    elif command -v dnf >/dev/null 2>&1; then
        echo "dnf"
    elif command -v pacman >/dev/null 2>&1; then
        echo "pacman"
    elif command -v zypper >/dev/null 2>&1; then
        echo "zypper"
    else
        echo "desconhecido"
    fi
}

instalar() {
    local gestor="$1"; shift
    case "$gestor" in
        apt)    DEBIAN_FRONTEND=noninteractive apt-get install -y "$@" ;;
        dnf)    dnf install -y "$@" ;;
        pacman) pacman -S --needed --noconfirm "$@" ;;
        zypper) zypper install -y "$@" ;;
    esac
}

GESTOR="$(detetar_pacotes)"
info "Gestor de pacotes detetado: $GESTOR"

# ---------------------------------------------------------------- python base
if ! command -v python3 >/dev/null 2>&1; then
    erro "python3 não encontrado. Instala-o e volta a correr este script."
    exit 1
fi

VERSAO_PY="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
info "Python $VERSAO_PY"
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
    erro "Python 3.10+ é necessário (o código usa sintaxe moderna)."
    exit 1
fi

# ---------------------------------------------------------------- subsistema gráfico
if [ -n "${WAYLAND_DISPLAY:-}" ] && [ -z "${DISPLAY:-}" ]; then
    aviso "Wayland puro detetado."
    aviso "A captura de ecrã só funciona em janelas X11 (via XWayland)."
    aviso "Se usares GNOME em Wayland, a visão do ecrã vai devolver vazio."
    aviso "Alternativa: iniciar a sessão em 'Ubuntu on Xorg' nas definições de login."
fi

if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    aviso "Sem DISPLAY nem WAYLAND_DISPLAY: a correr sem ecrã."
    aviso "Visão e rato/teclado vão ficar desativados. A voz continua a funcionar."
fi

# ---------------------------------------------------------------- libs de sistema
PAQUETES_SISTEMA=(
    python3-tk python3-venv python3-dev
    libx11-6 libxext6 libxtst6 libxrender1
    libasound2t64 portaudio19-dev
    xdg-utils
)

case "$GESTOR" in
    apt)
        info "A instalar libs de sistema (precisa de sudo)..."
        sudo apt-get update -qq
        instalar apt "${PAQUETES_SISTEMA[@]}"
        ;;
    dnf)    instalar dnf python3-tkinter python3-devel alsa-lib portaudio-devel xdg-utils ;;
    pacman) instalar pacman tk python alsa-lib portaudio xdg-utils ;;
    zypper) instalar zypper python3-tk python3-devel alsa-devel portaudio-devel xdg-utils ;;
    *) aviso "Gestor desconhecido: instala à mão o python3-tk e a portaudio." ;;
esac

# ---------------------------------------------------------------- venv
if [ ! -d ".venv" ]; then
    info "A criar ambiente virtual em .venv"
    python3 -m venv .venv
else
    info "Ambiente virtual .venv já existe"
fi

# shellcheck disable=SC1091
source .venv/bin/activate

info "A atualizar pip"
python -m pip install --quiet --upgrade pip wheel

info "A instalar dependências Python (pode demorar: torch é grande)"
if python -m pip install -r requirements-linux.txt; then
    info "Dependências instaladas"
else
    erro "Falhou a instalação. Se a culpa for do pacote 'keyboard',"
    erro "instala o resto assim:"
    erro "  pip install -r requirements-linux.txt --no-deps"
    exit 1
fi

# ---------------------------------------------------------------- .env
if [ ! -f ".env" ]; then
    cp .env.example .env
    chmod 600 .env
    aviso "Criei o .env a partir do .env.example. Preenche:"
    aviso "  GROQ_API_KEY_LLM=<a tua chave>"
    aviso "Ver README_LINUX.md para o resto."
else
    info ".env já existe"
fi

# ---------------------------------------------------------------- verificação final
echo
info "A verificar o ambiente..."
python - <<'PYEOF'
import sys
sys.path.insert(0, ".")
try:
    from Arcana import platform_shim as ps
except Exception as e:
    print(f"[x] platform_shim não importou: {e}")
    raise SystemExit(1)

print(ps.descrever_ambiente())

problemas = []
if not ps.TEM_ECRA:
    problemas.append("sem sessão gráfica: visão e rato/teclado indisponíveis")
if not ps.tem_ferramenta("xdg-open"):
    problemas.append("falta xdg-open: não consegue abrir ficheiros")
if not ps.detetar_backend_ecra() == "mss" and not ps.IS_WINDOWS:
    problemas.append("mss não instalado: a captura de ecrã pode falhar")

print()
if problemas:
    for p in problemas:
        print(f"[!] {p}")
else
    print("[+] Ambiente pronto. Corre com:  ./run_ia.sh")
PYEOF
