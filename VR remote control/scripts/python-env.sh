#!/usr/bin/env bash
# Sourced by launch helpers. An explicit interpreter always wins.
rd_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -n "${ROBODATA_PYTHON:-}" ]]; then
  rd_python="$ROBODATA_PYTHON"
elif [[ -x "$rd_root/.venv/bin/python" ]]; then
  rd_python="$rd_root/.venv/bin/python"
else
  rd_python=python3
fi
