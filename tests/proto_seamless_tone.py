"""Prototype: low-frequency 'seamless tone' correction.

Idea: extrapolate the surrounding (unmasked) low-frequency color INTO the masked
region via normalized Gaussian blur, then shift the generated patch's low
frequency to that target. Preserves generated high-freq detail, fixes
brightness/color offset AND gradients. Compares seam metrics vs raw + old chain.
"""
import os, numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, binary_dilation, binary_erosion

OUT = r"E:\AI\ComfyUI\output\RasterRelay"
INP = r"E:\AI\ComfyUI\input"
REP = r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-results"

def load(p): return np.asarray(Image.open(p).convert("RGB"), np.float32)/255.0
orig = load(os.path.join(INP,"RASTERRELAY_SOURCE.png"))
raw  = load(os.path.join(OUT,"TEST_raw_00000_.png"))
base = load(os.path.join(OUT,"TEST_baseline_00000_.png"))
mask = np.asarray(Image.open(os.path.join(INP,"RASTERRELAY_MASK.png")).convert("L"),np.float32)/255.0

m = mask>0.5
outer = binary_dilation(m,iterations=25)&~m
inner = m&~binary_erosion(m,iterations=25)
def luma(x):return 0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2]
def seam(img):
    return abs(luma(img)[inner].mean()-luma(img)[outer].mean()), np.abs(img[inner].mean(0)-img[outer].mean(0)).mean()

def seamless_tone(generated, original, msoft, sigma, strength=1.0):
    """msoft: soft mask in [0,1], 1=generated region."""
    W = (1.0 - msoft)[...,None]                       # known = surroundings
    eps = 1e-4
    # extrapolate surrounding low-freq tone into the hole (normalized conv)
    num = np.stack([gaussian_filter(original[...,c]*W[...,0], sigma) for c in range(3)],-1)
    den = gaussian_filter(W[...,0], sigma)[...,None] + eps
    target_lf = num/den
    # generated own low frequency
    gen_lf = np.stack([gaussian_filter(generated[...,c], sigma) for c in range(3)],-1)
    correction = (target_lf - gen_lf)*strength
    out = generated + correction*msoft[...,None]
    return np.clip(out,0,1)

print(f"{'variant':28} {'L_interior':>10} {'dL_seam':>9} {'dRGB_seam':>10}")
ctxL = luma(orig)[outer].mean()
print(f"{'(context ring target L)':28} {ctxL:10.3f}")
for img,name in [(raw,'RAW decode'),(base,'OLD chain (AreaMatch+CH)')]:
    dl,dc=seam(img); print(f"{name:28} {luma(img)[m].mean():10.3f} {dl:9.4f} {dc:10.4f}")

best=None
for sigma in [25,40,60,90]:
    res=seamless_tone(raw,orig,mask,sigma)
    dl,dc=seam(res); Li=luma(res)[m].mean()
    print(f"{'seamless_tone sigma='+str(sigma):28} {Li:10.3f} {dl:9.4f} {dc:10.4f}")
    if best is None or dl<best[1]: best=(sigma,dl,res)

# save best visual + seam zoom
sigma,_,res=best
Image.fromarray((res*255).astype(np.uint8)).save(os.path.join(REP,"proto_seamless_full.png"))
ys,xs=np.where(m); y0,cx=ys.min(),(xs.min()+xs.max())//2
b=70; zy0,zy1,zx0,zx1=max(0,y0-b),y0+b,max(0,cx-b),cx+b
def zoom(img):
    z=(img[zy0:zy1,zx0:zx1]*255).astype(np.uint8)
    return Image.fromarray(z).resize(((zx1-zx0)*3,(zy1-zy0)*3),Image.NEAREST)
zoom(res).save(os.path.join(REP,"seam_seamless.png"))
print(f"\nBest sigma={sigma}. Wrote proto_seamless_full.png + seam_seamless.png")
