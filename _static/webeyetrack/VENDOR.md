# Vendored WebEyeTrack

Do not edit `webeyetrack.js` by hand. It is a build artifact.

- Source: https://github.com/RedForestAI/WebEyeTrack (MIT)
- Pinned at: `14719ad861467c98890058f7c41a94638ae1db2b`
- Patches: [`vendor/webeyetrack/patches/`](../../vendor/webeyetrack/patches/)
- Rebuild: `tools/build_webeyetrack.sh`
- Verify: `tools/build_webeyetrack.sh --check`

## Why we patch upstream

WebEyeTrack personalises its gaze model with `adapt()`, which updates the
network weights in place. Those weights live in a Web Worker, and every oTree
page is a full document load, so the worker — and the calibration — is
destroyed on navigation. There is no upstream API to export that state, and the
calibration support set holds raw eye-patch images rather than anything
serialisable. Patch 0002 therefore adds `saveCalibration(key)` and a matching
restore path via TF.js's `indexeddb://` handler.

The other patches fix a broken build, and add the control surface a research
instrument needs: an explicit `calibrate()` that is not debounced, the ability
to stop incidental clicks from retraining the model, an error signal when the
model fails to load, and `destroy()`.

Each patch is written to be submittable upstream as-is.

## Updating

1. Bump `REF` in [`vendor/webeyetrack/UPSTREAM`](../../vendor/webeyetrack/UPSTREAM).
2. Run `tools/build_webeyetrack.sh`. If a patch no longer applies, the script
   stops and names it.
3. Commit the regenerated `webeyetrack.js` together with the patch changes.

Upstream's build is reproducible from its `package-lock.json`; an unpatched
build of `14719ad861467c98890058f7c41a94638ae1db2b` is byte-identical to the published `webeyetrack@0.0.2`
npm artifact. `--check` relies on that.
