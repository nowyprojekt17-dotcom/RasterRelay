import functools
import os
import tempfile
import torch
import numpy as np
from PIL import Image

# sRGB ICC tagging is best-effort: if a minimal PIL build lacks ImageCms the node
# still saves (just without the iCCP chunk), exactly as before.
try:
    from PIL import ImageCms
    _IMAGECMS_AVAILABLE = True
except Exception:  # pragma: no cover - environment-dependent
    ImageCms = None
    _IMAGECMS_AVAILABLE = False

# ComfyUI modules - optional imports for testing
try:
    import folder_paths
    COMFYUI_AVAILABLE = True
except ImportError:
    COMFYUI_AVAILABLE = False
    folder_paths = None


@functools.lru_cache(maxsize=1)
def _srgb_icc_bytes():
    """Standard sRGB ICC profile bytes for the PNG iCCP chunk.

    We only TAG the pixels as sRGB; no pixel values change. The RasterRelay
    pipeline and the FLUX model already work in sRGB, so the result is sRGB - it
    was just untagged. Embedding the profile lets Photoshop convert the result
    into a wide-gamut document's space (Adobe RGB / ProPhoto) on placement
    instead of misreading the untagged RGB as the document profile (tonal drift).
    """
    if not _IMAGECMS_AVAILABLE:
        return None
    try:
        return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    except Exception:  # pragma: no cover - environment-dependent
        return None


class RasterRelaySaveImage:
    """
    Saves a generated image (RGB or RGBA) to the ComfyUI output directory as PNG.
    Preserves the alpha channel when the input has 4 channels, so transparent areas
    stay transparent instead of being flattened to black by the standard SaveImage node.
    """
    CATEGORY = "RasterRelay"
    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "save"
    DESCRIPTION = "Saves a generated image to PNG with optional alpha channel preserved."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE", {
                    "tooltip": "Image tensor (3 or 4 channels). 4-channel tensors keep transparency."
                }),
                "filename_prefix": ("STRING", {
                    "default": "RasterRelay/inpainting",
                    "tooltip": "Subfolder and filename prefix for the saved PNG."
                }),
            }
        }

    @staticmethod
    def _to_uint8_array(tensor):
        array = (tensor.clamp(0.0, 1.0) * 255.0).round().to(torch.uint8).cpu().numpy()
        if array.ndim == 4:
            array = array[0]
        return array

    @staticmethod
    def _alpha_bbox(array):
        if array.shape[-1] < 4:
            return None

        alpha = array[:, :, 3]
        ys, xs = np.where(alpha > 0)
        if len(xs) == 0 or len(ys) == 0:
            return None

        min_x = int(xs.min())
        min_y = int(ys.min())
        max_x = int(xs.max())
        max_y = int(ys.max())
        return {
            "left": min_x,
            "top": min_y,
            "right": max_x + 1,
            "bottom": max_y + 1,
            "width": max_x - min_x + 1,
            "height": max_y - min_y + 1,
        }

    @staticmethod
    def _safe_prefix(text):
        safe = str(text or "image").replace("\\", "_").replace("/", "_")
        safe = safe.strip("._ ")
        return safe or "image"

    @classmethod
    def _fallback_output_dir(cls):
        configured = os.environ.get("RASTERRELAY_OUTPUT_DIR")
        if configured:
            return configured
        return os.path.join(tempfile.gettempdir(), "RasterRelay")

    @classmethod
    def _resolve_output_target(cls, base_output_dir, filename_prefix):
        subfolder, filename_prefix_text = os.path.split(filename_prefix)
        filename_prefix_text = cls._safe_prefix(filename_prefix_text)
        if not subfolder:
            return base_output_dir, "", filename_prefix_text

        requested_output_dir = os.path.join(base_output_dir, subfolder)
        try:
            os.makedirs(requested_output_dir, exist_ok=True)
            return requested_output_dir, subfolder, filename_prefix_text
        except OSError:
            flattened_subfolder = cls._safe_prefix(subfolder)
            return base_output_dir, "", f"{flattened_subfolder}_{filename_prefix_text}"

    @classmethod
    def _fallback_target(cls, filename_prefix):
        subfolder, filename_prefix_text = os.path.split(filename_prefix)
        parts = [cls._safe_prefix(part) for part in (subfolder, filename_prefix_text) if part]
        fallback_prefix = "_".join(parts) or "image"
        fallback_dir = cls._fallback_output_dir()
        os.makedirs(fallback_dir, exist_ok=True)
        return fallback_dir, "", fallback_prefix

    def save(self, images, filename_prefix):
        output_dir, subfolder, filename_prefix_text = self._resolve_output_target(
            folder_paths.get_output_directory(),
            filename_prefix,
        )

        if images.dim() == 3:
            images = images.unsqueeze(0)

        png_kwargs = {"format": "PNG", "compress_level": 6}
        icc = _srgb_icc_bytes()
        if icc:
            png_kwargs["icc_profile"] = icc

        counter = 0
        results = []

        for index, image in enumerate(images):
            array = self._to_uint8_array(image)
            if array.shape[-1] == 4:
                pil_image = Image.fromarray(array, mode="RGBA")
            else:
                pil_image = Image.fromarray(array[:, :, :3], mode="RGB")

            file_name = f"{filename_prefix_text}_{counter:05d}_.png"
            full_path = os.path.join(output_dir, file_name)

            while os.path.exists(full_path):
                counter += 1
                file_name = f"{filename_prefix_text}_{counter:05d}_.png"
                full_path = os.path.join(output_dir, file_name)

            try:
                pil_image.save(full_path, **png_kwargs)
                absolute_path = full_path
            except OSError:
                output_dir, subfolder, filename_prefix_text = self._fallback_target(filename_prefix)
                file_name = f"{filename_prefix_text}_{counter:05d}_.png"
                full_path = os.path.join(output_dir, file_name)
                while os.path.exists(full_path):
                    counter += 1
                    file_name = f"{filename_prefix_text}_{counter:05d}_.png"
                    full_path = os.path.join(output_dir, file_name)
                pil_image.save(full_path, **png_kwargs)
                absolute_path = full_path

            results.append({
                "filename": file_name,
                "subfolder": subfolder,
                "type": "output",
                "absolute_path": absolute_path,
                "width": int(array.shape[1]),
                "height": int(array.shape[0]),
                "alpha_bbox": self._alpha_bbox(array),
            })

            counter += 1

        return {"ui": {"images": results}}
