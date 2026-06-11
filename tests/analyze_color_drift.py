"""Quantify and visualize the color/brightness drift at the inpaint seam.

Compares original vs raw decode vs color-corrected output inside the mask and
in a thin ring just outside it. Reports the brightness/color offset that makes
the generated patch 'stand out', and writes seam-zoom + diff visualizations.
"""
import numpy as np
from PIL import Image

OUT = r"E:\AI\ComfyUI\output\RasterRelay"
INP = r"E:\AI\ComfyUI\input"
REPORT = r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-results"
import os
os.makedirs(REPORT, exist_ok=True)

def load(p):
    return np.asarray(Image.open(p).convert("RGB"), dtype=np.float32) / 255.0

orig = load(os.path.join(INP, "RASTERRELAY_SOURCE.png"))
raw  = load(os.path.join(OUT, "TEST_raw_00000_.png"))
base = load(os.path.join(OUT, "TEST_baseline_00000_.png"))
mask = np.asarray(Image.open(os.path.join(INP, "RASTERRELAY_MASK.png")).convert("L"), dtype=np.float32) / 255.0

H, W = mask.shape
m = mask > 0.5                      # hard interior
# ring just OUTSIDE the mask (within ~25px): dilate hard mask, subtract
from scipy.ndimage import binary_dilation, binary_erosion
outer = binary_dilation(m, iterations=25) & ~m
inner_edge = m & ~binary_erosion(m, iterations=25)   # band just inside seam

def luma(img):  # Rec.709
    return 0.2126*img[...,0] + 0.7152*img[...,1] + 0.4126*0 + 0.0722*img[...,2]

def stats(img, region, label):
    L = luma(img)[region]
    r = img[...,0][region]; g = img[...,1][region]; b = img[...,2][region]
    return dict(label=label, L=L.mean(), R=r.mean(), G=g.mean(), B=b.mean())

print("=== Mean brightness (L) and RGB, per region ===")
print(f"{'region':22} {'L':>6} {'R':>6} {'G':>6} {'B':>6}")
for img,name in [(orig,'ORIG'),(raw,'RAW decode'),(base,'CORRECTED')]:
    s_in = stats(img, m, 'interior')
    print(f"{name+' interior':22} {s_in['L']:.3f} {s_in['R']:.3f} {s_in['G']:.3f} {s_in['B']:.3f}")
# the surrounding context is identical across images (outside mask restored), use orig
s_ring = stats(orig, outer, 'ring')
print(f"{'CONTEXT ring (orig)':22} {s_ring['L']:.3f} {s_ring['R']:.3f} {s_ring['G']:.3f} {s_ring['B']:.3f}")

print()
print("=== SEAM DISCONTINUITY: |mean(inner band) - mean(outer ring)| ===")
print("(lower = generated patch blends better with surroundings)")
for img,name in [(raw,'RAW decode'),(base,'CORRECTED')]:
    Li = luma(img)[inner_edge].mean()
    Lo = luma(img)[outer].mean()
    di = img.reshape(-1,3)
    inner_rgb = img[inner_edge].mean(0); outer_rgb = img[outer].mean(0)
    dL = abs(Li-Lo)
    dC = np.abs(inner_rgb-outer_rgb).mean()
    print(f"{name:14} ΔL_seam={dL:.4f}   ΔRGB_seam={dC:.4f}")

# --- visuals ---
# seam zoom: top edge of mask. find bbox
ys, xs = np.where(m)
y0,y1,x0,x1 = ys.min(), ys.max(), xs.min(), xs.max()
cx = (x0+x1)//2
band = 70
zy0 = max(0, y0-band); zy1 = min(H, y0+band)
zx0 = max(0, cx-band); zx1 = min(W, cx+band)
def zoom(img):
    z = (img[zy0:zy1, zx0:zx1]*255).astype(np.uint8)
    return Image.fromarray(z).resize(((zx1-zx0)*3,(zy1-zy0)*3), Image.NEAREST)
zoom(orig).save(os.path.join(REPORT,"seam_orig.png"))
zoom(raw).save(os.path.join(REPORT,"seam_raw.png"))
zoom(base).save(os.path.join(REPORT,"seam_corrected.png"))

# amplified diff of corrected vs orig (shows where/what changed, x4)
diff = np.clip(np.abs(base-orig)*4.0,0,1)
Image.fromarray((diff*255).astype(np.uint8)).save(os.path.join(REPORT,"diff_corrected_x4.png"))
print("\nWrote seam_orig/raw/corrected.png and diff_corrected_x4.png to test-results/")
