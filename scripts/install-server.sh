#!/usr/bin/env bash
# Install the committed origin/main snapshot, never the working tree.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${STUDIO_INSTALL_PYTHON:-python3}" "$ROOT/scripts/install_server.py" "$@"
