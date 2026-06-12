"""Measure the hotfix validation battery: G2 (intent), R1 (ghosts), B2 (regression)."""
import os, numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, binary_dilation, binary_erosion, gaussian_filter

OUT = r"E:\AI\ComfyUI\output\RasterRelay"
INP = r"E:\AI\ComfyUI\input"
REP = r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-results"

import glob
def newest(prefix):
    files = sorted(glob.glob(os.path.join(OUT, prefix + "*.png")), key=os.path.getmtime)
    assert files, f"no output for {prefix}"
    return files[-1]

def load(p): return np.asarray(Image.open(p).convert("RGB"), np.float32) / 255.0
def luma(x): return 0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]
def crop_to(img, h, w): return img[:h, :w]

# ---------- G2: green intent ----------
src = load(os.path.join(INP, "rasterrelay-2026-06-11T23-30-38-490Z-source.png"))
mask = np.asarray(Image.open(os.path.join(INP, "rasterrelay-mask-1781220639504.png")).convert("L"), np.float32) / 255.0
m = mask > 0.5
H, W = src.shape[:2]
raw = crop_to(load(newest("TEST_G2_raw")), H, W)
fin = crop_to(load(newest("TEST_G2__")), H, W)
def green(img): return (img[..., 1] - (img[..., 0] + img[..., 2]) / 2)[m].mean()
print("=== G2: zielone wlosy (intent preservation) ===")
print(f"  {'':16}{'L_in':>7}{'green':>9}")
print(f"  {'SOURCE':16}{luma(src)[m].mean():7.3f}{green(src):+9.4f}")
print(f"  {'RAW decode':16}{luma(raw)[m].mean():7.3f}{green(raw):+9.4f}")
print(f"  {'FINAL (fix)':16}{luma(fin)[m].mean():7.3f}{green(fin):+9.4f}   (stary lancuch: L 0.387, green -0.0017)")
band = (mask > 0.02) & (mask < 0.98)
print(f"  halo band dL = {luma(fin)[band].mean()-luma(src)[band].mean():+.4f}  (stary: +0.0377)")
Image.fromarray((np.concatenate([src, raw, fin], 1) * 255).astype(np.uint8)).save(os.path.join(REP, "G2_strip.png"))

# ---------- R1: necklace removal ghosts ----------
srcP = load(os.path.join(INP, "rasterrelay-2026-06-11T22-27-04-203Z-source.png"))
maskR = np.asarray(Image.open(os.path.join(INP, "removal-necklace-mask.png")).convert("L"), np.float32) / 255.0
mR = maskR > 0.5
Hp, Wp = srcP.shape[:2]
rawR = crop_to(load(newest("TEST_R1_raw")), Hp, Wp)
finR = crop_to(load(newest("TEST_R1__")), Hp, Wp)
# ghost metric: high-frequency of ORIGINAL (the necklace edges) correlated with
# high-frequency of the result inside the mask. 0 = no ghost.
def hf(img):
    L = luma(img)
    return L - gaussian_filter(L, 3)
hf_src, hf_fin, hf_raw = hf(srcP), hf(finR), hf(rawR)
sel = mR & (np.abs(hf_src) > 0.05)   # where the original has strong structure (chain)
def ghost_corr(hf_out):
    a, b = hf_src[sel], hf_out[sel]
    if a.std() < 1e-6 or b.std() < 1e-6: return 0.0
    return float(np.corrcoef(a, b)[0, 1])
print("\n=== R1: usuwanie naszyjnika (ghost contours) ===")
print(f"  structure pixels in mask: {sel.sum()}")
print(f"  ghost corr RAW   = {ghost_corr(hf_raw):+.3f}")
print(f"  ghost corr FINAL = {ghost_corr(hf_fin):+.3f}   (>0.3 = widoczny duch, ~0 = czysto)")
def zoom(img, y0, y1, x0, x1, s=3):
    c = (img[y0:y1, x0:x1] * 255).astype(np.uint8)
    return np.asarray(Image.fromarray(c).resize(((x1 - x0) * s, (y1 - y0) * s), Image.LANCZOS))
Image.fromarray(np.concatenate([zoom(i, 370, 520, 215, 380) for i in [srcP, rawR, finR]], 1)).save(os.path.join(REP, "R1_zoom.png"))

# ---------- B2: blonde regression ----------
maskB = np.asarray(Image.open(os.path.join(INP, "rasterrelay-mask-1781216825242.png")).convert("L"), np.float32) / 255.0
mB = maskB > 0.5
finB = crop_to(load(newest("TEST_B2__")), Hp, Wp)
sd = np.where(mB, distance_transform_edt(mB), -distance_transform_edt(~mB))
bins = np.arange(-40, 42, 2); centers = (bins[:-1] + bins[1:]) / 2
def prof(img):
    L = luma(img); out = []
    for b0, b1 in zip(bins[:-1], bins[1:]):
        s_ = (sd >= b0) & (sd < b1)
        out.append(L[s_].mean() if s_.any() else np.nan)
    return np.array(out)
def step(p):
    near = np.abs(centers) <= 12
    dif = np.abs(np.diff(p)); pairs = near[:-1] & near[1:]
    return np.nanmax(dif[pairs])
outerB = binary_dilation(mB, iterations=25) & ~mB
innerB = mB & ~binary_erosion(mB, iterations=25)
dl = abs(luma(finB)[innerB].mean() - luma(finB)[outerB].mean())
print("\n=== B2: blond regresja (stara chain: dL_seam 0.0105, seam_step 0.0019) ===")
print(f"  FINAL(fix): dL_seam = {dl:.4f}  seam_step = {step(prof(finB)):.4f}")
print("\nstrips: G2_strip.png (src|raw|final), R1_zoom.png (src|raw|final)")
