#!/bin/bash
# Build source-pinned private Wine media PE modules. Keep the SteamOS VM stopped.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
exec python3 "$root/scripts/lite/record-media-build.py" build "$@"
