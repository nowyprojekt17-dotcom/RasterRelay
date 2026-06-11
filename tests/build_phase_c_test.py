"""E2E portrait test of the full Phase C chain (comparable with TEST_Pprod/TEST_PA1)."""
import json

SRC = "rasterrelay-2026-06-11T22-27-04-203Z-source.png"
MSK = "rasterrelay-mask-1781216825242.png"
PROMPT = "platinum blonde hair, natural studio light, photorealistic"
W, H = 624, 544

wf = json.load(open(r"C:\Users\Mierz\Desktop\RasterRelay\photoshop_plugin\workflows\inpainting-api.json", encoding="utf-8"))
wf["10"]["inputs"]["image"] = SRC
wf["11"]["inputs"]["image"] = MSK
wf["31"]["inputs"]["text"] = PROMPT
wf["60"]["inputs"]["noise_seed"] = 12345
wf["60"]["inputs"]["randomize_seed"] = "disable"
for nid in ("21", "62"):
    wf[nid]["inputs"]["width"] = W
    wf[nid]["inputs"]["height"] = H
for k, v in {"crop_left": 0, "crop_top": 0, "crop_width": W, "crop_height": H, "doc_width": W, "doc_height": H}.items():
    wf["91"]["inputs"][k] = v
# scale tone radii the way the plugin would: min/8 and min/3
wf["96"]["inputs"]["tone_radius"] = max(16, min(200, round(min(W, H) / 8)))   # 68
wf["97"]["inputs"]["tone_radius"] = max(32, min(320, round(min(W, H) / 3)))   # 181
wf["80"]["inputs"]["filename_prefix"] = "RasterRelay/TEST_PC_"

with open(r"C:\Users\Mierz\Desktop\RasterRelay\tests\_wf_PC.json", "w", encoding="utf-8") as f:
    json.dump({"prompt": wf}, f)
print("PC workflow written: tone_radius=%d chroma_radius=%d" % (wf["96"]["inputs"]["tone_radius"], wf["97"]["inputs"]["tone_radius"]))
