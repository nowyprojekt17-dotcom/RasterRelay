import json

wf = {
 "10": {"class_type": "LoadImage", "inputs": {"image": "RASTERRELAY_SOURCE.png", "upload": "image"}},
 "11": {"class_type": "LoadImageMask", "inputs": {"image": "RASTERRELAY_MASK.png", "channel": "red"}},
 "20": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "flux-2-klein-9b-Q4_K_M.gguf"}},
 "21": {"class_type": "ModelSamplingFlux", "inputs": {"model": ["20", 0], "max_shift": 1.15, "base_shift": 0.5, "width": 1024, "height": 1024}},
 "30": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_8b_fp8mixed.safetensors", "type": "flux2"}},
 "90": {"class_type": "RasterRelayLoraStack", "inputs": {"model": ["21", 0], "clip": ["30", 0], "loras_json": "[]"}},
 "22": {"class_type": "DifferentialDiffusion", "inputs": {"model": ["90", 0]}},
 "31": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["90", 1], "text": "RasterRelay inpainting"}},
 "32": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["90", 1], "text": ""}},
 "40": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
 "41": {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["40", 0]}},
 "42": {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["41", 0], "mask": ["11", 0]}},
 "51": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["31", 0], "latent": ["41", 0]}},
 "52": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["32", 0], "latent": ["41", 0]}},
 "60": {"class_type": "RandomNoise", "inputs": {"noise_seed": 0, "randomize_seed": "enable"}},
 "61": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
 "62": {"class_type": "Flux2Scheduler", "inputs": {"steps": 20, "width": 1024, "height": 1024}},
 "63": {"class_type": "CFGGuider", "inputs": {"model": ["22", 0], "positive": ["51", 0], "negative": ["52", 0], "cfg": 1}},
 "64": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["60", 0], "guider": ["63", 0], "sampler": ["61", 0], "sigmas": ["62", 0], "latent_image": ["42", 0]}},
 "65": {"class_type": "VAEDecode", "inputs": {"samples": ["64", 0], "vae": ["40", 0]}},
 # Phase C: edge-aware compositing mask. GUIDE = the GENERATED image (65), not
 # the original: for recolours the silhouette matches anyway, and for removals
 # the original object's edges must NOT pull the mask (ghost contours).
 "13": {"class_type": "RasterRelayMaskEdgeRefine", "inputs": {"image": ["65", 0], "mask": ["11", 0], "radius": 8, "edge_sensitivity": 0.02, "strength": 1.0}},
 "94": {"class_type": "RasterRelayVaeDriftMatch", "inputs": {"original_crop": ["10", 0], "generated_crop": ["65", 0], "mask": ["13", 0], "blend_radius": 16, "restore_unmasked": True, "mask_mode": "soft"}},
 # inside the mask: restore original where the model changed little (unintended
 # tone drift on background/skin -> mask-shaped stains); keep where it changed
 # a lot (the intended edit). Measured bimodal split: drift <0.05, intent >0.15.
 "95": {"class_type": "RasterRelayBackgroundPreserve", "inputs": {"original_image": ["10", 0], "generated_image": ["94", 0], "mask": ["13", 0], "object_luma_max": 0.58, "red_keep_threshold": 0.08, "blend_radius": 16, "change_keep_threshold": 0.10}},
 # intent-preserving: full correction only in the seam band; deep interior
 # keeps the model's intentional edit (recolours, removals, new objects)
 "96": {"class_type": "RasterRelaySeamlessTone", "inputs": {"original_image": ["10", 0], "generated_image": ["95", 0], "mask": ["13", 0], "tone_radius": 40, "strength": 1.0, "mode": "full", "interior_strength": 0.15, "seam_band": 24}},
 # Phase C: large-radius chroma-only pass kills residual colour cast AT THE SEAM ONLY
 "97": {"class_type": "RasterRelaySeamlessTone", "inputs": {"original_image": ["10", 0], "generated_image": ["96", 0], "mask": ["13", 0], "tone_radius": 120, "strength": 0.85, "mode": "chroma", "interior_strength": 0.0, "seam_band": 24}},
 # Phase C: photographic grain continuity (residual clamped so removed objects leave no ghost contours)
 "98": {"class_type": "RasterRelayGrainTransfer", "inputs": {"original_image": ["10", 0], "generated_image": ["97", 0], "mask": ["13", 0], "grain_strength": 0.8, "blur_radius": 3, "edge_feather": 16, "preserve_luminance": True, "grain_clip": 0.04}},
 "91": {"class_type": "RasterRelayPadToDocument", "inputs": {"image": ["98", 0], "mask": ["13", 0], "crop_left": 0, "crop_top": 0, "crop_width": 1024, "crop_height": 768, "doc_width": 1024, "doc_height": 768, "alpha_mode": "crop"}},
 "80": {"class_type": "RasterRelaySaveImage", "inputs": {"images": ["91", 0], "filename_prefix": "RasterRelay/inpainting"}},
}

mapping = {
 "status": "ready",
 "description": "RasterRelay Flux.2 Klein 9B GGUF inpainting. Seam-free colour via VaeDriftMatch + SeamlessTone (low-frequency tone diffusion).",
 "inputs": {
  "sourceImage": {"nodeId": "10", "inputName": "image"},
  "selectionMask": {"nodeId": "11", "inputName": "image"},
  "prompt": {"nodeId": "31", "inputName": "text"},
  "negativePrompt": {"nodeId": "32", "inputName": "text"},
  "steps": {"nodeId": "62", "inputName": "steps"},
  "cfg": {"nodeId": "63", "inputName": "cfg"},
  "seed": {"nodeId": "60", "inputName": "noise_seed"},
  "seedRandomize": {"nodeId": "60", "inputName": "randomize_seed"},
  "lorasJson": {"nodeId": "90", "inputName": "loras_json"},
  "width": [{"nodeId": "21", "inputName": "width"}, {"nodeId": "62", "inputName": "width"}],
  "height": [{"nodeId": "21", "inputName": "height"}, {"nodeId": "62", "inputName": "height"}],
  "cropLeft": {"nodeId": "91", "inputName": "crop_left"},
  "cropTop": {"nodeId": "91", "inputName": "crop_top"},
  "cropWidth": {"nodeId": "91", "inputName": "crop_width"},
  "cropHeight": {"nodeId": "91", "inputName": "crop_height"},
  "docWidth": {"nodeId": "91", "inputName": "doc_width"},
  "docHeight": {"nodeId": "91", "inputName": "doc_height"},
  "toneRadius": {"nodeId": "96", "inputName": "tone_radius"},
  "toneStrength": {"nodeId": "96", "inputName": "strength"},
  "chromaRadius": {"nodeId": "97", "inputName": "tone_radius"},
  "chromaStrength": {"nodeId": "97", "inputName": "strength"},
  "grainStrength": {"nodeId": "98", "inputName": "grain_strength"},
  "maskRefineStrength": {"nodeId": "13", "inputName": "strength"},
  "backgroundPreserveThreshold": {"nodeId": "95", "inputName": "change_keep_threshold"},
 },
 "notes": {
  "baseModel": "flux-2-klein-9b-Q4_K_M.gguf",
  "textEncoder": "qwen_3_8b_fp8mixed.safetensors",
  "vae": "flux2-vae.safetensors",
  "maskChannel": "LoadImageMask red channel. Plugin uploads the crop-local generation/denoise mask.",
  "architecture": "DifferentialDiffusion + VAEDecode -> [MaskEdgeRefine guides compositing] -> VaeDriftMatch -> SeamlessTone(full, ~crop/8) -> SeamlessTone(chroma-only, ~crop/3) -> GrainTransfer -> PadToDocument -> SaveImage.",
  "phaseC": "MaskEdgeRefine (guided filter) snaps the compositing mask to real image edges (hair strands keep their silhouette, no halo). Chroma-only SeamlessTone pass at large radius removes residual colour cast without touching luminance. GrainTransfer restores photographic grain so the patch shares the original's texture character. Generation/denoise path still uses the raw plugin mask (node 11) - refinement applies to compositing only.",
  "differentialDiffusion": "Model patch: soft mask becomes a per-pixel denoise gradient, so the model itself blends tone/texture progressively at the boundary. Measured -18% dL_seam / -22% seam_step on the hair-recolor case; neutral on easy cases. InpaintModelConditioning was tested and is a no-op for Flux2 Klein GGUF (pixel-identical output) - intentionally not used.",
  "colorPipeline": "VaeDriftMatch hard-restores original pixels outside the selection (zero VAE drift there). SeamlessTone then diffuses the surrounding low-frequency colour/brightness INTO the masked region and shifts only the generated low frequency to match it, fixing exposure/colour offset AND lighting gradients while preserving generated detail. Replaces the old global-Reinhard AreaMatch+ColorHarmonize chain, which measurably worsened the seam.",
  "tone_radius": "Gaussian sigma in px of the tone field. Plugin sets it to ~1/8 of the smaller crop dimension (about 1/4 of the selection radius).",
  "cfg": "1 recommended for FLUX models",
 },
}

base = r"C:\Users\Mierz\Desktop\RasterRelay\photoshop_plugin\workflows"
with open(base + r"\inpainting-api.json", "w", encoding="utf-8") as f:
    json.dump(wf, f, indent=2)
with open(base + r"\inpainting-api.mapping.json", "w", encoding="utf-8") as f:
    json.dump(mapping, f, indent=2)
print("wrote production workflow (", len(wf), "nodes) + mapping (", len(mapping["inputs"]), "keys)")
