# RasterRelay

RasterRelay is being prepared for a rebuild of the ComfyUI workflow and custom node approach.

## Current State

- The old workflow files have been removed.
- The old RasterRelay ComfyUI custom nodes have been removed.
- Test code, test assets, generated test output, runtime logs, and old validation scripts have been removed.
- The remaining project is the application shell: Launcher, Photoshop UXP panel, brand asset, and minimal helper scripts.

## Kept Structure

- `launcher/` - Tauri + React launcher.
- `photoshop_plugin/` - Photoshop UXP panel shell.
- `assets/brand/` - RasterRelay brand asset.
- `test-images/` - local image set for manual testing and rebuild references.
- `scripts/create-desktop-shortcut.ps1` - launcher shortcut helper.
- `scripts/load-uxp-plugin.mjs` - UXP Developer Tools loader used by the launcher.

## Rebuild Notes

The next implementation should add a new workflow and any new custom node package from scratch. Avoid reusing the removed workflow contracts, generated test outputs, or previous RasterRelay node assumptions unless they are intentionally redesigned.
