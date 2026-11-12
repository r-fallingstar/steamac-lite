#!/bin/bash
# Build the four ABI-compatible libraries from a fresh, verified source tree.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
if pgrep -x steamac-vm >/dev/null; then
  echo 'Close SteamOS before building on an 8 GB Mac.' >&2
  exit 1
fi
# This command owns extraction, execution, validation and publication. There is
# deliberately no command for certifying pre-existing source/library directories.
exec python3 "$ROOT/scripts/lite/record-video-build.py" build
