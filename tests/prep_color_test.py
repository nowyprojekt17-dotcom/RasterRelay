"""Prepare a realistic color-consistency test input for RasterRelay.

Picks a real photo, extracts a 768x768 crop as the "source" the plugin would
send, and builds a centered soft mask (the "selection"). Saves both into
ComfyUI/input under the names the workflow's LoadImage/LoadImageMask expect.
"""
import os
import sys
from PIL import Image, ImageDraw, ImageFilter

IMG_DIR = r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images"
COMFY_INPUT = r"E:\AI\ComfyUI\input"
SIZE = 768            # crop size (multiple of 16)
MASK_BOX = 320        # centered selection size
FEATHER = 18          # soft edge

candidates = ["car-color-test.jpg", "P1075287.jpg", "61CiqMYiRPL._AC_UY1000_.jpg"]
src_path = None
for c in candidates:
    p = os.path.join(IMG_DIR, c)
    if os.path.exists(p):
        src_path = p
        break
if src_path is None:
    # fall back to first jpg/png
    for f in sorted(os.listdir(IMG_DIR)):
        if f.lower().endswith((".jpg", ".jpeg", ".png")):
            src_path = os.path.join(IMG_DIR, f)
            break

print("Source photo:", src_path)
img = Image.open(src_path).convert("RGB")
print("Original size:", img.size)

# center-crop the largest square, then resize to SIZE
w, h = img.size
s = min(w, h)
left = (w - s) // 2
top = (h - s) // 2
crop = img.crop((left, top, left + s, top + s)).resize((SIZE, SIZE), Image.LANCZOS)

os.makedirs(COMFY_INPUT, exist_ok=True)
crop.save(os.path.join(COMFY_INPUT, "RASTERRELAY_SOURCE.png"))

# centered soft mask: white selection on black, feathered
mask = Image.new("L", (SIZE, SIZE), 0)
d = ImageDraw.Draw(mask)
m0 = (SIZE - MASK_BOX) // 2
d.rectangle([m0, m0, m0 + MASK_BOX, m0 + MASK_BOX], fill=255)
mask = mask.filter(ImageFilter.GaussianBlur(FEATHER))
# store mask in RED channel (workflow reads LoadImageMask channel=red)
rgb_mask = Image.merge("RGB", (mask, mask, mask))
rgb_mask.save(os.path.join(COMFY_INPUT, "RASTERRELAY_MASK.png"))

print("Wrote RASTERRELAY_SOURCE.png and RASTERRELAY_MASK.png to", COMFY_INPUT)
print(f"crop={SIZE}x{SIZE} mask_box={MASK_BOX} feather={FEATHER}")
