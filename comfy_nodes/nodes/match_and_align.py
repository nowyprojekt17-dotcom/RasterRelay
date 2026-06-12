import torch
import torch.nn.functional as F

# Try relative import first (when loaded as part of package),
# fall back to local implementation (when loaded directly in tests)
try:
    from ..utils.mask_processing import blur_mask as _shared_blur_mask
    def blur_mask(mask, blend_radius):
        return _shared_blur_mask(mask, blend_radius)
except (ImportError, SystemError):
    def _gaussian_kernel(kernel_size, sigma):
        x = torch.arange(kernel_size, dtype=torch.float32) - (kernel_size - 1) / 2
        kernel = torch.exp(-0.5 * (x / sigma) ** 2)
        kernel = kernel / kernel.sum()
        return kernel

    def blur_mask(mask, blend_radius):
        if blend_radius <= 0:
            return mask

        device = mask.device
        kernel_size = blend_radius * 6 + 1
        if kernel_size % 2 == 0:
            kernel_size += 1
        sigma = blend_radius / 3.0

        kernel = _gaussian_kernel(kernel_size, sigma).to(device)

        m_bchw = mask.permute(0, 3, 1, 2)

        # Separable 1D Gaussian horizontal pass
        m_bchw = F.pad(m_bchw, (kernel_size // 2, kernel_size // 2, 0, 0), mode="replicate")
        kernel_h = kernel.view(1, 1, 1, kernel_size)
        m_bchw = F.conv2d(m_bchw, kernel_h, padding="valid")

        # Vertical pass
        m_bchw = F.pad(m_bchw, (0, 0, kernel_size // 2, kernel_size // 2), mode="replicate")
        kernel_v = kernel.view(1, 1, kernel_size, 1)
        m_bchw = F.conv2d(m_bchw, kernel_v, padding="valid")

        return m_bchw.permute(0, 2, 3, 1)


class RasterRelaySmartCropAligner:
    """
    Pads the crop area outward to match the grid requirements of the model (e.g. 16 or 64 px)
    without stretching/resizing the pixels, preserving 1:1 scale.

    Example:
        >>> aligner = RasterRelaySmartCropAligner()
        >>> aligned_img, aligned_mask, pad_l, pad_t, pad_r, pad_b = aligner.align(
        ...     document_image, document_mask,
        ...     crop_left=100, crop_top=200,
        ...     crop_width=513, crop_height=385,
        ...     grid_size=16
        ... )
        # crop 513x385 -> aligned 528x376 (next multiples of 16)
    """
    CATEGORY = "RasterRelay"
    RETURN_TYPES = ("IMAGE", "MASK", "INT", "INT", "INT", "INT")
    RETURN_NAMES = ("aligned_image", "aligned_mask", "pad_left", "pad_top", "pad_right", "pad_bottom")
    FUNCTION = "align"
    DESCRIPTION = "Expands crop coordinates outward to align with grid size without scaling."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "document_image": ("IMAGE", {"tooltip": "Full document image (RGB or RGBA)"}),
                "document_mask": ("MASK", {"tooltip": "Full document mask"}),
                "crop_left": ("INT", {"default": 0, "min": 0, "max": 16384}),
                "crop_top": ("INT", {"default": 0, "min": 0, "max": 16384}),
                "crop_width": ("INT", {"default": 512, "min": 1, "max": 16384}),
                "crop_height": ("INT", {"default": 512, "min": 1, "max": 16384}),
                "grid_size": ("INT", {"default": 16, "min": 8, "max": 64, "step": 8}),
            }
        }

    def align(self, document_image, document_mask, crop_left, crop_top, crop_width, crop_height, grid_size):
        _, doc_h, doc_w, _ = document_image.shape

        # Calculate target dimensions aligned with grid_size
        aligned_w = ((crop_width + grid_size - 1) // grid_size) * grid_size
        aligned_h = ((crop_height + grid_size - 1) // grid_size) * grid_size

        extra_w = aligned_w - crop_width
        extra_h = aligned_h - crop_height

        # Distribute padding to left/right and top/bottom
        pad_l = extra_w // 2
        pad_r = extra_w - pad_l
        pad_t = extra_h // 2
        pad_b = extra_h - pad_t

        new_left = crop_left - pad_l
        new_right = crop_left + crop_width + pad_r
        new_top = crop_top - pad_t
        new_bottom = crop_top + crop_height + pad_b

        # Shift the crop window if it falls out of document boundaries
        if new_left < 0:
            new_right -= new_left
            new_left = 0
        if new_right > doc_w:
            new_left -= (new_right - doc_w)
            new_right = doc_w
            if new_left < 0:
                new_left = 0

        if new_top < 0:
            new_bottom -= new_top
            new_top = 0
        if new_bottom > doc_h:
            new_top -= (new_bottom - doc_h)
            new_bottom = doc_h
            if new_top < 0:
                new_top = 0

        # Recalculate actual padding applied
        actual_pad_l = crop_left - new_left
        actual_pad_t = crop_top - new_top
        actual_pad_r = new_right - (crop_left + crop_width)
        actual_pad_b = new_bottom - (crop_top + crop_height)

        # Slice the document image and mask
        aligned_image = document_image[:, new_top:new_bottom, new_left:new_right, :]

        if document_mask.dim() == 2:
            document_mask = document_mask.unsqueeze(0)

        # Ensure mask batch size matches image batch size
        if document_mask.shape[0] == 1 and document_image.shape[0] > 1:
            document_mask = document_mask.repeat(document_image.shape[0], 1, 1)

        aligned_mask = document_mask[:, new_top:new_bottom, new_left:new_right]

        return (
            aligned_image,
            aligned_mask,
            actual_pad_l,
            actual_pad_t,
            actual_pad_r,
            actual_pad_b,
        )


class RasterRelaySmartCropTrimmer:
    """
    Crops away the extra aligned padding added by RasterRelaySmartCropAligner,
    returning the generated image back to the original crop dimensions.

    Example:
        >>> trimmer = RasterRelaySmartCropTrimmer()
        >>> trimmed_img, trimmed_mask = trimmer.trim(
        ...     generated_image, generated_mask,
        ...     pad_left=8, pad_top=8,
        ...     pad_right=7, pad_bottom=6
        ... )
        # Removes padding to restore original crop size
    """
    CATEGORY = "RasterRelay"
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("trimmed_image", "trimmed_mask")
    FUNCTION = "trim"
    DESCRIPTION = "Removes the alignment padding to restore original crop dimensions."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "generated_image": ("IMAGE", {"tooltip": "Image from generation workflow"}),
                "generated_mask": ("MASK", {"tooltip": "Mask from generation workflow"}),
                "pad_left": ("INT", {"default": 0}),
                "pad_top": ("INT", {"default": 0}),
                "pad_right": ("INT", {"default": 0}),
                "pad_bottom": ("INT", {"default": 0}),
            }
        }

    def trim(self, generated_image, generated_mask, pad_left, pad_top, pad_right, pad_bottom):
        _, h, w, _ = generated_image.shape

        crop_r = w - pad_right
        crop_b = h - pad_bottom

        trimmed_image = generated_image[:, pad_top:crop_b, pad_left:crop_r, :]

        if generated_mask.dim() == 2:
            generated_mask = generated_mask.unsqueeze(0)

        trimmed_mask = generated_mask[:, pad_top:crop_b, pad_left:crop_r]

        return (trimmed_image, trimmed_mask)


class RasterRelayVaeDriftMatch:
    """
    Forces the unmasked (original reference) regions of the generated image to be
    mathematically identical to the original crop, preventing VAE drift.
    Blends the edges smoothly to avoid any visible seam.

    Example:
        >>> matcher = RasterRelayVaeDriftMatch()
        >>> matched = matcher.match_drift(
        ...     original_crop, generated_crop, mask,
        ...     blend_radius=12, restore_unmasked=True
        ... )
        # Unmasked pixels are identical to original, edges are smoothly blended
    """
    CATEGORY = "RasterRelay"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("matched_image",)
    FUNCTION = "match_drift"
    DESCRIPTION = "Restores original unmasked pixels to bypass VAE reconstruction drift."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "original_crop": ("IMAGE", {"tooltip": "Original unedited crop from Photoshop"}),
                "generated_crop": ("IMAGE", {"tooltip": "Generated/VAE-decoded crop"}),
                "mask": ("MASK", {"tooltip": "Inpainting mask (1 = edited, 0 = original)"}),
                "blend_radius": ("INT", {"default": 12, "min": 0, "max": 128, "tooltip": "Smooth blending radius at the mask boundary"}),
                "restore_unmasked": ("BOOLEAN", {"default": True, "tooltip": "Restore original pixels where mask is 0"}),
            },
            "optional": {
                "mask_mode": (["binary", "soft"], {
                    "default": "binary",
                    "tooltip": "binary = Photoshop layer mask controls softness; soft = pre-blend content by mask values",
                }),
            },
        }

    @staticmethod
    def _resize_image(image, height, width):
        if image.shape[1] == height and image.shape[2] == width:
            return image

        channels_first = image.permute(0, 3, 1, 2)
        resized = F.interpolate(channels_first, size=(height, width), mode="bilinear", align_corners=False)
        return resized.permute(0, 2, 3, 1)

    def match_drift(self, original_crop, generated_crop, mask, blend_radius, restore_unmasked, mask_mode="binary"):
        if not restore_unmasked:
            return (generated_crop,)

        device = generated_crop.device
        orig = original_crop.to(device)
        gen = generated_crop.to(device)
        target_h, target_w = orig.shape[1:3]

        # VAE encoding can crop non-grid-aligned inputs. Composite against the
        # Photoshop crop size so downstream padding always receives that shape.
        gen = self._resize_image(gen, target_h, target_w)

        # Format mask to B H W 1
        if mask.dim() == 2:
            mask = mask.unsqueeze(0).unsqueeze(-1)
        elif mask.dim() == 3:
            mask = mask.unsqueeze(-1)

        mask = mask.to(device)
        if mask.shape[0] == 1 and gen.shape[0] > 1:
            mask = mask.repeat(gen.shape[0], 1, 1, 1)

        # Match dimensions of mask to the original Photoshop crop if they differ.
        if mask.shape[1:3] != orig.shape[1:3]:
            mask_perm = mask.permute(0, 3, 1, 2)
            mask_resized = F.interpolate(mask_perm, size=orig.shape[1:3], mode="bilinear", align_corners=False)
            mask = mask_resized.permute(0, 2, 3, 1)

        if mask_mode == "soft":
            content_mask = blur_mask(mask, blend_radius)
        else:
            # For Photoshop layer-mask workflows, the layer content must not be
            # pre-feathered by the same mask. Otherwise the edge gets blended
            # twice: once in the pixels and once by Photoshop's layer mask.
            content_mask = (mask > 0.0001).to(dtype=gen.dtype)

        # Align channels
        c_orig = orig.shape[-1]
        c_gen = gen.shape[-1]
        if c_orig != c_gen:
            c_min = min(c_orig, c_gen)
            orig_rgb = orig[..., :c_min]
            gen_rgb = gen[..., :c_min]
        else:
            orig_rgb = orig
            gen_rgb = gen

        # Perfect blend: original where mask is 0, generated where mask is 1.
        composited = orig_rgb * (1.0 - content_mask) + gen_rgb * content_mask

        # Gaussian edge blending intentionally spreads the transition outside the
        # mask edge. Force truly unmasked pixels back to the original so Photoshop
        # mask edits never reveal VAE/color/scale drift in reference areas.
        exact_unmasked = mask <= 0.0001
        composited = torch.where(exact_unmasked, orig_rgb, composited)

        # Restore alpha channel if original has 4 channels
        if c_gen == 4 and composited.shape[-1] == 3:
            composited = torch.cat([composited, gen[..., 3:]], dim=-1)

        # Zwolnij pamięć GPU po dużych operacjach
        del orig, gen, orig_rgb, gen_rgb, content_mask, mask, exact_unmasked
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return (composited.clamp(0.0, 1.0),)


class RasterRelayGrainInjector:
    """
    Extracts the fine micro-texture/grain from the original image reference area
    and injects it into the generated area, ensuring seamless blending of noise.

    Example:
        >>> injector = RasterRelayGrainInjector()
        >>> grained = injector.inject_grain(
        ...     original_crop, generated_crop, mask,
        ...     grain_strength=1.0
        ... )
        # Grain from original is injected into generated region
    """
    CATEGORY = "RasterRelay"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("grained_image",)
    FUNCTION = "inject_grain"
    DESCRIPTION = "Extracts noise from original and applies it to generated areas."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "original_crop": ("IMAGE", {"tooltip": "Original unedited crop"}),
                "generated_crop": ("IMAGE", {"tooltip": "Generated image"}),
                "mask": ("MASK", {"tooltip": "Inpainting mask"}),
                "grain_strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.1}),
            }
        }

    def inject_grain(self, original_crop, generated_crop, mask, grain_strength):
        if grain_strength <= 0:
            return (generated_crop,)

        device = generated_crop.device
        orig = original_crop[..., :3].to(device)
        gen = generated_crop.to(device)

        # Extract luminance grain. RGB-independent random noise creates colored
        # speckles, so the injected grain is monochrome and preserves hue.
        luminance_weights = torch.tensor([0.299, 0.587, 0.114], dtype=orig.dtype, device=device)
        orig_luma = (orig * luminance_weights).sum(dim=-1, keepdim=True)
        orig_luma_blur = F.avg_pool2d(
            orig_luma.permute(0, 3, 1, 2),
            kernel_size=3,
            stride=1,
            padding=1,
        ).permute(0, 2, 3, 1)
        noise_profile = orig_luma - orig_luma_blur

        if mask.dim() == 2:
            mask = mask.unsqueeze(0)
        if mask.shape[0] == 1 and generated_crop.shape[0] > 1:
            mask = mask.repeat(generated_crop.shape[0], 1, 1)

        ref_mask = (1.0 - mask).unsqueeze(-1).to(device)
        mask_expanded = mask.unsqueeze(-1).to(device)

        # Compute standard deviation of grain in the reference area
        sum_mask = ref_mask.sum().clamp(min=1.0)
        ref_pixels = noise_profile * ref_mask
        mean_noise = ref_pixels.sum() / sum_mask
        var_noise = ((ref_pixels - mean_noise) ** 2 * ref_mask).sum() / sum_mask
        std_noise = torch.sqrt(var_noise).clamp(min=1e-5)

        # Generate similar monochrome noise and apply it equally to RGB.
        noise = torch.randn_like(gen[..., :1]) * std_noise * grain_strength

        # Inject noise only to the generated region (where mask is 1)
        grained_rgb = gen[..., :3] + (noise * mask_expanded)
        grained_rgb = grained_rgb.clamp(0.0, 1.0)

        if gen.shape[-1] == 4:
            grained_rgb = torch.cat([grained_rgb, gen[..., 3:]], dim=-1)

        return (grained_rgb,)
