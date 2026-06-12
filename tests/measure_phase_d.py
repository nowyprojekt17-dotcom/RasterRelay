"""Phase D measurements: seam/intent metrics + DETAIL SHARPNESS vs pre-D runs."""
import os, glob, numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, binary_erosion, laplace

OUT = r"E:\AI\ComfyUI\output\RasterRelay"
INP = r"E:\AI\ComfyUI\input"
REP = r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-results"

def files(p): return sorted(glob.glob(os.path.join(OUT, p + "*.png")), key=os.path.getmtime)
def load(p): return np.asarray(Image.open(p).convert("RGB"), np.float32) / 255.0
def luma(x): return 0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]
def sharpness(img, region):
    return float(np.var(laplace(luma(img)))) if region is None else float(np.var(laplace(luma(img))[region]))

# ---- B2 blonde: new (Phase D) vs previous (Phase B) ----
srcP = load(os.path.join(INP, "rasterrelay-2026-06-11T22-27-04-203Z-source.png"))
maskB = np.asarray(Image.open(os.path.join(INP, "rasterrelay-mask-1781216825242.png")).convert("L"), np.float32) / 255.0
mB = maskB > 0.5
H, W = srcP.shape[:2]
b2 = files("TEST_B2__")
new = load(b2[-1])[:H, :W]
old = load(b2[-2])[:H, :W]
outer = binary_dilation(mB, iterations=25) & ~mB
inner = mB & ~binary_erosion(mB, iterations=25)
print("=== B2 blond: Phase D (gen 1168x1008) vs Phase B (gen 624x544) ===")
for name, img in [("Phase B", old), ("Phase D", new)]:
    dl = abs(luma(img)[inner].mean() - luma(img)[outer].mean())
    sh = sharpness(img, mB)
    print(f"  {name}: dL_seam={dl:.4f}  ostrosc(maska)={sh:.5f}")
print(f"  ostrosc oryginalu (maska) = {sharpness(srcP, mB):.5f}")
def zoom(img, y0, y1, x0, x1, s=4):
    c = (img[y0:y1, x0:x1] * 255).astype(np.uint8)
    return np.asarray(Image.fromarray(c).resize(((x1 - x0) * s, (y1 - y0) * s), Image.LANCZOS))
# hair strands close-up: orig | phaseB | phaseD
Image.fromarray(np.concatenate([zoom(i, 150, 250, 480, 600) for i in [srcP, old, new]], 1)).save(
    os.path.join(REP, "D_sharpness_zoom.png"))

# ---- G2 green: intent + drift on Phase D ----
srcG = load(os.path.join(INP, "rasterrelay-2026-06-11T23-30-38-490Z-source.png"))
maskG = np.asarray(Image.open(os.path.join(INP, "rasterrelay-mask-1781220639504.png")).convert("L"), np.float32) / 255.0
mG = maskG > 0.5
Hg, Wg = srcG.shape[:2]
g2 = files("TEST_G2__")
finG = load(g2[-1])[:Hg, :Wg]
rawG = load(files("TEST_G2_raw")[-1])[:Hg, :Wg]
g = (finG[..., 1] - (finG[..., 0] + finG[..., 2]) / 2)[mG].mean()
deltaG = np.abs(rawG - srcG).max(-1)
driftG = mG & (deltaG < 0.05)
print("\n=== G2 zielone wlosy (Phase D) ===")
print(f"  green = {g:+.4f} (Phase B: +0.0230)   dryf tla = {(luma(finG)-luma(srcG))[driftG].mean():+.4f}")
print(f"  ostrosc maski: D={sharpness(finG, mG):.5f}")
Image.fromarray((np.concatenate([srcG, finG], 1) * 255).astype(np.uint8)).save(os.path.join(REP, "G2_phaseD_strip.png"))
print("\nsaved D_sharpness_zoom.png (orig|B|D), G2_phaseD_strip.png")
