"""Diagnose the failed 'zielone wlosy' run (inpainting_00156)."""
import os, numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, binary_erosion

INP = r"E:\AI\ComfyUI\input"
OUT = r"E:\AI\ComfyUI\output\RasterRelay"
REP = r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-results"
SRC = os.path.join(INP, "rasterrelay-2026-06-11T23-30-38-490Z-source.png")
MSK = os.path.join(INP, "rasterrelay-mask-1781220639504.png")
RES = os.path.join(OUT, "inpainting_00156_.png")

def load(p): return np.asarray(Image.open(p).convert("RGB"), np.float32) / 255.0
def luma(x): return 0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]

src = load(SRC)
res_im = Image.open(RES).convert("RGBA")
res_a = np.asarray(res_im, np.float32) / 255.0
alpha = res_a[..., 3]
ys, xs = np.where(alpha > 0.5)
y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
res = res_a[y0:y1, x0:x1, :3]
mask = np.asarray(Image.open(MSK).convert("L"), np.float32) / 255.0
H, W = src.shape[:2]
res = res[:H, :W]
print("src", src.shape, "res", res.shape, "mask", mask.shape)

m_hard = mask > 0.5
m_soft_band = (mask > 0.02) & (mask < 0.98)   # transition/halo band
print(f"mask hard coverage {100*m_hard.mean():.1f}% | soft band {100*m_soft_band.mean():.1f}%")

# Where did brightness change vs original?
dL = luma(res) - luma(src)
print("\n=== Brightness change (result - original) by region ===")
for name, reg in [
    ("inside hard mask", m_hard),
    ("soft band (halo)", m_soft_band),
    ("outside mask", mask <= 0.02),
]:
    print(f"  {name:20} dL = {dL[reg].mean():+.4f}  (|dL| {np.abs(dL[reg]).mean():.4f})")

# Greenness: G - (R+B)/2 inside mask, result vs source
green_res = (res[..., 1] - (res[..., 0] + res[..., 2]) / 2)[m_hard].mean()
green_src = (src[..., 1] - (src[..., 0] + src[..., 2]) / 2)[m_hard].mean()
print(f"\n=== Green signal inside mask: source {green_src:+.4f} -> result {green_res:+.4f} ===")

# visuals: mask overlay + amplified dL map
ov = src.copy(); ov[..., 0] = np.clip(ov[..., 0] + (mask) * 0.5, 0, 1)
Image.fromarray((ov * 255).astype(np.uint8)).save(os.path.join(REP, "green_mask_overlay.png"))
dmap = np.clip(np.stack([np.maximum(dL, 0), np.zeros_like(dL), np.maximum(-dL, 0)], -1) * 6, 0, 1)
Image.fromarray((dmap * 255).astype(np.uint8)).save(os.path.join(REP, "green_dL_map_x6.png"))
print("saved green_mask_overlay.png (mask=red) and green_dL_map_x6.png (red=jasniej, niebieski=ciemniej)")
