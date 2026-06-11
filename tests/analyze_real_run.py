"""Analyze the real Photoshop run (inpainting_00155) for residual seam issues.
Read-only: measures and visualizes, changes nothing in the project.
"""
import os, numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, binary_erosion

INP = r"E:\AI\ComfyUI\input"
OUT = r"E:\AI\ComfyUI\output\RasterRelay"
REP = r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-results"
SRC = os.path.join(INP, "rasterrelay-2026-06-11T22-27-04-203Z-source.png")
MSK = os.path.join(INP, "rasterrelay-mask-1781216825242.png")
RES = os.path.join(OUT, "inpainting_00155_.png")

src = Image.open(SRC).convert("RGB")
msk = Image.open(MSK)
res = Image.open(RES)
print("source:", src.size, "| mask:", msk.size, msk.mode, "| result:", res.size, res.mode)

src_a = np.asarray(src, np.float32) / 255.0
# mask: red channel
msk_rgb = np.asarray(msk.convert("RGB"), np.float32) / 255.0
mraw = msk_rgb[..., 0]

# result is padded-to-document with alpha; extract opaque crop bbox
res_rgba = np.asarray(res.convert("RGBA"), np.float32) / 255.0
alpha = res_rgba[..., 3]
ys, xs = np.where(alpha > 0.5)
if len(ys):
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    crop = res_rgba[y0:y1, x0:x1, :3]
    print("result opaque bbox:", (x1 - x0, y1 - y0), "at", (x0, y0))
else:
    crop = res_rgba[..., :3]
    print("WARNING: no alpha bbox; using whole result")

print("crop vs source size match:", crop.shape[:2], src_a.shape[:2])
H, W = min(crop.shape[0], src_a.shape[0]), min(crop.shape[1], src_a.shape[1])
crop = crop[:H, :W]; src_c = src_a[:H, :W]
if mraw.shape[:2] != (H, W):
    mraw = np.asarray(Image.fromarray((mraw*255).astype(np.uint8)).resize((W, H)), np.float32)/255.0

m = mraw > 0.5
print(f"mask coverage: {100*m.mean():.1f}% of crop | mask bbox area")
if m.any():
    mys, mxs = np.where(m)
    print("  mask bbox:", (mxs.min(), mys.min(), mxs.max(), mys.max()))

def luma(x): return 0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2]
outer = binary_dilation(m, iterations=30) & ~m
inner = m & ~binary_erosion(m, iterations=30)

print("\n=== Seam metrics on REAL result (inpainting_00155) ===")
Li, Lo = luma(crop)[inner].mean(), luma(crop)[outer].mean()
dRGB = np.abs(crop[inner].mean(0) - crop[outer].mean(0)).mean()
print(f"  interior-band L = {Li:.3f}  outer-ring L = {Lo:.3f}  dL_seam = {abs(Li-Lo):.4f}  dRGB_seam = {dRGB:.4f}")
print(f"  mask interior mean L = {luma(crop)[m].mean():.3f}  vs context ring L = {luma(crop)[outer].mean():.3f}")
print("  per-channel interior vs ring:",
      np.round(crop[inner].mean(0) - crop[outer].mean(0), 4))

# visuals: mask overlay on source, seam zoom of result, amplified diff result-vs-source
ov = src_c.copy(); ov[..., 0] = np.clip(ov[..., 0] + m*0.4, 0, 1)
Image.fromarray((ov*255).astype(np.uint8)).save(os.path.join(REP, "real_mask_overlay.png"))
# diff inside-ish (where generated differs from original) x3
diff = np.clip(np.abs(crop - src_c)*3.0, 0, 1)
Image.fromarray((diff*255).astype(np.uint8)).save(os.path.join(REP, "real_diff_x3.png"))
# full result crop for viewing
Image.fromarray((crop*255).astype(np.uint8)).save(os.path.join(REP, "real_result_crop.png"))
print("\nWrote real_mask_overlay.png, real_diff_x3.png, real_result_crop.png")
