"""
Test z rozniejszym GrainTransfer (strength=1.0) zeby pokazac efekt dodawania ziarna.
"""
import json
import requests
import time
import numpy as np
from PIL import Image
from scipy import ndimage

COMFYUI_URL = "http://127.0.0.1:8188"

def enqueue_workflow(workflow):
    r = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow, "disable_random_seed": True})
    r.raise_for_status()
    return r.json()["prompt_id"]

def wait_for_completion(prompt_id, timeout=120):
    start = time.time()
    while time.time() - start < timeout:
        r = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
        if r.status_code == 200:
            data = r.json()
            if prompt_id in data:
                status = data[prompt_id].get("status", {})
                if status.get("completed", False):
                    return data[prompt_id]
        time.sleep(1)
    raise TimeoutError()

def get_output_image(history, node_id=80):
    outputs = history.get("outputs", {})
    node_output = outputs.get(str(node_id), {})
    images = node_output.get("images", [])
    if images:
        return images[0]["filename"]
    return None

def download_output_image(filename):
    params = {"filename": filename, "subfolder": "", "type": "output"}
    r = requests.get(f"{COMFYUI_URL}/view", params=params, stream=True)
    r.raise_for_status()
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        for chunk in r.iter_content(chunk_size=8192):
            tmp.write(chunk)
        tmp_path = tmp.name
    return Image.open(tmp_path).convert("RGB")

# Pipeline z GrainTransfer strength=1.0 (pelne ziarno)
PIPELINE_FULL_GRAIN = {
    "10": {"class_type": "LoadImage", "inputs": {"image": "RASTERRELAY_SOURCE.png"}},
    "11": {"class_type": "LoadImageMask", "inputs": {"channel": "red", "image": "RASTERRELAY_MASK.png"}},
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
    "80": {"class_type": "RasterRelaySaveImage", "inputs": {"filename_prefix": "full_grain", "images": ["95", 0]}},
    "90": {"class_type": "RasterRelayLoraStack", "inputs": {"clip": ["30", 0], "loras_json": "[]", "model": ["21", 0]}},
    "96": {"class_type": "RasterRelayColorMatch", "inputs": {"method": "reinhard_lab", "preserve_luminance": True, "reference_image": ["10", 0], "strength": 0.85, "target_image": ["65", 0]}},
    "97": {"class_type": "RasterRelayGrainTransfer", "inputs": {"blur_radius": 3, "edge_feather": 20, "generated_image": ["96", 0], "grain_strength": 1.0, "mask": ["11", 0], "original_image": ["10", 0], "preserve_luminance": True}},
    "94": {"class_type": "RasterRelayVaeDriftMatch", "inputs": {"blend_radius": 12, "generated_crop": ["97", 0], "mask": ["11", 0], "mask_mode": "soft", "original_crop": ["10", 0], "restore_unmasked": True}},
    "95": {"class_type": "RasterRelayColorHarmonize", "inputs": {"blend_radius": 20, "edge_boost": 1.2, "generated_image": ["94", 0], "interior_weight": 0.6, "margin": 30, "mask": ["11", 0], "original_image": ["10", 0], "strength": 0.85}},
}

# Pipeline BEZ GrainTransfer (zeby pokazac roznice)
PIPELINE_NO_GRAIN = {
    "10": {"class_type": "LoadImage", "inputs": {"image": "RASTERRELAY_SOURCE.png"}},
    "11": {"class_type": "LoadImageMask", "inputs": {"channel": "red", "image": "RASTERRELAY_MASK.png"}},
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
    "80": {"class_type": "RasterRelaySaveImage", "inputs": {"filename_prefix": "no_grain", "images": ["95", 0]}},
    "90": {"class_type": "RasterRelayLoraStack", "inputs": {"clip": ["30", 0], "loras_json": "[]", "model": ["21", 0]}},
    "96": {"class_type": "RasterRelayColorMatch", "inputs": {"method": "reinhard_lab", "preserve_luminance": True, "reference_image": ["10", 0], "strength": 0.85, "target_image": ["65", 0]}},
    # NO GrainTransfer - VaeDriftMatch takes directly from ColorMatch
    "94": {"class_type": "RasterRelayVaeDriftMatch", "inputs": {"blend_radius": 12, "generated_crop": ["96", 0], "mask": ["11", 0], "mask_mode": "soft", "original_crop": ["10", 0], "restore_unmasked": True}},
    "95": {"class_type": "RasterRelayColorHarmonize", "inputs": {"blend_radius": 20, "edge_boost": 1.2, "generated_image": ["94", 0], "interior_weight": 0.6, "margin": 30, "mask": ["11", 0], "original_image": ["10", 0], "strength": 0.85}},
}

print("=" * 70)
print("TEST: Z vs BEZ GrainTransfer")
print("=" * 70)

# Run without grain
print("\n[1/4] Uruchamianie pipeline BEZ GrainTransfer...")
no_grain_id = enqueue_workflow(PIPELINE_NO_GRAIN)
no_grain_history = wait_for_completion(no_grain_id)
no_grain_filename = get_output_image(no_grain_history)
no_grain_img = download_output_image(no_grain_filename)
print(f"  Zakonczono: {no_grain_filename}")

# Run with full grain
print("\n[2/4] Uruchamianie pipeline Z GrainTransfer (strength=1.0)...")
full_grain_id = enqueue_workflow(PIPELINE_FULL_GRAIN)
full_grain_history = wait_for_completion(full_grain_id)
full_grain_filename = get_output_image(full_grain_history)
full_grain_img = download_output_image(full_grain_filename)
print(f"  Zakonczono: {full_grain_filename}")

# Load mask
mask = np.array(Image.open(r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images\rr-04-car-logo-clean-panel-0131279d-mask.png").convert("L")) > 128

# Convert to numpy
no_grain_arr = np.array(no_grain_img, dtype=np.float32)
full_grain_arr = np.array(full_grain_img, dtype=np.float32)

# Compute texture variance in generated area
print("\n[3/4] Analiza tekstury w wygenerowanym obszarze...")

def compute_texture(img_arr, mask, iterations=10):
    """Compute local variance in generated area."""
    gen_region = mask & ndimage.binary_erosion(mask, iterations=iterations)
    if gen_region.sum() < 100:
        return 0

    gray = img_arr.mean(axis=2)
    ys, xs = np.where(gen_region)
    vars = []
    for i in range(0, len(ys), 5):
        y, x = ys[i], xs[i]
        patch = gray[max(0,y-4):y+5, max(0,x-4):x+5]
        if patch.shape == (9, 9):
            vars.append(patch.var())
    return np.mean(vars) if vars else 0

no_grain_texture = compute_texture(no_grain_arr, mask)
full_grain_texture = compute_texture(full_grain_arr, mask)

print(f"   BEZ GrainTransfer: wariancja = {no_grain_texture:.1f}")
print(f"   Z GrainTransfer:   wariancja = {full_grain_texture:.1f}")
print(f"   Roznica: {((full_grain_texture - no_grain_texture) / no_grain_texture * 100):.1f}%")

# Save images
no_grain_img.save(r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images\grain_test_no_grain.png")
full_grain_img.save(r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images\grain_test_full_grain.png")

print("\n[4/4] Zapisano obrazy:")
print("   grain_test_no_grain.png (bez GrainTransfer)")
print("   grain_test_full_grain.png (z GrainTransfer strength=1.0)")

# Summary
print("\n" + "=" * 70)
if full_grain_texture > no_grain_texture * 1.05:
    print(f"KONKLUZJA: GrainTransfer dodaje {((full_grain_texture - no_grain_texture) / no_grain_texture * 100):.1f}% wiecej tekstury/ziarna")
    print("To eliminuje 'plastyczny' wyglad AI-generated obrazu.")
else:
    print("KONKLUZJA: GrainTransfer nie dodaje wystarczajaco tekstury")
print("=" * 70)
