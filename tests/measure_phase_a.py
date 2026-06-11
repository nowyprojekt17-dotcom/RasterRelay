"""Unified seam metrics for Phase A variants vs existing baselines."""
import os, numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, binary_erosion

OUT = r"E:\AI\ComfyUI\output\RasterRelay"
INP = r"E:\AI\ComfyUI\input"

def load(p): return np.asarray(Image.open(p).convert("RGB"), np.float32) / 255.0
orig = load(os.path.join(INP, "RASTERRELAY_SOURCE.png"))
mask = np.asarray(Image.open(os.path.join(INP, "RASTERRELAY_MASK.png")).convert("L"), np.float32) / 255.0
m = mask > 0.5
outer = binary_dilation(m, iterations=25) & ~m
inner = m & ~binary_erosion(m, iterations=25)

def luma(x): return 0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]
ctx = luma(orig)[outer].mean()
print(f"CONTEXT ring target L = {ctx:.3f}\n")
print(f"{'variant':34}{'L_int':>7}{'dL_seam':>9}{'dRGB':>8}")

variants = [
    ("RAW (SetLatentNoiseMask)", "TEST_raw_00000_.png"),
    ("PROD post (VDM+SeamlessTone)", "TEST_new_00000_.png"),
    ("A1 raw  (DD)", "TEST_A1_raw_00000_.png"),
    ("A1 post (DD + prod post)", "TEST_A1__00000_.png"),
    ("A2 raw  (DD+IMC)", "TEST_A2_raw_00000_.png"),
    ("A2 post (DD+IMC + prod post)", "TEST_A2__00000_.png"),
]
for name, fn in variants:
    p = os.path.join(OUT, fn)
    if not os.path.exists(p):
        print(f"{name:34}  MISSING"); continue
    img = load(p)
    dl = abs(luma(img)[inner].mean() - luma(img)[outer].mean())
    dc = np.abs(img[inner].mean(0) - img[outer].mean(0)).mean()
    print(f"{name:34}{luma(img)[m].mean():7.3f}{dl:9.4f}{dc:8.4f}")

# comparison strips
REP = r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-results"
row_raw = np.concatenate([load(os.path.join(OUT, "TEST_raw_00000_.png")),
                          load(os.path.join(OUT, "TEST_A1_raw_00000_.png")),
                          load(os.path.join(OUT, "TEST_A2_raw_00000_.png"))], axis=1)
Image.fromarray((row_raw * 255).astype(np.uint8)).save(os.path.join(REP, "phaseA_raw_strip.png"))
row_post = np.concatenate([load(os.path.join(OUT, "TEST_new_00000_.png")),
                           load(os.path.join(OUT, "TEST_A1__00000_.png")),
                           load(os.path.join(OUT, "TEST_A2__00000_.png"))], axis=1)
Image.fromarray((row_post * 255).astype(np.uint8)).save(os.path.join(REP, "phaseA_post_strip.png"))
print("\nstrips: phaseA_raw_strip.png (raw|A1raw|A2raw), phaseA_post_strip.png (prod|A1|A2)")
