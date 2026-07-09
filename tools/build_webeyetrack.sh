#!/usr/bin/env bash
#
# Build the vendored WebEyeTrack bundle from pinned upstream source plus our
# patch series, and install it at _static/webeyetrack/webeyetrack.js.
#
#   tools/build_webeyetrack.sh           build and install
#   tools/build_webeyetrack.sh --check   build and verify the checked-in bundle
#                                        matches, without touching it
#
# Why a patch series rather than a fork
# -------------------------------------
# We need exactly one thing upstream cannot do: persist a calibrated model
# across page loads (WebEyeTrack adapts the model in place inside a Web Worker,
# and an oTree page navigation destroys the worker). Everything else we need is
# reachable from our own code. So the diff is deliberately small, each patch is
# self-contained and submittable upstream unchanged, and updating means bumping
# REF in vendor/webeyetrack/UPSTREAM and re-running this script. If upstream
# moves the code we patch, `git apply` fails loudly instead of silently
# producing a bundle that behaves differently from the source we think it came
# from.
#
# Upstream's build is byte-for-byte reproducible from its package-lock.json, so
# --check is a real supply-chain assertion: the committed bundle is exactly what
# this pinned source and these patches produce, and nothing else.
#
# Requires: node, npm, curl, tar, git.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR_DIR="$REPO_ROOT/vendor/webeyetrack"
PATCH_DIR="$VENDOR_DIR/patches"
DEST_DIR="$REPO_ROOT/_static/webeyetrack"
DEST="$DEST_DIR/webeyetrack.js"

CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

# shellcheck disable=SC1091
REPO="$(sed -n 's/^REPO=//p' "$VENDOR_DIR/UPSTREAM")"
REF="$(sed -n 's/^REF=//p' "$VENDOR_DIR/UPSTREAM")"
test -n "$REPO" && test -n "$REF" || { echo "error: REPO/REF missing from $VENDOR_DIR/UPSTREAM" >&2; exit 1; }

for cmd in node npm curl tar git; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "error: '$cmd' is required" >&2; exit 1; }
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Fetching ${REPO} @ ${REF}"
curl -fsSL "${REPO/github.com/codeload.github.com}/tar.gz/${REF}" -o "$TMP/src.tgz"
mkdir -p "$TMP/src"
tar xzf "$TMP/src.tgz" -C "$TMP/src" --strip-components=1

JS="$TMP/src/js"
test -d "$JS/src" || { echo "error: js/src missing -- upstream layout changed" >&2; exit 1; }

echo "Applying patch series"
for patch in "$PATCH_DIR"/*.patch; do
  name="$(basename "$patch")"
  if ! git -C "$JS" apply --check "$patch" 2>/dev/null; then
    echo "error: ${name} does not apply to ${REF}." >&2
    echo "       Upstream moved the code this patch touches. Re-roll it against" >&2
    echo "       the new source, then bump REF in vendor/webeyetrack/UPSTREAM." >&2
    exit 1
  fi
  git -C "$JS" apply "$patch"
  echo "  applied ${name}"
done

echo "Installing build dependencies (--ignore-scripts skips 'canvas', a jest-only native dep)"
npm --prefix "$JS" ci --ignore-scripts --no-audit --no-fund >/dev/null 2>&1

echo "Building"
( cd "$JS" && npx webpack --config webpack.config.js >/dev/null 2>&1 )
BUILT="$JS/dist/index.js"
test -f "$BUILT" || { echo "error: webpack produced no dist/index.js" >&2; exit 1; }

# The bundle must expose the API our tracker depends on. A silent upstream
# rename would otherwise ship a bundle that fails only in a participant's
# browser, mid-study.
for symbol in 'type:"calibrate"' 'type:"error"' 'setAdaptOnClick' 'indexeddb://' 'type:"ready"'; do
  if ! grep -q "$symbol" "$BUILT"; then
    echo "error: built bundle is missing '${symbol}'. The patches applied but did not take effect." >&2
    exit 1
  fi
done
node --check "$BUILT"
echo "  built $(wc -c < "$BUILT" | tr -d ' ') bytes; API symbols present; parses"

if [ "$CHECK_ONLY" -eq 1 ]; then
  if cmp -s "$BUILT" "$DEST"; then
    echo "OK: ${DEST#"$REPO_ROOT"/} is exactly what ${REF} + patches produce."
    exit 0
  fi
  echo "MISMATCH: ${DEST#"$REPO_ROOT"/} differs from a fresh build." >&2
  echo "          Run tools/build_webeyetrack.sh to regenerate it." >&2
  exit 1
fi

mkdir -p "$DEST_DIR"
cp "$BUILT" "$DEST"
cp "$TMP/src/LICENSE" "$DEST_DIR/LICENSE"
cp "$JS/dist/index.js.LICENSE.txt" "$DEST_DIR/THIRD_PARTY_LICENSES.txt"

cat > "$DEST_DIR/VENDOR.md" <<EOF
# Vendored WebEyeTrack

Do not edit \`webeyetrack.js\` by hand. It is a build artifact.

- Source: ${REPO} (MIT)
- Pinned at: \`${REF}\`
- Patches: [\`vendor/webeyetrack/patches/\`](../../vendor/webeyetrack/patches/)
- Rebuild: \`tools/build_webeyetrack.sh\`
- Verify: \`tools/build_webeyetrack.sh --check\`

## Why we patch upstream

WebEyeTrack personalises its gaze model with \`adapt()\`, which updates the
network weights in place. Those weights live in a Web Worker, and every oTree
page is a full document load, so the worker — and the calibration — is
destroyed on navigation. There is no upstream API to export that state, and the
calibration support set holds raw eye-patch images rather than anything
serialisable. Patch 0002 therefore adds \`saveCalibration(key)\` and a matching
restore path via TF.js's \`indexeddb://\` handler.

The other patches fix a broken build, and add the control surface a research
instrument needs: an explicit \`calibrate()\` that is not debounced, the ability
to stop incidental clicks from retraining the model, an error signal when the
model fails to load, and \`destroy()\`.

Each patch is written to be submittable upstream as-is.

## Updating

1. Bump \`REF\` in [\`vendor/webeyetrack/UPSTREAM\`](../../vendor/webeyetrack/UPSTREAM).
2. Run \`tools/build_webeyetrack.sh\`. If a patch no longer applies, the script
   stops and names it.
3. Commit the regenerated \`webeyetrack.js\` together with the patch changes.

Upstream's build is reproducible from its \`package-lock.json\`; an unpatched
build of \`${REF}\` is byte-identical to the published \`webeyetrack@0.0.2\`
npm artifact. \`--check\` relies on that.
EOF

echo
echo "Installed:"
ls -la "$DEST_DIR" | awk 'NR>3 {printf "  %-28s %10s bytes\n", $9, $5}'
