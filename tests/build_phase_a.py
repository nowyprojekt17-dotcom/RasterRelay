"""Phase A experiment: DifferentialDiffusion (A1) and +InpaintModelConditioning (A2).

Generates two API workflows on the same inputs/seed as the production tests so
seam metrics are directly comparable with TEST_new / TEST_raw baselines.
"""
import json

PROMPT = "a polished chrome front grille and bumper of a sports car, detailed, sharp focus"


def core(prefix, use_imc):
    wf = {
        "10": {"class_type": "LoadImage", "inputs": {"image": "RASTERRELAY_SOURCE.png", "upload": "image"}},
        "11": {"class_type": "LoadImageMask", "inputs": {"image": "RASTERRELAY_MASK.png", "channel": "red"}},
        "20": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "flux-2-klein-9b-Q4_K_M.gguf"}},
        "21": {"class_type": "ModelSamplingFlux", "inputs": {"model": ["20", 0], "max_shift": 1.15, "base_shift": 0.5, "width": 768, "height": 768}},
        "30": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_8b_fp8mixed.safetensors", "type": "flux2"}},
        "90": {"class_type": "RasterRelayLoraStack", "inputs": {"model": ["21", 0], "clip": ["30", 0], "loras_json": "[]"}},
        # A-novelty: DifferentialDiffusion patch on the model
        "22": {"class_type": "DifferentialDiffusion", "inputs": {"model": ["90", 0]}},
        "31": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["90", 1], "text": PROMPT}},
        "32": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["90", 1], "text": ""}},
        "40": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
        "41": {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["40", 0]}},
        "51": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["31", 0], "latent": ["41", 0]}},
        "52": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["32", 0], "latent": ["41", 0]}},
        "60": {"class_type": "RandomNoise", "inputs": {"noise_seed": 12345, "randomize_seed": "disable"}},
        "61": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "62": {"class_type": "Flux2Scheduler", "inputs": {"steps": 20, "width": 768, "height": 768}},
        "65": {"class_type": "VAEDecode", "inputs": {"samples": ["64", 0], "vae": ["40", 0]}},
        # post chain identical to production
        "94": {"class_type": "RasterRelayVaeDriftMatch", "inputs": {"original_crop": ["10", 0], "generated_crop": ["65", 0], "mask": ["11", 0], "blend_radius": 16, "restore_unmasked": True, "mask_mode": "soft"}},
        "96": {"class_type": "RasterRelaySeamlessTone", "inputs": {"original_image": ["10", 0], "generated_image": ["94", 0], "mask": ["11", 0], "tone_radius": 40, "strength": 1.0}},
        "91": {"class_type": "RasterRelayPadToDocument", "inputs": {"image": ["96", 0], "mask": ["11", 0], "crop_left": 0, "crop_top": 0, "crop_width": 768, "crop_height": 768, "doc_width": 768, "doc_height": 768, "alpha_mode": "crop"}},
        "80": {"class_type": "RasterRelaySaveImage", "inputs": {"images": ["91", 0], "filename_prefix": f"RasterRelay/{prefix}"}},
        "81": {"class_type": "RasterRelaySaveImage", "inputs": {"images": ["65", 0], "filename_prefix": f"RasterRelay/{prefix}raw"}},
    }
    if use_imc:
        # official inpaint path: conditioning(+ref) + vae + pixels + mask -> masked latent
        wf["43"] = {"class_type": "InpaintModelConditioning", "inputs": {
            "positive": ["51", 0], "negative": ["52", 0], "vae": ["40", 0],
            "pixels": ["10", 0], "mask": ["11", 0], "noise_mask": True}}
        wf["63"] = {"class_type": "CFGGuider", "inputs": {"model": ["22", 0], "positive": ["43", 0], "negative": ["43", 1], "cfg": 1}}
        wf["64"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["60", 0], "guider": ["63", 0], "sampler": ["61", 0], "sigmas": ["62", 0], "latent_image": ["43", 2]}}
    else:
        wf["42"] = {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["41", 0], "mask": ["11", 0]}}
        wf["63"] = {"class_type": "CFGGuider", "inputs": {"model": ["22", 0], "positive": ["51", 0], "negative": ["52", 0], "cfg": 1}}
        wf["64"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["60", 0], "guider": ["63", 0], "sampler": ["61", 0], "sigmas": ["62", 0], "latent_image": ["42", 0]}}
    return wf


base = r"C:\Users\Mierz\Desktop\RasterRelay\tests"
with open(base + r"\_wf_A1.json", "w", encoding="utf-8") as f:
    json.dump({"prompt": core("TEST_A1_", use_imc=False)}, f)
with open(base + r"\_wf_A2.json", "w", encoding="utf-8") as f:
    json.dump({"prompt": core("TEST_A2_", use_imc=True)}, f)
print("wrote _wf_A1.json (DD only) and _wf_A2.json (DD + InpaintModelConditioning)")
