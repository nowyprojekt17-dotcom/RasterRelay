"""Seam visibility as a luma profile across the mask boundary.

For each pixel we compute signed distance to the mask edge (negative = outside,
positive = inside) and average luma per 2px distance bin. A visible seam shows
as a kink/step in the profile; smooth monotone transition = invisible.
We report the max bin-to-bin jump near the boundary (|d| <= 12 px) as
'seam_step' — directly comparable across variants.
"""
import os, numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt

OUT = r"E:\AI\ComfyUI\output\RasterRelay"
INP = r"E:\AI\ComfyUI\input"

def load(p): return np.asarray(Image.open(p).convert("RGB"), np.float32) / 255.0
def luma(x): return 0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]

orig = load(os.path.join(INP, "RASTERRELAY_SOURCE.png"))
mask = np.asarray(Image.open(os.path.join(INP, "RASTERRELAY_MASK.png")).convert("L"), np.float32) / 255.0
m = mask > 0.5
# signed distance: + inside mask, - outside
d_in = distance_transform_edt(m)
d_out = distance_transform_edt(~m)
sd = np.where(m, d_in, -d_out)

bins = np.arange(-40, 42, 2)
def profile(img):
    L = luma(img)
    prof = []
    for b0, b1 in zip(bins[:-1], bins[1:]):
        sel = (sd >= b0) & (sd < b1)
        prof.append(L[sel].mean() if sel.any() else np.nan)
    return np.array(prof)

def seam_step(prof):
    centers = (bins[:-1] + bins[1:]) / 2
    near = np.abs(centers) <= 12
    dif = np.abs(np.diff(prof))
    near_pairs = near[:-1] & near[1:]
    return np.nanmax(dif[near_pairs])

variants = [
    ("ORIGINAL (no edit)", None),
    ("PROD (no DD)", "TEST_new_00000_.png"),
    ("A1 (DD)", "TEST_A1__00000_.png"),
]
print(f"{'variant':22}{'seam_step':>10}   (max luma jump within +/-12px of boundary)")
profs = {}
for name, fn in variants:
    img = orig if fn is None else load(os.path.join(OUT, fn))
    p = profile(img)
    profs[name] = p
    print(f"{name:22}{seam_step(p):10.4f}")

# also dump profiles around the boundary for inspection
centers = (bins[:-1] + bins[1:]) / 2
sel = np.abs(centers) <= 16
print("\ndist(px): " + " ".join(f"{c:6.0f}" for c in centers[sel]))
for name, p in profs.items():
    print(f"{name[:20]:20}: " + " ".join(f"{v:6.3f}" for v in p[sel]))
