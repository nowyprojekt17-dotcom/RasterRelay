"""Validation battery for the intent-preserving hotfix.

Three cases on the new production graph:
  G2 - green hair recolor (intent preservation)   [seed 777]
  R1 - necklace removal (ghost contours)          [seed 4242]
  B2 - blonde recolor regression (seam metrics)   [seed 12345]
"""
import json, copy, os
from PIL import Image, ImageDraw, ImageFilter

COMFY_IN = r"E:\AI\ComfyUI\input"
BASE = r"C:\Users\Mierz\Desktop\RasterRelay"

prod = json.load(open(BASE + r"\photoshop_plugin\workflows\inpainting-api.json", encoding="utf-8"))

def optimal_gen_size(w, h, target_area=1152 * 1024, min_scale=0.5, max_scale=1.0, multiple=16):
    """Mirror of panel-helpers computeOptimalGenSize."""
    scale = min(max_scale, max(min_scale, (target_area / (w * h)) ** 0.5))
    gw = max(multiple, round((w * scale) / multiple) * multiple)
    gh = max(multiple, round((h * scale) / multiple) * multiple)
    return gw, gh


def variant(src, msk, prompt, seed, W, H, prefix, extra_saves=True):
    wf = copy.deepcopy(prod)
    wf["10"]["inputs"]["image"] = src
    wf["11"]["inputs"]["image"] = msk
    wf["31"]["inputs"]["text"] = prompt
    wf["60"]["inputs"]["noise_seed"] = seed
    wf["60"]["inputs"]["randomize_seed"] = "disable"
    GW, GH = optimal_gen_size(W, H)
    for nid in ("21", "62", "14", "15", "17"):     # generation resolution
        wf[nid]["inputs"]["width"] = GW
        wf[nid]["inputs"]["height"] = GH
    for nid in ("16", "18"):                        # back to native crop
        wf[nid]["inputs"]["width"] = W
        wf[nid]["inputs"]["height"] = H
    for k, v in {"crop_left": 0, "crop_top": 0, "crop_width": W, "crop_height": H,
                 "doc_width": W, "doc_height": H}.items():
        wf["91"]["inputs"][k] = v
    wf["96"]["inputs"]["tone_radius"] = max(16, min(200, round(min(W, H) / 8)))
    wf["97"]["inputs"]["tone_radius"] = max(32, min(320, round(min(W, H) / 3)))
    wf["80"]["inputs"]["filename_prefix"] = "RasterRelay/" + prefix
    if extra_saves:
        wf["82"] = {"class_type": "RasterRelaySaveImage",
                    "inputs": {"images": ["16", 0], "filename_prefix": "RasterRelay/" + prefix + "raw"}}
    print(f"  {prefix}: native {W}x{H} -> gen {GW}x{GH}")
    return wf

# --- R1: build a necklace-removal mask on the blonde portrait source ---
SRC_P = "rasterrelay-2026-06-11T22-27-04-203Z-source.png"
W, H = 624, 544
mask = Image.new("L", (W, H), 0)
d = ImageDraw.Draw(mask)
d.ellipse([225, 375, 370, 515], fill=255)   # covers chain + pendant
mask = mask.filter(ImageFilter.GaussianBlur(12))
Image.merge("RGB", (mask, mask, mask)).save(os.path.join(COMFY_IN, "removal-necklace-mask.png"))

cases = {
    "_wf_G2.json": variant("rasterrelay-2026-06-11T23-30-38-490Z-source.png",
                           "rasterrelay-mask-1781220639504.png",
                           "zielone wlosy, green hair", 777, 640, 528, "TEST_G2_"),
    "_wf_R1.json": variant(SRC_P, "removal-necklace-mask.png",
                           "bare chest and neck skin, no necklace, no jewelry, natural skin texture",
                           4242, W, H, "TEST_R1_"),
    "_wf_B2.json": variant(SRC_P, "rasterrelay-mask-1781216825242.png",
                           "platinum blonde hair, natural studio light, photorealistic",
                           12345, W, H, "TEST_B2_"),
}
for fn, wf in cases.items():
    with open(BASE + r"\tests\\" + fn, "w", encoding="utf-8") as f:
        json.dump({"prompt": wf}, f)
print("battery written:", ", ".join(cases))
