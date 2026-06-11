"""
Porównanie stary vs nowy pipeline postprocessingu RasterRelay.

Metryki:
1. Seam Score - różnica pikseli na krawędzi maski (im mniej tym lepiej)
2. Color Delta E - różnica kolorów między wygenerowanym a otoczeniem (im mniej tym lepiej)
3. Grain Variance - wariancja lokalna tekstury (im bliżej oryginału tym lepiej)
4. SSIM - strukturalne podobieństwo między wygenerowanym a otoczeniem (im więcej tym lepiej)
"""
import json
import torch
import numpy as np
from PIL import Image
import requests
import time
import os

COMFYUI_URL = "http://127.0.0.1:8188"
SOURCE_IMAGE = "RASTERRELAY_SOURCE.png"
MASK_IMAGE = "RASTERRELAY_MASK.png"

def upload_image(filepath, filename):
    """Upload image to ComfyUI input directory."""
    with open(filepath, "rb") as f:
        files = {"image": (filename, f)}
        data = {"filename": filename}
        r = requests.post(f"{COMFYUI_URL}/upload/image", files=files, data=data)
        r.raise_for_status()
    return filename

def enqueue_workflow(workflow, disable_random_seed=True):
    """Submit workflow to ComfyUI and return prompt_id."""
    payload = {"prompt": workflow, "disable_random_seed": disable_random_seed}
    r = requests.post(f"{COMFYUI_URL}/prompt", json=payload)
    r.raise_for_status()
    return r.json()["prompt_id"]

def wait_for_completion(prompt_id, timeout=120):
    """Wait for workflow to complete."""
    start = time.time()
    while time.time() - start < timeout:
        r = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
        if r.status_code == 200:
            data = r.json()
            if prompt_id in data:
                status = data[prompt_id].get("status", {})
                if status.get("completed", False):
                    return data[prompt_id]
                if status.get("status_str") == "error":
                    raise Exception(f"Workflow failed: {status}")
        time.sleep(1)
    raise TimeoutError(f"Workflow {prompt_id} did not complete in {timeout}s")

def get_output_image(history, node_id=80):
    """Get output image filename from history."""
    outputs = history.get("outputs", {})
    node_output = outputs.get(str(node_id), {})
    images = node_output.get("images", [])
    if images:
        return images[0]["filename"]
    return None

def download_output_image(filename, subfolder="", type="output"):
    """Download image from ComfyUI output directory."""
    params = {"filename": filename, "subfolder": subfolder, "type": type}
    r = requests.get(f"{COMFYUI_URL}/view", params=params, stream=True)
    r.raise_for_status()
    # Save to temp file and open
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        for chunk in r.iter_content(chunk_size=8192):
            tmp.write(chunk)
        tmp_path = tmp.name
    return Image.open(tmp_path).convert("RGB")

def load_mask(filepath):
    """Load mask as binary numpy array."""
    img = Image.open(filepath).convert("L")
    arr = np.array(img)
    return (arr > 128).astype(np.uint8)

def get_mask_boundary(mask, erosion_radius=2):
    """Get pixels at the boundary of the mask."""
    from scipy import ndimage
    eroded = ndimage.binary_erosion(mask, iterations=erosion_radius)
    boundary = mask & ~eroded
    return boundary

def compute_seam_score(image_arr, mask):
    """
    Compute seam score: mean absolute difference between
    generated area edge pixels and their immediate outside neighbors.
    Lower is better (smoother transition).
    """
    boundary = get_mask_boundary(mask, erosion_radius=1)
    outside_boundary = get_mask_boundary(1 - mask, erosion_radius=1)

    # Get pixels just inside and just outside the boundary
    from scipy import ndimage
    inside_pixels = []
    outside_pixels = []

    ys, xs = np.where(boundary)
    for y, x in zip(ys, xs):
        # Find nearest outside pixel
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                ny, nx = y + dy, x + dx
                if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1]:
                    if not mask[ny, nx]:  # outside
                        inside_pixels.append(image_arr[y, x])
                        outside_pixels.append(image_arr[ny, nx])
                        break
            else:
                continue
            break

    if not inside_pixels:
        return float("inf")

    inside = np.array(inside_pixels, dtype=np.float32)
    outside = np.array(outside_pixels, dtype=np.float32)
    diff = np.abs(inside - outside).mean()
    return diff

def compute_color_delta_e(image_arr, mask):
    """
    Compute mean Delta E (CIE76) between generated area and surrounding original area.
    Lower is better (better color match).
    """
    # Get mean color of generated area (interior)
    from scipy import ndimage
    eroded_mask = ndimage.binary_erosion(mask, iterations=5)
    dilated_mask = ndimage.binary_dilation(mask, iterations=5)

    generated_region = mask & ~eroded_mask  # ring just inside
    surrounding_region = ~mask & dilated_mask  # ring just outside

    if generated_region.sum() == 0 or surrounding_region.sum() == 0:
        return float("inf")

    gen_color = image_arr[generated_region].mean(axis=0)
    surr_color = image_arr[surrounding_region].mean(axis=0)

    # Simple Euclidean distance in RGB (approximation of Delta E)
    delta_e = np.sqrt(np.sum((gen_color - surr_color) ** 2))
    return delta_e

def compute_grain_variance(image_arr, mask, patch_size=8):
    """
    Compute local variance (grain measure) in generated vs original areas.
    Returns ratio: generated_variance / original_variance.
    Closer to 1.0 is better (matching grain).
    """
    from scipy import ndimage
    eroded_mask = ndimage.binary_erosion(mask, iterations=10)
    eroded_inv = ndimage.binary_erosion(1 - mask, iterations=10)

    gen_region = mask & eroded_mask
    orig_region = (~mask) & eroded_inv

    if gen_region.sum() < 100 or orig_region.sum() < 100:
        return float("inf")

    # Convert to grayscale for grain analysis
    gray = np.mean(image_arr, axis=2)

    # Compute local variance using sliding window
    def local_variance(arr, region, patch_size):
        ys, xs = np.where(region)
        variances = []
        for i in range(0, len(ys), 4):  # sample every 4th pixel
            y, x = ys[i], xs[i]
            y1, y2 = max(0, y - patch_size), min(arr.shape[0], y + patch_size)
            x1, x2 = max(0, x - patch_size), min(arr.shape[1], x + patch_size)
            patch = arr[y1:y2, x1:x2]
            variances.append(patch.var())
        return np.mean(variances) if variances else 0

    gen_var = local_variance(gray, gen_region, patch_size)
    orig_var = local_variance(gray, orig_region, patch_size)

    if orig_var == 0:
        return float("inf")
    return gen_var / orig_var

def compute_ssim_region(image_arr, mask):
    """
    Compute SSIM-like measure between generated area texture and original area texture.
    Uses local structure comparison.
    """
    from scipy import ndimage
    eroded_mask = ndimage.binary_erosion(mask, iterations=10)
    eroded_inv = ndimage.binary_erosion(1 - mask, iterations=10)

    gen_region = mask & eroded_mask
    orig_region = (~mask) & eroded_inv

    if gen_region.sum() < 100 or orig_region.sum() < 100:
        return 0.0

    gray = np.mean(image_arr, axis=2)

    # Compute edge density (Laplacian variance) as texture measure
    def edge_density(arr, region):
        ys, xs = np.where(region)
        densities = []
        for i in range(0, len(ys), 4):
            y, x = ys[i], xs[i]
            y1, y2 = max(1, y - 5), min(arr.shape[0] - 1, y + 5)
            x1, x2 = max(1, x - 5), min(arr.shape[1] - 1, x + 5)
            patch = arr[y1:y2, x1:x2]
            # Laplacian
            lap = np.abs(patch[1:-1, 1:-1] * 4 - patch[:-2, 1:-1] - patch[2:, 1:-1] - patch[1:-1, :-2] - patch[1:-1, 2:])
            densities.append(lap.mean())
        return np.mean(densities) if densities else 0

    gen_edge = edge_density(gray, gen_region)
    orig_edge = edge_density(gray, orig_region)

    if max(gen_edge, orig_edge) == 0:
        return 1.0 if gen_edge == orig_edge else 0.0

    # Ratio closer to 1.0 is better
    ratio = min(gen_edge, orig_edge) / max(gen_edge, orig_edge)
    return ratio


# Define old pipeline (before fixes)
OLD_PIPELINE = {
    "10": {"class_type": "LoadImage", "inputs": {"image": SOURCE_IMAGE}},
    "11": {"class_type": "LoadImageMask", "inputs": {"channel": "red", "image": MASK_IMAGE}},
    "20": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "flux-2-klein-9b-Q4_K_M.gguf"}},
    "21": {"class_type": "ModelSamplingFlux", "inputs": {"base_shift": 0.5, "height": 400, "max_shift": 1.15, "model": ["20", 0], "width": 800}},
    "30": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_8b_fp8mixed.safetensors", "type": "flux2"}},
    "31": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["90", 1], "text": "Edit the masked area only. Keep the result photorealistic and naturally integrated with the original image. Match perspective, lighting, shadows, exposure, color temperature, contrast, grain, texture sharpness and depth of field. Preserve unmasked areas exactly. Avoid visible seams, halos, pasted-on edges and color shifts."}},
    "32": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["90", 1], "text": "blurry, distortion, visible seam, halo, pasted edge, color mismatch, exposure mismatch, different lighting, watermark, text, low quality, jpeg artifacts, oversaturated, undersaturated"}},
    "40": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
    "41": {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["40", 0]}},
    "42": {"class_type": "SetLatentNoiseMask", "inputs": {"mask": ["11", 0], "samples": ["41", 0]}},
    "51": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["31", 0], "latent": ["41", 0]}},
    "52": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["32", 0], "latent": ["41", 0]}},
    "60": {"class_type": "RandomNoise", "inputs": {"noise_seed": 42}},
    "61": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
    "62": {"class_type": "Flux2Scheduler", "inputs": {"height": 400, "steps": 14, "width": 800}},
    "63": {"class_type": "CFGGuider", "inputs": {"cfg": 1, "model": ["90", 0], "negative": ["52", 0], "positive": ["51", 0]}},
    "64": {"class_type": "SamplerCustomAdvanced", "inputs": {"guider": ["63", 0], "latent_image": ["42", 0], "noise": ["60", 0], "sampler": ["61", 0], "sigmas": ["62", 0]}},
    "65": {"class_type": "VAEDecode", "inputs": {"samples": ["64", 0], "vae": ["40", 0]}},
    "80": {"class_type": "RasterRelaySaveImage", "inputs": {"filename_prefix": "compare_old", "images": ["95", 0]}},
    "90": {"class_type": "RasterRelayLoraStack", "inputs": {"clip": ["30", 0], "loras_json": "[]", "model": ["21", 0]}},
    # OLD: ColorMatch with strength=0.7, preserve_luminance=false
    "96": {"class_type": "RasterRelayColorMatch", "inputs": {"method": "reinhard_lab", "preserve_luminance": False, "reference_image": ["10", 0], "strength": 0.7, "target_image": ["65", 0]}},
    # OLD: No GrainTransfer - VaeDriftMatch takes directly from ColorMatch
    "94": {"class_type": "RasterRelayVaeDriftMatch", "inputs": {"blend_radius": 12, "generated_crop": ["96", 0], "mask": ["11", 0], "mask_mode": "soft", "original_crop": ["10", 0], "restore_unmasked": True}},
    # OLD: ColorHarmonize with interior_weight=0.25 (hardcoded), edge_boost=1.0 (no boost)
    "95": {"class_type": "RasterRelayColorHarmonize", "inputs": {"blend_radius": 20, "edge_boost": 1.0, "generated_image": ["94", 0], "interior_weight": 0.25, "margin": 30, "mask": ["11", 0], "original_image": ["10", 0], "strength": 0.7}},
}

# Define new pipeline (after fixes)
NEW_PIPELINE = {
    "10": {"class_type": "LoadImage", "inputs": {"image": SOURCE_IMAGE}},
    "11": {"class_type": "LoadImageMask", "inputs": {"channel": "red", "image": MASK_IMAGE}},
    "20": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "flux-2-klein-9b-Q4_K_M.gguf"}},
    "21": {"class_type": "ModelSamplingFlux", "inputs": {"base_shift": 0.5, "height": 400, "max_shift": 1.15, "model": ["20", 0], "width": 800}},
    "30": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_8b_fp8mixed.safetensors", "type": "flux2"}},
    "31": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["90", 1], "text": "Edit the masked area only. Keep the result photorealistic and naturally integrated with the original image. Match perspective, lighting, shadows, exposure, color temperature, contrast, grain, texture sharpness and depth of field. Preserve unmasked areas exactly. Avoid visible seams, halos, pasted-on edges and color shifts."}},
    "32": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["90", 1], "text": "blurry, distortion, visible seam, halo, pasted edge, color mismatch, exposure mismatch, different lighting, watermark, text, low quality, jpeg artifacts, oversaturated, undersaturated"}},
    "40": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
    "41": {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["40", 0]}},
    "42": {"class_type": "SetLatentNoiseMask", "inputs": {"mask": ["11", 0], "samples": ["41", 0]}},
    "51": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["31", 0], "latent": ["41", 0]}},
    "52": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["32", 0], "latent": ["41", 0]}},
    "60": {"class_type": "RandomNoise", "inputs": {"noise_seed": 42}},
    "61": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
    "62": {"class_type": "Flux2Scheduler", "inputs": {"height": 400, "steps": 14, "width": 800}},
    "63": {"class_type": "CFGGuider", "inputs": {"cfg": 1, "model": ["90", 0], "negative": ["52", 0], "positive": ["51", 0]}},
    "64": {"class_type": "SamplerCustomAdvanced", "inputs": {"guider": ["63", 0], "latent_image": ["42", 0], "noise": ["60", 0], "sampler": ["61", 0], "sigmas": ["62", 0]}},
    "65": {"class_type": "VAEDecode", "inputs": {"samples": ["64", 0], "vae": ["40", 0]}},
    "80": {"class_type": "RasterRelaySaveImage", "inputs": {"filename_prefix": "compare_new", "images": ["95", 0]}},
    "90": {"class_type": "RasterRelayLoraStack", "inputs": {"clip": ["30", 0], "loras_json": "[]", "model": ["21", 0]}},
    # NEW: ColorMatch with strength=0.85, preserve_luminance=True
    "96": {"class_type": "RasterRelayColorMatch", "inputs": {"method": "reinhard_lab", "preserve_luminance": True, "reference_image": ["10", 0], "strength": 0.85, "target_image": ["65", 0]}},
    # NEW: GrainTransfer between ColorMatch and VaeDriftMatch
    "97": {"class_type": "RasterRelayGrainTransfer", "inputs": {"blur_radius": 3, "edge_feather": 20, "generated_image": ["96", 0], "grain_strength": 0.8, "mask": ["11", 0], "original_image": ["10", 0], "preserve_luminance": True}},
    # NEW: VaeDriftMatch takes from GrainTransfer
    "94": {"class_type": "RasterRelayVaeDriftMatch", "inputs": {"blend_radius": 12, "generated_crop": ["97", 0], "mask": ["11", 0], "mask_mode": "soft", "original_crop": ["10", 0], "restore_unmasked": True}},
    # NEW: ColorHarmonize with interior_weight=0.6, edge_boost=1.2
    "95": {"class_type": "RasterRelayColorHarmonize", "inputs": {"blend_radius": 20, "edge_boost": 1.2, "generated_image": ["94", 0], "interior_weight": 0.6, "margin": 30, "mask": ["11", 0], "original_image": ["10", 0], "strength": 0.85}},
}


def main():
    print("=" * 70)
    print("POROWNANIE STARY vs NOWY PIPELINE POSTPROCESSINGU RASTERRELAY")
    print("=" * 70)

    # Upload images
    print("\n[1/6] Upload obrazow do ComfyUI...")
    upload_image(r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images\rr-04-car-logo-clean-panel-0131279d-source.png", SOURCE_IMAGE)
    upload_image(r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images\rr-04-car-logo-clean-panel-0131279d-mask.png", MASK_IMAGE)
    print("  OK")

    # Load mask for metrics
    mask = load_mask(r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images\rr-04-car-logo-clean-panel-0131279d-mask.png")
    print(f"  Maska: {mask.shape}, pixels wygenerowane: {mask.sum()}")

    # Run old pipeline
    print("\n[2/6] Uruchamianie STAREGO pipeline (before fixes)...")
    old_id = enqueue_workflow(OLD_PIPELINE)
    print(f"  Prompt ID: {old_id}")
    old_history = wait_for_completion(old_id)
    old_filename = get_output_image(old_history)
    print(f"  Zakonczono. Output: {old_filename}")

    # Run new pipeline
    print("\n[3/6] Uruchamianie NOWEGO pipeline (after fixes)...")
    new_id = enqueue_workflow(NEW_PIPELINE)
    print(f"  Prompt ID: {new_id}")
    new_history = wait_for_completion(new_id)
    new_filename = get_output_image(new_history)
    print(f"  Zakonczono. Output: {new_filename}")

    # Download images
    print("\n[4/6] Pobieranie wynikow...")
    old_img = download_output_image(old_filename)
    new_img = download_output_image(new_filename)
    old_arr = np.array(old_img, dtype=np.float32)
    new_arr = np.array(new_img, dtype=np.float32)
    print(f"  Stary: {old_arr.shape}, Nowy: {new_arr.shape}")

    # Compute metrics
    print("\n[5/6] Obliczanie metryk...")

    metrics = {}

    # 1. Seam Score
    old_seam = compute_seam_score(old_arr, mask)
    new_seam = compute_seam_score(new_arr, mask)
    metrics["Seam Score (nizsz = lepiej)"] = {
        "stary": old_seam,
        "nowy": new_seam,
        "poprawa": ((old_seam - new_seam) / old_seam * 100) if old_seam > 0 else 0
    }

    # 2. Color Delta E
    old_delta = compute_color_delta_e(old_arr, mask)
    new_delta = compute_color_delta_e(new_arr, mask)
    metrics["Color Delta E (nizsz = lepiej)"] = {
        "stary": old_delta,
        "nowy": new_delta,
        "poprawa": ((old_delta - new_delta) / old_delta * 100) if old_delta > 0 else 0
    }

    # 3. Grain Variance Ratio
    old_grain = compute_grain_variance(old_arr, mask)
    new_grain = compute_grain_variance(new_arr, mask)
    # Ideal ratio is 1.0, compute distance from ideal
    old_grain_dev = abs(old_grain - 1.0)
    new_grain_dev = abs(new_grain - 1.0)
    metrics["Grain Variance Ratio (blizej 1.0 = lepiej)"] = {
        "stary": old_grain,
        "nowy": new_grain,
        "odchylenie_stary": old_grain_dev,
        "odchylenie_nowy": new_grain_dev,
        "poprawa": ((old_grain_dev - new_grain_dev) / old_grain_dev * 100) if old_grain_dev > 0 else 0
    }

    # 4. Texture/Edge Density Match
    old_texture = compute_ssim_region(old_arr, mask)
    new_texture = compute_ssim_region(new_arr, mask)
    metrics["Texture Match (wyzsz = lepiej)"] = {
        "stary": old_texture,
        "nowy": new_texture,
        "poprawa": ((new_texture - old_texture) / old_texture * 100) if old_texture > 0 else 0
    }

    # Print results
    print("\n[6/6] WYNIKI:")
    print("=" * 70)
    print(f"{'Metryka':<35} {'Stary':>12} {'Nowy':>12} {'Poprawa':>12}")
    print("-" * 70)

    total_improvement = 0
    count = 0

    for name, data in metrics.items():
        old_val = data["stary"]
        new_val = data["nowy"]
        improvement = data["poprawa"]

        if "nizsz" in name.lower():
            better = new_val < old_val
        else:
            better = new_val > old_val

        status = "LEPIEJ" if better else "GORZEJ"
        print(f"{name:<35} {old_val:>12.4f} {new_val:>12.4f} {improvement:>11.1f}% {status}")

        if "poprawa" in data:
            total_improvement += improvement
            count += 1

    print("-" * 70)
    avg_improvement = total_improvement / count if count > 0 else 0
    print(f"{'SREDNIA POPRAWA':<35} {'':>12} {'':>12} {avg_improvement:>11.1f}%")
    print("=" * 70)

    # Save comparison images
    old_img.save(r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images\compare_old_result.png")
    new_img.save(r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images\compare_new_result.png")
    print(f"\nZapisano obrazy porownawcze:")
    print(f"  Stary: compare_old_result.png")
    print(f"  Nowy: compare_new_result.png")

    # Final verdict
    print("\n" + "=" * 70)
    if avg_improvement > 10:
        print(f"WNIOSK: Nowy pipeline jest WYRAZNIE LEPSZY (srednia poprawa: {avg_improvement:.1f}%)")
    elif avg_improvement > 0:
        print(f"WNIOSK: Nowy pipeline jest NIECO LEPSZY (srednia poprawa: {avg_improvement:.1f}%)")
    else:
        print(f"WNIOSK: Brak wyraznej poprawy (srednia zmiana: {avg_improvement:.1f}%)")
    print("=" * 70)

    return metrics


if __name__ == "__main__":
    main()
