#!/usr/bin/env bash
# Copy the canonical shared_mcp.py into plugin roots. Plugins are distributed alone, so they
# carry their own copy; this keeps every copy byte-identical to the canonical file.
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/shared_mcp.py"
for d in "$@"; do cp "$SRC" "$d/shared_mcp.py"; echo "vendored $(grep -m1 '^VERSION' "$SRC") -> $d/shared_mcp.py"; done
