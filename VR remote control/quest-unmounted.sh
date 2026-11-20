#!/usr/bin/env bash
# Compatibility entry point for existing desktop instructions.
set -euo pipefail
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/scripts/quest-unmounted.sh" "$@"
