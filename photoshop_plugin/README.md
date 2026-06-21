# RasterRelay Photoshop Plugin

This folder contains the remaining Photoshop UXP panel shell.

The previous workflow bundle, test harness, test assets, and RasterRelay custom node assumptions have been removed. The panel still contains the application-side plumbing for document checks, asset export, ComfyUI upload, workflow submission, and result placement, but it is intentionally waiting for a new workflow/custom node design.

## Kept Files

- `manifest.json` - Photoshop Beta 27.8 UXP manifest.
- `index.html` - panel entrypoint.
- `src/panel.js` - panel runtime.
- `src/panel-helpers.js` - shared panel helpers.
- `styles.css` - panel styling.

## Rebuild Notes

Add the next workflow and mapping only when the new approach is defined. Do not assume the removed `photoshop_plugin/workflows` files or old RasterRelay custom nodes still exist.
