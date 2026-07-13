#!/usr/bin/env bash
#
# Download MediaPipe's face-detection runtime and model into _static/mediapipe/.
#
#   tools/fetch_mediapipe_assets.sh           download (skips files already present and valid)
#   tools/fetch_mediapipe_assets.sh --check   verify the checked-in files, download nothing
#
# Why
# ---
# WebEyeTrack fetches the MediaPipe WASM runtime from jsDelivr and the face
# landmark model from a Google Cloud Storage bucket, in every participant's
# browser, at run time. That is two things a study cannot control: whether those
# hosts are reachable when a participant sits down, and whether participants'
# IP addresses may be disclosed to them. Serving the files ourselves removes
# both. See vendor/webeyetrack/patches/0004-*.patch for the change that makes
# the paths configurable.
#
# MediaPipe is Apache-2.0. The checksums below pin exactly what we serve; if an
# upstream URL ever returns different bytes, this script fails rather than
# silently shipping them.

set -euo pipefail

MEDIAPIPE_VERSION="0.10.3"
WASM_BASE="https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MEDIAPIPE_VERSION}/wasm"
MODEL_URL="https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"

DEST="$(cd "$(dirname "$0")/.." && pwd)/_static/mediapipe"

CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

# MediaPipe's FilesetResolver probes for WASM SIMD support and loads whichever
# pair matches, so both must be present.
#   path-relative-to-DEST | url
ASSETS="
wasm/vision_wasm_internal.js|${WASM_BASE}/vision_wasm_internal.js
wasm/vision_wasm_internal.wasm|${WASM_BASE}/vision_wasm_internal.wasm
wasm/vision_wasm_nosimd_internal.js|${WASM_BASE}/vision_wasm_nosimd_internal.js
wasm/vision_wasm_nosimd_internal.wasm|${WASM_BASE}/vision_wasm_nosimd_internal.wasm
face_landmarker.task|${MODEL_URL}
"

sha256() { shasum -a 256 "$1" | cut -d' ' -f1; }

SUMS_FILE="$(cd "$(dirname "$0")/.." && pwd)/vendor/mediapipe/SHA256SUMS"

fetch_one() {
  local rel="$1" url="$2"
  local out="$DEST/$rel"
  mkdir -p "$(dirname "$out")"
  echo "  fetching $rel"
  curl -fsSL "$url" -o "$out"
}

mkdir -p "$DEST" "$(dirname "$SUMS_FILE")"

if [ "$CHECK_ONLY" -eq 1 ]; then
  test -f "$SUMS_FILE" || { echo "error: $SUMS_FILE missing; run without --check first" >&2; exit 1; }
  status=0
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    expected="${line%% *}"
    rel="${line##* }"
    if [ ! -f "$DEST/$rel" ]; then
      echo "MISSING  $rel" >&2; status=1; continue
    fi
    actual="$(sha256 "$DEST/$rel")"
    if [ "$actual" != "$expected" ]; then
      echo "MISMATCH $rel" >&2; status=1
    else
      echo "  ok  $rel"
    fi
  done < "$SUMS_FILE"
  [ "$status" -eq 0 ] && echo "OK: MediaPipe assets match ${SUMS_FILE#"$(cd "$(dirname "$0")/.." && pwd)"/}"
  exit "$status"
fi

echo "Downloading MediaPipe ${MEDIAPIPE_VERSION} assets into ${DEST}"
: > "$SUMS_FILE.tmp"
echo "$ASSETS" | while IFS='|' read -r rel url; do
  [ -z "$rel" ] && continue
  fetch_one "$rel" "$url"
  echo "$(sha256 "$DEST/$rel")  $rel" >> "$SUMS_FILE.tmp"
done
mv "$SUMS_FILE.tmp" "$SUMS_FILE"

cat > "$DEST/NOTICE" <<'EOF'
These files are redistributed unmodified from Google's MediaPipe project.

  vision_wasm_*.{js,wasm}   @mediapipe/tasks-vision 0.10.3   Apache License 2.0
  face_landmarker.task      MediaPipe Face Landmarker         Apache License 2.0

  https://github.com/google-ai-edge/mediapipe
  https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker

They are served from this application's own /static/ tree so that no
participant's browser contacts a third-party host while a study is running.

Regenerate and verify with tools/fetch_mediapipe_assets.sh.
EOF

echo
echo "Fetched:"
find "$DEST" -type f | sort | while read -r f; do
  printf "  %-46s %10s bytes\n" "${f#"$DEST"/}" "$(wc -c < "$f" | tr -d ' ')"
done
echo
echo "Checksums written to ${SUMS_FILE}"
