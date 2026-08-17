#!/bin/bash
# Full rebuild: refresh App Store data, pull any new artwork, regenerate the site, check it.
#
#   ./build.sh              refresh ratings from the App Store, then build
#   ./build.sh --offline    build from the committed data, no network
#
set -euo pipefail
cd "$(dirname "$0")"

eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null || true

if [[ "${1:-}" == "--offline" ]]; then
  echo "==> using committed app data (offline)"
else
  echo "==> refreshing App Store metadata"
  python3 src/make_apps_json.py
  echo "==> fetching any missing artwork"
  python3 src/fetch_assets.py
  echo "==> regenerating social images"
  python3 src/make_social.py
fi

echo "==> building pages"
python3 src/build.py "${@:2}"

echo "==> checking output"
python3 src/check.py

echo
echo "Done. Preview with:  python3 -m http.server 4173  →  http://localhost:4173"
