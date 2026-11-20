#!/usr/bin/env bash
# Stable entry point; implementation lives in scripts/.
set -euo pipefail
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/scripts/start-studio.sh" "$@"
