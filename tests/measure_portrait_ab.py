"""Portrait A/B: PROD (no DD) vs A1 (DD) on the real hair-recolor inputs."""
import os, numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, binary_dilation, binary_erosion

OUT = r"E:\AI\ComfyUI\output\RasterRelay"
INP = r"E:\AI\ComfyUI\input"
REP = r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-results"

def load(p): return np.asarray(Image.open(p).convert("RGB"), np.float32) / 255.0
def luma(x): return 0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]

orig = load(os.path.join(INP, "rasterrelay-2026-06-11T22-27-04-203Z-source.png"))
mask = np.asarray(Image.open(os.path.join(INP, "rasterrelay-mask-1781216825242.png")).convert("L"), np.float32) / 255.0
m = mask > 0.5
sd = np.where(m, distance_transform_edt(m), -distance_transform_edt(~m))
bins = np.arange(-40, 42, 2); centers = (bins[:-1] + bins[1:]) / 2

def prof(img):
    L = luma(img); out = []
    for b0, b1 in zip(bins[:-1], bins[1:]):
        sel = (sd >= b0) & (sd < b1)
        out.append(L[sel].mean() if sel.any() else np.nan)
    return np.array(out)

def step(p):
    near = np.abs(centers) <= 12
    dif = np.abs(np.diff(p)); pairs = near[:-1] & near[1:]
    return np.nanmax(dif[pairs])

outer = binary_dilation(m, iterations=25) & ~m
inner = m & ~binary_erosion(m, iterations=25)

print(f"{'variant':24}{'L_int':>7}{'dL_seam':>9}{'seam_step':>10}")
print(f"{'ORIGINAL':24}{luma(orig)[m].mean():7.3f}{'-':>9}{step(prof(orig)):10.4f}")
imgs = {}
for name, fn in [("PROD (no DD)", "TEST_Pprod__00000_.png"), ("A1 (DD)", "TEST_PA1__00000_.png")]:
    img = load(os.path.join(OUT, fn)); imgs[name] = img
    dl = abs(luma(img)[inner].mean() - luma(img)[outer].mean())
    print(f"{name:24}{luma(img)[m].mean():7.3f}{dl:9.4f}{step(prof(img)):10.4f}")

a = imgs["PROD (no DD)"]; b = imgs["A1 (DD)"]
Image.fromarray((np.concatenate([orig, a, b], 1) * 255).astype(np.uint8)).save(os.path.join(REP, "portrait_AB_full.png"))

def zoom(img, y0, y1, x0, x1, s=3):
    c = (img[y0:y1, x0:x1] * 255).astype(np.uint8)
    return np.asarray(Image.fromarray(c).resize(((x1 - x0) * s, (y1 - y0) * s), Image.LANCZOS))

Image.fromarray(np.concatenate([zoom(i, 150, 330, 480, 610) for i in [orig, a, b]], 1)).save(os.path.join(REP, "portrait_AB_zoom_righthair.png"))
Image.fromarray(np.concatenate([zoom(i, 380, 520, 100, 300) for i in [orig, a, b]], 1)).save(os.path.join(REP, "portrait_AB_zoom_shoulder.png"))
print("strips saved (orig|PROD|DD): portrait_AB_full / zoom_righthair / zoom_shoulder")
