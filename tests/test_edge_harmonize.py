"""
Test generowania obrazów z RasterRelayEdgeHarmonize.
Porównuje wyniki przed i po dodaniu EdgeHarmonize na różnych obrazach.
"""
import json
import requests
import time
import numpy as np
from PIL import Image
from scipy import ndimage
import os

COMFYUI_URL = "http://127.0.0.1:8188"

# Test images directory
TEST_DIR = r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images"
os.makedirs(TEST_DIR, exist_ok=True)

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

def download_output_image(filename, save_path):
    """Download image from ComfyUI output directory."""
    params = {"filename": filename, "subfolder": "", "type": "output"}
    r = requests.get(f"{COMFYUI_URL}/view", params=params, stream=True)
    r.raise_for_status()
    with open(save_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    return Image.open(save_path).convert("RGB")

def create_test_workflow(source_image, mask_image, prompt, negative_prompt, seed, include_edge_harmonize=True):
    """Create a test workflow with or without EdgeHarmonize."""
    workflow = {
        "10": {"class_type": "LoadImage", "inputs": {"image": source_image}},
        "11": {"class_type": "LoadImageMask", "inputs": {"channel": "red", "image": mask_image}},
        "20": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "flux-2-klein-9b-Q4_K_M.gguf"}},
        "21": {"class_type": "ModelSamplingFlux", "inputs": {"base_shift": 0.5, "height": 400, "max_shift": 1.15, "model": ["20", 0], "width": 800}},
        "30": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_8b_fp8mixed.safetensors", "type": "flux2"}},
        "31": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["90", 1], "text": prompt}},
        "32": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["90", 1], "text": negative_prompt}},
        "40": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
        "41": {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["40", 0]}},
        "42": {"class_type": "SetLatentNoiseMask", "inputs": {"mask": ["11", 0], "samples": ["41", 0]}},
        "51": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["31", 0], "latent": ["41", 0]}},
        "52": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["32", 0], "latent": ["41", 0]}},
        "60": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "61": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "62": {"class_type": "Flux2Scheduler", "inputs": {"height": 400, "steps": 14, "width": 800}},
        "63": {"class_type": "CFGGuider", "inputs": {"cfg": 1, "model": ["90", 0], "negative": ["52", 0], "positive": ["51", 0]}},
        "64": {"class_type": "SamplerCustomAdvanced", "inputs": {"guider": ["63", 0], "latent_image": ["42", 0], "noise": ["60", 0], "sampler": ["61", 0], "sigmas": ["62", 0]}},
        "65": {"class_type": "VAEDecode", "inputs": {"samples": ["64", 0], "vae": ["40", 0]}},
        "90": {"class_type": "RasterRelayLoraStack", "inputs": {"clip": ["30", 0], "loras_json": "[]", "model": ["21", 0]}},
        "96": {"class_type": "RasterRelayColorMatch", "inputs": {"method": "reinhard_lab", "preserve_luminance": True, "reference_image": ["10", 0], "strength": 0.85, "target_image": ["65", 0]}},
        "97": {"class_type": "RasterRelayGrainTransfer", "inputs": {"blur_radius": 3, "edge_feather": 20, "generated_image": ["96", 0], "grain_strength": 0.8, "mask": ["11", 0], "original_image": ["10", 0], "preserve_luminance": True}},
        "94": {"class_type": "RasterRelayVaeDriftMatch", "inputs": {"blend_radius": 12, "generated_crop": ["97", 0], "mask": ["11", 0], "mask_mode": "soft", "original_crop": ["10", 0], "restore_unmasked": True}},
        "95": {"class_type": "RasterRelayColorHarmonize", "inputs": {"blend_radius": 20, "edge_boost": 1.2, "generated_image": ["94", 0], "interior_weight": 0.6, "margin": 30, "mask": ["11", 0], "original_image": ["10", 0], "strength": 0.85}},
    }

    if include_edge_harmonize:
        workflow["98"] = {"class_type": "RasterRelayEdgeHarmonize", "inputs": {"edge_width": 20, "generated_image": ["95", 0], "mask": ["11", 0], "original_image": ["10", 0], "strength": 0.9}}
        workflow["80"] = {"class_type": "RasterRelaySaveImage", "inputs": {"filename_prefix": "with_edge", "images": ["98", 0]}}
    else:
        workflow["80"] = {"class_type": "RasterRelaySaveImage", "inputs": {"filename_prefix": "without_edge", "images": ["95", 0]}}

    return workflow

def compute_edge_metrics(original_path, result_path, mask_path):
    """Compute edge quality metrics."""
    orig = np.array(Image.open(original_path).convert("RGB"))
    result = np.array(Image.open(result_path).convert("RGB"))
    mask = np.array(Image.open(mask_path).convert("L")) > 128

    # Get edge zone (20px inside mask)
    eroded = ndimage.binary_erosion(mask, iterations=20)
    edge_zone = mask & ~eroded

    def luma(img):
        return img.mean(axis=2)

    orig_luma = luma(orig)
    result_luma = luma(result)

    # Luminance difference at edge
    edge_luma_diff = np.abs(result_luma[edge_zone] - orig_luma[edge_zone]).mean()

    # Color difference at edge (RGB)
    edge_color_diff = np.abs(result[edge_zone].astype(float) - orig[edge_zone].astype(float)).mean()

    # Global difference
    global_diff = np.abs(result.astype(float) - orig.astype(float)).mean()

    return {
        "edge_luma_diff": edge_luma_diff,
        "edge_color_diff": edge_color_diff,
        "global_diff": global_diff,
    }

def main():
    print("=" * 70)
    print("TEST GENEROWANIA OBRAZÓW Z RASTERRELAYEDGEHARMONIZE")
    print("=" * 70)

    # Test configuration
    test_cases = [
        {
            "name": "car_logo",
            "source": r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images\rr-04-car-logo-clean-panel-0131279d-source.png",
            "mask": r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images\rr-04-car-logo-clean-panel-0131279d-mask.png",
            "prompt": "Edit the masked area only. Keep the result photorealistic and naturally integrated with the original image. Match perspective, lighting, shadows, exposure, color temperature, contrast, grain, texture sharpness and depth of field. Preserve unmasked areas exactly. Avoid visible seams, halos, pasted-on edges and color shifts.",
            "negative_prompt": "blurry, distortion, visible seam, halo, pasted edge, color mismatch, exposure mismatch, different lighting, watermark, text, low quality, jpeg artifacts, oversaturated, undersaturated",
            "seed": 42,
        },
    ]

    results = []

    for i, test_case in enumerate(test_cases):
        print(f"\n[{i+1}/{len(test_cases)}] Test: {test_case['name']}")
        print("-" * 70)

        # Upload images
        source_filename = f"test_{test_case['name']}_source.png"
        mask_filename = f"test_{test_case['name']}_mask.png"
        upload_image(test_case["source"], source_filename)
        upload_image(test_case["mask"], mask_filename)

        # Run WITHOUT EdgeHarmonize
        print("  [1/4] Generowanie BEZ EdgeHarmonize...")
        workflow_without = create_test_workflow(
            source_filename, mask_filename,
            test_case["prompt"], test_case["negative_prompt"],
            test_case["seed"], include_edge_harmonize=False
        )
        prompt_id = enqueue_workflow(workflow_without)
        history = wait_for_completion(prompt_id)
        filename = get_output_image(history)
        without_path = os.path.join(TEST_DIR, f"{test_case['name']}_without_edge.png")
        download_output_image(filename, without_path)
        print(f"  Zapisano: {without_path}")

        # Run WITH EdgeHarmonize
        print("  [2/4] Generowanie Z EdgeHarmonize...")
        workflow_with = create_test_workflow(
            source_filename, mask_filename,
            test_case["prompt"], test_case["negative_prompt"],
            test_case["seed"], include_edge_harmonize=True
        )
        prompt_id = enqueue_workflow(workflow_with)
        history = wait_for_completion(prompt_id)
        filename = get_output_image(history)
        with_path = os.path.join(TEST_DIR, f"{test_case['name']}_with_edge.png")
        download_output_image(filename, with_path)
        print(f"  Zapisano: {with_path}")

        # Compute metrics
        print("  [3/4] Obliczanie metryk...")
        metrics_without = compute_edge_metrics(test_case["source"], without_path, test_case["mask"])
        metrics_with = compute_edge_metrics(test_case["source"], with_path, test_case["mask"])

        print(f"  [4/4] Wyniki:")
        print(f"    BEZ EdgeHarmonize:")
        print(f"      - Różnica luminancji na krawędzi: {metrics_without['edge_luma_diff']:.2f}")
        print(f"      - Różnica koloru na krawędzi: {metrics_without['edge_color_diff']:.2f}")
        print(f"      - Różnica globalna: {metrics_without['global_diff']:.2f}")
        print(f"    Z EdgeHarmonize:")
        print(f"      - Różnica luminancji na krawędzi: {metrics_with['edge_luma_diff']:.2f}")
        print(f"      - Różnica koloru na krawędzi: {metrics_with['edge_color_diff']:.2f}")
        print(f"      - Różnica globalna: {metrics_with['global_diff']:.2f}")

        # Calculate improvements
        luma_improvement = ((metrics_without['edge_luma_diff'] - metrics_with['edge_luma_diff']) / metrics_without['edge_luma_diff'] * 100)
        color_improvement = ((metrics_without['edge_color_diff'] - metrics_with['edge_color_diff']) / metrics_without['edge_color_diff'] * 100)

        print(f"    POPRAWA:")
        print(f"      - Luminancja na krawędzi: {luma_improvement:.1f}%")
        print(f"      - Kolor na krawędzi: {color_improvement:.1f}%")

        results.append({
            "name": test_case["name"],
            "without": metrics_without,
            "with": metrics_with,
            "luma_improvement": luma_improvement,
            "color_improvement": color_improvement,
        })

    # Summary
    print("\n" + "=" * 70)
    print("PODSUMOWANIE TESTÓW")
    print("=" * 70)

    avg_luma_improvement = np.mean([r["luma_improvement"] for r in results])
    avg_color_improvement = np.mean([r["color_improvement"] for r in results])

    print(f"\nŚrednia poprawa dla {len(results)} testów:")
    print(f"  - Luminancja na krawędzi: {avg_luma_improvement:.1f}%")
    print(f"  - Kolor na krawędzi: {avg_color_improvement:.1f}%")

    print("\nSzczegółowe wyniki:")
    print(f"{'Test':<15} {'Luma bez':>10} {'Luma z':>10} {'Poprawa':>10} {'Kolor bez':>10} {'Kolor z':>10} {'Poprawa':>10}")
    print("-" * 75)
    for r in results:
        print(f"{r['name']:<15} {r['without']['edge_luma_diff']:>10.2f} {r['with']['edge_luma_diff']:>10.2f} {r['luma_improvement']:>9.1f}% {r['without']['edge_color_diff']:>10.2f} {r['with']['edge_color_diff']:>10.2f} {r['color_improvement']:>9.1f}%")

    print("\n" + "=" * 70)
    if avg_luma_improvement > 50:
        print("WNIOSK: EdgeHarmonize ZNACZNIE POPRAWIA jakość krawędzi")
    elif avg_luma_improvement > 20:
        print("WNIOSK: EdgeHarmonize POPRAWIA jakość krawędzi")
    else:
        print("WNIOSK: EdgeHarmonize ma NIEWIELKI wpływ na jakość krawędzi")
    print("=" * 70)

    print(f"\nWyniki zapisane w: {TEST_DIR}")
    print("  - *_without_edge.png - wyniki bez EdgeHarmonize")
    print("  - *_with_edge.png - wyniki z EdgeHarmonize")

    return results

if __name__ == "__main__":
    main()
