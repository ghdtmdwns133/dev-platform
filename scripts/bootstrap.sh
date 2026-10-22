#!/usr/bin/env sh
# Bootstrap a dev-platform checkout on Linux/macOS.
# Detects required tools, prints install hints instead of installing anything,
# then syncs the CLI environment, checks the version contract and installs hooks.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

missing=""
for tool in uv node dotnet docker; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        missing="$missing $tool"
    fi
done

if [ -n "$missing" ]; then
    echo "Missing required tools:$missing"
    for tool in $missing; do
        case "$tool" in
            uv) echo "  install uv: https://docs.astral.sh/uv/getting-started/installation/" ;;
            node) echo "  install node: https://nodejs.org/en/download" ;;
            dotnet) echo "  install dotnet: https://dotnet.microsoft.com/download" ;;
            docker) echo "  install docker: https://docs.docker.com/engine/install/" ;;
        esac
    done
    echo "Install them and re-run scripts/bootstrap.sh (nothing was installed automatically)."
    exit 1
fi

uv sync --project cli
uv run --project cli devctl versions --check
uv run --project cli devctl hooks install
