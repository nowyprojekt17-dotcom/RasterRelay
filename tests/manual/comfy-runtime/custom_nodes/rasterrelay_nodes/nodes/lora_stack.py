import json
import logging

# ComfyUI modules - optional imports for testing
try:
    import folder_paths
    import comfy.utils
    import comfy.sd
    COMFYUI_AVAILABLE = True
except ImportError:
    COMFYUI_AVAILABLE = False
    folder_paths = None
    comfy = None


class RasterRelayLoraStack:
    """
    Applies multiple LoRA models from a JSON configuration string.
    Each LoRA is applied sequentially to both MODEL and CLIP.
    """
    CATEGORY = "RasterRelay"
    RETURN_TYPES = ("MODEL", "CLIP")
    RETURN_NAMES = ("model", "clip")
    FUNCTION = "apply_loras"
    DESCRIPTION = "Applies multiple LoRA models from JSON config to MODEL and CLIP."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL", {"tooltip": "The model to apply LoRAs to"}),
                "clip": ("CLIP", {"tooltip": "The CLIP to apply LoRAs to"}),
                "loras_json": ("STRING", {
                    "multiline": True,
                    "default": '[]',
                    "tooltip": ('JSON array of LoRA configs. '
                                'Each entry: {"name":"file.safetensors","strength_model":1.0,"strength_clip":1.0}. '
                                'Empty array = no LoRAs applied.'),
                }),
            }
        }

    @staticmethod
    def _normalize_configs(loras_json):
        try:
            configs = json.loads(loras_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"RasterRelayLoraStack: invalid loras_json: {e}") from e

        if not isinstance(configs, list):
            raise ValueError("RasterRelayLoraStack: loras_json must be a JSON array")

        normalized = []
        for idx, cfg in enumerate(configs):
            if not isinstance(cfg, dict):
                raise ValueError(f"RasterRelayLoraStack: entry #{idx} must be an object")

            lora_name = str(cfg.get("name", "")).strip()
            if not lora_name:
                raise ValueError(f"RasterRelayLoraStack: entry #{idx} has no LoRA name")

            strength_model = float(cfg.get("strength_model", cfg.get("strengthModel", 1.0)))
            strength_clip = float(cfg.get("strength_clip", cfg.get("strengthClip", strength_model)))
            normalized.append({
                "name": lora_name,
                "strength_model": max(-2.0, min(2.0, strength_model)),
                "strength_clip": max(-2.0, min(2.0, strength_clip)),
            })

        return normalized

    def apply_loras(self, model, clip, loras_json):
        configs = self._normalize_configs(loras_json)

        if not configs:
            return (model, clip)

        for idx, cfg in enumerate(configs):
            lora_name = cfg["name"]
            strength_model = cfg["strength_model"]
            strength_clip = cfg["strength_clip"]

            try:
                lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)
            except Exception as e:
                raise FileNotFoundError(f"RasterRelayLoraStack: LoRA '{lora_name}' not found") from e

            lora_sd = comfy.utils.load_torch_file(lora_path, safe_load=True)

            if lora_sd is None:
                raise RuntimeError(f"RasterRelayLoraStack: could not load LoRA '{lora_name}'")

            logging.info(
                "RasterRelayLoraStack: applying LoRA #%s '%s' model=%s clip=%s",
                idx + 1,
                lora_name,
                strength_model,
                strength_clip,
            )
            model, clip = comfy.sd.load_lora_for_models(
                model, clip, lora_sd, strength_model, strength_clip
            )

        return (model, clip)
