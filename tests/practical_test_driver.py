"""RasterRelay practical test driver.

Runs the FULL production workflow (phases A-D + hotfixes) on an arbitrary image
with a generated mask, measures seam/intent/drift metrics, and saves a
side-by-side strip. Designed to be called repeatedly across test images.

Usage:
  python practical_test_driver.py --image NAME.jpg --prompt "..." \
      --mask center-ellipse --mask-frac 0.45 --seed 1234 --name case01

Prints one JSON line (params + metrics) to stdout on success.
"""
import argparse, json, os, sys, time, urllib.request, glob
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import distance_transform_edt, binary_dilation, binary_erosion

COMFY = "http://127.0.0.1:8188"
COMFY_IN = r"E:\AI\ComfyUI\input"
COMFY_OUT = r"E:\AI\ComfyUI\output\RasterRelay"
BASE = r"C:\Users\Mierz\Desktop\RasterRelay"
IMG_DIR = os.path.join(BASE, "tests", "manual", "test-images")
REP_DIR = os.path.join(BASE, "tests", "manual", "test-results", "practical")
PROD = os.path.join(BASE, "photoshop_plugin", "workflows", "inpainting-api.json")
MAX_DIM = 1024  # cap working crop for reasonable test speed


def optimal_gen_size(w, h, target_area=1152 * 1024, min_scale=0.5, max_scale=1.0, multiple=16):
    scale = min(max_scale, max(min_scale, (target_area / (w * h)) ** 0.5))
    gw = max(multiple, round((w * scale) / multiple) * multiple)
    gh = max(multiple, round((h * scale) / multiple) * multiple)
    return gw, gh, scale


def make_mask(W, H, kind, frac):
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    r = int(min(W, H) * frac / 2)
    cx, cy = W // 2, H // 2
    if kind == "center-ellipse":
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    elif kind == "center-rect":
        d.rectangle([cx - r, cy - r, cx + r, cy + r], fill=255)
    elif kind == "top":
        d.ellipse([cx - r, int(H * 0.30) - r, cx + r, int(H * 0.30) + r], fill=255)
    elif kind == "left":
        d.ellipse([int(W * 0.32) - r, cy - r, int(W * 0.32) + r, cy + r], fill=255)
    else:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    return m.filter(ImageFilter.GaussianBlur(max(6, r // 12)))


def post(path, payload):
    req = urllib.request.Request(COMFY + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))


def wait(pid, timeout=400):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            h = json.load(urllib.request.urlopen(f"{COMFY}/history/{pid}"))
            if pid in h and h[pid].get("status", {}).get("status_str"):
                return h[pid]["status"]["status_str"]
        except Exception:
            pass
        time.sleep(5)
    return "timeout"


def newest(prefix):
    fs = sorted(glob.glob(os.path.join(COMFY_OUT, prefix + "*.png")), key=os.path.getmtime)
    return fs[-1] if fs else None


def luma(x): return 0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--mask", default="center-ellipse")
    ap.add_argument("--mask-frac", type=float, default=0.45)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--name", required=True)
    a = ap.parse_args()

    os.makedirs(REP_DIR, exist_ok=True)
    src_path = os.path.join(IMG_DIR, a.image)
    if not os.path.exists(src_path):
        print(json.dumps({"name": a.name, "error": f"image not found: {a.image}"})); sys.exit(1)

    img = Image.open(src_path).convert("RGB")
    # scale so max dim <= MAX_DIM, dims multiple of 16
    sc = min(1.0, MAX_DIM / max(img.size))
    W = max(16, int(img.width * sc) // 16 * 16)
    H = max(16, int(img.height * sc) // 16 * 16)
    crop = img.resize((W, H), Image.LANCZOS)
    crop.save(os.path.join(COMFY_IN, f"PRACT_{a.name}_src.png"))
    mask = make_mask(W, H, a.mask, a.mask_frac)
    Image.merge("RGB", (mask, mask, mask)).save(os.path.join(COMFY_IN, f"PRACT_{a.name}_mask.png"))

    GW, GH, scale = optimal_gen_size(W, H)
    wf = json.load(open(PROD, encoding="utf-8"))
    wf["10"]["inputs"]["image"] = f"PRACT_{a.name}_src.png"
    wf["11"]["inputs"]["image"] = f"PRACT_{a.name}_mask.png"
    wf["31"]["inputs"]["text"] = a.prompt
    wf["60"]["inputs"]["noise_seed"] = a.seed
    wf["60"]["inputs"]["randomize_seed"] = "disable"
    for nid in ("21", "62", "14", "15", "17"):
        wf[nid]["inputs"]["width"] = GW; wf[nid]["inputs"]["height"] = GH
    for nid in ("16", "18"):
        wf[nid]["inputs"]["width"] = W; wf[nid]["inputs"]["height"] = H
    for k, v in {"crop_left": 0, "crop_top": 0, "crop_width": W, "crop_height": H,
                 "doc_width": W, "doc_height": H}.items():
        wf["91"]["inputs"][k] = v
    wf["96"]["inputs"]["tone_radius"] = max(16, min(200, round(min(W, H) / 8)))
    wf["97"]["inputs"]["tone_radius"] = max(32, min(320, round(min(W, H) / 3)))
    wf["80"]["inputs"]["filename_prefix"] = f"RasterRelay/PRACT_{a.name}_"
    wf["82"] = {"class_type": "RasterRelaySaveImage",
                "inputs": {"images": ["16", 0], "filename_prefix": f"RasterRelay/PRACT_{a.name}_raw"}}

    t0 = time.time()
    r = post("/prompt", {"prompt": wf})
    if r.get("node_errors"):
        print(json.dumps({"name": a.name, "error": "node_errors", "detail": r["node_errors"]})); sys.exit(1)
    status = wait(r["prompt_id"])
    gen_s = round(time.time() - t0, 1)
    if status != "success":
        print(json.dumps({"name": a.name, "error": f"status={status}"})); sys.exit(1)

    s = np.asarray(crop, np.float32) / 255.0
    fin = np.asarray(Image.open(newest(f"PRACT_{a.name}_")).convert("RGB"), np.float32)[:H, :W] / 255.0
    rawf = newest(f"PRACT_{a.name}_raw")
    raw = np.asarray(Image.open(rawf).convert("RGB"), np.float32)[:H, :W] / 255.0 if rawf else fin
    mk = np.asarray(mask, np.float32) / 255.0
    m = mk > 0.5
    outer = binary_dilation(m, iterations=25) & ~m
    inner = m & ~binary_erosion(m, iterations=25)
    sd = np.where(m, distance_transform_edt(m), -distance_transform_edt(~m))
    bins = np.arange(-40, 42, 2); centers = (bins[:-1] + bins[1:]) / 2
    prof = np.array([luma(fin)[(sd >= b0) & (sd < b1)].mean() if ((sd >= b0) & (sd < b1)).any() else np.nan
                     for b0, b1 in zip(bins[:-1], bins[1:])])
    near = np.abs(centers) <= 12
    seam_step = float(np.nanmax(np.abs(np.diff(prof))[near[:-1] & near[1:]]))
    delta_raw = np.abs(raw - s).max(-1)
    intent = m & (delta_raw > 0.15)
    metrics = {
        "dL_seam": round(float(abs(luma(fin)[inner].mean() - luma(fin)[outer].mean())), 4),
        "dRGB_seam": round(float(np.abs(fin[inner].mean(0) - fin[outer].mean(0)).mean()), 4),
        "seam_step": round(seam_step, 4),
        "outside_mask_change": round(float(np.abs(fin - s).max(-1)[mk <= 0.02].mean()), 5),
        "intent_preserved": round(float(np.abs(fin - raw).max(-1)[intent].mean()) if intent.any() else 0.0, 4),
    }
    strip = np.concatenate([s, fin], 1)
    Image.fromarray((strip * 255).astype(np.uint8)).save(os.path.join(REP_DIR, f"{a.name}.png"))

    out = {"name": a.name, "image": a.image, "prompt": a.prompt, "mask": a.mask,
           "mask_frac": a.mask_frac, "seed": a.seed, "native": f"{W}x{H}",
           "gen": f"{GW}x{GH}", "gen_scale": round(scale, 3), "gen_seconds": gen_s,
           "metrics": metrics, "strip": os.path.join(REP_DIR, f"{a.name}.png")}
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
