"""Diagnose mask-shaped tone stains (run inpainting_00161, arm + wall)."""
import os, numpy as np
from PIL import Image

INP = r"E:\AI\ComfyUI\input"
OUT = r"E:\AI\ComfyUI\output\RasterRelay"
REP = r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-results"
SRC = os.path.join(INP, "rasterrelay-2026-06-12T07-30-04-198Z-source.png")
MSK = os.path.join(INP, "rasterrelay-mask-1781249405062.png")
RES = os.path.join(OUT, "inpainting_00161_.png")

def load(p): return np.asarray(Image.open(p).convert("RGB"), np.float32) / 255.0
def luma(x): return 0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]

src = load(SRC)
res_rgba = np.asarray(Image.open(RES).convert("RGBA"), np.float32) / 255.0
a = res_rgba[..., 3]
ys, xs = np.where(a > 0.5)
res = res_rgba[ys.min():ys.max()+1, xs.min():xs.max()+1, :3]
mask = np.asarray(Image.open(MSK).convert("L"), np.float32) / 255.0
H, W = src.shape[:2]
res = res[:H, :W]
print("src", src.shape, "res", res.shape, "mask coverage", f"{100*(mask>0.5).mean():.1f}%")

m = mask > 0.5
delta = np.abs(res - src).max(axis=-1)          # per-pixel max-channel change
dL = luma(res) - luma(src)

print("\n=== Rozkład zmiany |delta| WEWNĄTRZ maski ===")
d = delta[m]
for q in (10, 25, 50, 75, 90, 99):
    print(f"  p{q:02d} = {np.percentile(d, q):.4f}")
print(f"  fraction with delta < 0.05: {100*(d < 0.05).mean():.1f}%  (kandydat: dryf tla)")
print(f"  fraction with delta > 0.15: {100*(d > 0.15).mean():.1f}%  (kandydat: intencja)")
print(f"  mean dL inside mask: {dL[m].mean():+.4f}")

# overlay + delta map + side by side
ov = src.copy(); ov[..., 0] = np.clip(ov[..., 0] + mask * 0.5, 0, 1)
Image.fromarray((ov * 255).astype(np.uint8)).save(os.path.join(REP, "stain_mask_overlay.png"))
dmap = np.clip(delta * 4, 0, 1)
Image.fromarray((np.stack([dmap]*3, -1) * 255).astype(np.uint8)).save(os.path.join(REP, "stain_delta_x4.png"))
Image.fromarray((np.concatenate([src, res], 1) * 255).astype(np.uint8)).save(os.path.join(REP, "stain_src_res.png"))
print("\nsaved stain_mask_overlay / stain_delta_x4 / stain_src_res")
