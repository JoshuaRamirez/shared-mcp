#!/usr/bin/env bash
# Daily refresh of the live sections (inventory, tests, doctor); commits and pushes only if the page changed.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 reading-room/generate.py
if ! git diff --quiet -- reading-room/index.html; then
  git -c core.hooksPath=/dev/null commit -qm "room: daily refresh $(date +%F)" -- reading-room/index.html
  git push -q origin main && echo "$(date '+%F %T') refreshed and pushed"
else
  echo "$(date '+%F %T') unchanged"
fi
