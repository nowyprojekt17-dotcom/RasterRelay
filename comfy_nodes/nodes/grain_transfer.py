import torch
import torch.nn.functional as F


class RasterRelayGrainTransfer:
    """
    Extracts high-frequency grain/noise from the original image and injects it
    into the generated image, so the inpaint blends seamlessly with surrounding
    photographic texture instead of looking "plasticky" or "AI-generated".

    Algorithm:
      1. Compute luma of the original image.
      2. Subtract a Gaussian-blurred version to isolate the grain residual.
      3. Same for the generated image (to keep only the delta we want to add).
      4. Blend the residual into the generated image with `grain_strength`,
         scaled by the feathered mask so the boundary is invisible.
      5. Result is added to RGB channels equally (monochrome grain), preserving
         hue and saturation while restoring fine texture.

    Example:
        >>> transfer = RasterRelayGrainTransfer()
        >>> result = transfer.inject_grain(
        ...     original_image, generated_image, mask,
        ...     grain_strength=0.8, blur_radius=3,
        ...     edge_feather=16, preserve_luminance=True
        ... )
        # Generated region now has matching grain texture from original
    """

    CATEGORY = "RasterRelay"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("grained_image",)
    FUNCTION = "inject_grain"
    DESCRIPTION = "Transfers photographic grain from the original image to the generated area, eliminating the 'plasticky' AI-generated look."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "original_image": ("IMAGE", {"tooltip": "Original unedited image — grain source"}),
                "generated_image": ("IMAGE", {"tooltip": "Generated/inpainted image — grain target"}),
                "mask": ("MASK", {"tooltip": "Mask: 1 = generated, 0 = original"}),
                "grain_strength": ("FLOAT", {
                    "default": 0.8, "min": 0.0, "max": 2.0, "step": 0.05,
                    "tooltip": "How much grain to inject (1.0 = same grain as original).",
                }),
                "blur_radius": ("INT", {
                    "default": 3, "min": 1, "max": 15, "step": 1,
                    "tooltip": "Gaussian radius to extract residual grain. Higher = coarser grain.",
                }),
                "edge_feather": ("INT", {
                    "default": 16, "min": 0, "max": 64, "step": 1,
                    "tooltip": "Feather radius for the grain-injection mask. Hides the seam.",
                }),
                "preserve_luminance": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Inject only the difference from local luma so the overall exposure doesn't drift.",
                }),
            }
        }

    @staticmethod
    def _gaussian_kernel1d(kernel_size, sigma, device):
        x = torch.arange(kernel_size, dtype=torch.float32, device=device) - (kernel_size - 1) / 2
        kernel = torch.exp(-0.5 * (x / sigma) ** 2)
        return kernel / kernel.sum()

    def _blur_luma(self, image, blur_radius):
        if blur_radius <= 0:
            blur_radius = 1
        device = image.device
        h, w = image.shape[1], image.shape[2]
        max_kernel = min(h, w) if min(h, w) % 2 == 1 else min(h, w) - 1
        max_kernel = max(3, max_kernel)
        k = blur_radius * 6 + 1
        if k % 2 == 0:
            k += 1
        k = min(k, max_kernel)
        if k < 3:
            k = 3
        sigma = max(blur_radius / 3.0, 0.5)

        kernel = self._gaussian_kernel1d(k, sigma, device)
        weights_h = kernel.view(1, 1, 1, k)
        weights_v = kernel.view(1, 1, k, 1)

        x = image.permute(0, 3, 1, 2)  # BCHW
        pad = k // 2
        x = F.pad(x, (pad, pad, 0, 0), mode="reflect")
        x = F.conv2d(x, weights_h, padding="valid")
        x = F.pad(x, (0, 0, pad, pad), mode="reflect")
        x = F.conv2d(x, weights_v, padding="valid")
        return x.permute(0, 2, 3, 1)

    def _feather_mask(self, mask_4d, radius):
        if radius <= 0:
            return mask_4d.clamp(0.0, 1.0)
        device = mask_4d.device
        h, w = mask_4d.shape[1], mask_4d.shape[2]
        max_kernel_h = max(3, h if h % 2 == 1 else h - 1)
        max_kernel_w = max(3, w if w % 2 == 1 else w - 1)
        k = radius * 6 + 1
        if k % 2 == 0:
            k += 1
        k = min(k, min(max_kernel_h, max_kernel_w))
        if k < 3:
            k = 3
        sigma = max(radius / 3.0, 0.5)
        kernel = self._gaussian_kernel1d(k, sigma, device)
        x = mask_4d.permute(0, 3, 1, 2)
        pad = k // 2
        x = F.pad(x, (pad, pad, 0, 0), mode="reflect")
        x = F.conv2d(x, kernel.view(1, 1, 1, k), padding="valid")
        x = F.pad(x, (0, 0, pad, pad), mode="reflect")
        x = F.conv2d(x, kernel.view(1, 1, k, 1), padding="valid")
        return x.permute(0, 2, 3, 1).clamp(0.0, 1.0)

    def _luma(self, rgb):
        weights = torch.tensor([0.299, 0.587, 0.114], dtype=rgb.dtype, device=rgb.device)
        return (rgb * weights).sum(dim=-1, keepdim=True)

    def inject_grain(self, original_image, generated_image, mask, grain_strength,
                     blur_radius, edge_feather, preserve_luminance):
        if grain_strength <= 0.0:
            return (generated_image.clone(),)

        device = generated_image.device
        dtype = generated_image.dtype

        orig = original_image.to(device=device, dtype=dtype)
        gen = generated_image.to(device=device, dtype=dtype)

        orig_rgb = orig[..., :3]
        gen_rgb = gen[..., :3]

        if mask.dim() == 2:
            mask = mask.unsqueeze(0)
        if mask.dim() == 3:
            mask = mask.unsqueeze(-1)
        mask = mask.to(device=device, dtype=dtype)
        if mask.shape[0] == 1 and gen.shape[0] > 1:
            mask = mask.repeat(gen.shape[0], 1, 1, 1)

        h, w = gen.shape[1:3]
        if mask.shape[1:3] != (h, w):
            mp = mask.permute(0, 3, 1, 2)
            mp = F.interpolate(mp, size=(h, w), mode="bilinear", align_corners=False)
            mask = mp.permute(0, 2, 3, 1)

        # 1. Extract grain residual from original (luma only)
        orig_luma = self._luma(orig_rgb)
        orig_luma_blur = self._blur_luma(orig_luma, blur_radius)
        orig_grain = orig_luma - orig_luma_blur

        # If original and gen have different spatial sizes, resample grain to gen size.
        if orig_grain.shape[1:3] != (h, w):
            og = orig_grain.permute(0, 3, 1, 2)
            og = F.interpolate(og, size=(h, w), mode="bilinear", align_corners=False)
            orig_grain = og.permute(0, 2, 3, 1)

        # 2. Same for generated — to know what grain is already there
        gen_luma = self._luma(gen_rgb)
        gen_luma_blur = self._blur_luma(gen_luma, blur_radius)
        gen_grain = gen_luma - gen_luma_blur

        # 3. Target grain residual = original residual - generated residual
        target_grain = (orig_grain - gen_grain) * grain_strength

        # 4. Feather the mask for seamless injection
        feathered = self._feather_mask(mask.clamp(0.0, 1.0), edge_feather)

        if preserve_luminance:
            # Add the grain delta uniformly to RGB so luma changes but hue is preserved
            # Channel-wise: add a fraction so that luma changes by `target_grain`
            # weights w: adding (target_grain, target_grain, target_grain) per pixel
            # preserves perceived chroma approximately because delta is achromatic.
            grain_rgb = target_grain.expand_as(gen_rgb)
            grained = gen_rgb + grain_rgb * feathered
        else:
            grained = gen_rgb + target_grain.expand_as(gen_rgb) * feathered

        result = grained.clamp(0.0, 1.0)

        if gen.shape[-1] == 4:
            result = torch.cat([result, gen[..., 3:4]], dim=-1)

        # Zwolnij pamięć GPU po dużych operacjach
        del orig, gen, orig_rgb, gen_rgb, orig_luma, orig_luma_blur, orig_grain
        del gen_luma, gen_luma_blur, gen_grain, target_grain, feathered, grained
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return (result,)
