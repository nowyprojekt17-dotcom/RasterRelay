import torch
import torch.nn.functional as F


class RasterRelayEdgeHarmonize:
    """
    Removes visible halos at mask edges by smoothing the color transition
    between generated and original images.

    Algorithm:
    1. Compute the color difference (original - generated) in the mask region.
    2. Blur this difference map with a large kernel to smooth out sharp transitions.
    3. Apply the blurred difference to the generated image.
    4. This effectively smooths any halo/border by averaging the color mismatch
       across a wider region, making the transition invisible.

    Example:
        >>> harmonizer = RasterRelayEdgeHarmonize()
        >>> result = harmonizer.harmonize(
        ...     original_image, generated_image, mask,
        ...     edge_width=40, strength=1.0
        ... )
        # Visible halos at mask edges are removed
    """

    CATEGORY = "RasterRelay"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("harmonized_image",)
    FUNCTION = "harmonize"
    DESCRIPTION = "Removes visible halos at mask edges by smoothing the color transition."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "original_image": ("IMAGE", {"tooltip": "Original unedited image"}),
                "generated_image": ("IMAGE", {"tooltip": "Generated/inpainted image (may have halo at edges)"}),
                "mask": ("MASK", {"tooltip": "Inpainting mask (1 = generated, 0 = original)"}),
                "edge_width": ("INT", {
                    "default": 40, "min": 10, "max": 100, "step": 1,
                    "tooltip": "Width of the smoothing zone in pixels from the mask boundary inward.",
                }),
                "strength": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "Correction strength (0 = no change, 1 = full halo removal).",
                }),
            }
        }

    @staticmethod
    def _gaussian_kernel1d(kernel_size, sigma, device):
        x = torch.arange(kernel_size, dtype=torch.float32, device=device) - (kernel_size - 1) / 2
        kernel = torch.exp(-0.5 * (x / sigma) ** 2)
        return kernel / kernel.sum()

    def _blur_2d(self, image, radius):
        """Apply separable Gaussian blur to a BHWC tensor."""
        if radius <= 0:
            return image
        device = image.device
        dtype = image.dtype
        h, w = image.shape[1], image.shape[2]
        c = image.shape[3]
        max_kernel = min(h, w) if min(h, w) % 2 == 1 else min(h, w) - 1
        max_kernel = max(3, max_kernel)
        k = radius * 6 + 1
        if k % 2 == 0:
            k += 1
        k = min(k, max_kernel)
        if k < 3:
            k = 3
        sigma = max(radius / 3.0, 0.5)

        kernel = self._gaussian_kernel1d(k, sigma, device)

        # Convert BHWC -> BCHW
        x = image.permute(0, 3, 1, 2)

        # Create depthwise conv kernel for c channels
        kernel_h = kernel.view(1, 1, 1, k).repeat(c, 1, 1, 1)
        kernel_v = kernel.view(1, 1, k, 1).repeat(c, 1, 1, 1)

        pad = k // 2
        x = F.pad(x, (pad, pad, 0, 0), mode="reflect")
        x = F.conv2d(x, kernel_h, padding=0, groups=c)
        x = F.pad(x, (0, 0, pad, pad), mode="reflect")
        x = F.conv2d(x, kernel_v, padding=0, groups=c)

        # Convert BCHW -> BHWC
        return x.permute(0, 2, 3, 1)

    def harmonize(self, original_image, generated_image, mask, edge_width, strength):
        if strength <= 0.0:
            return (generated_image.clone(),)

        device = generated_image.device
        dtype = generated_image.dtype

        orig = original_image.to(device=device, dtype=dtype)
        gen = generated_image.to(device=device, dtype=dtype)

        orig_rgb = orig[..., :3]
        gen_rgb = gen[..., :3]

        # Handle mask dimensions
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

        # 1. Compute color difference (original - generated)
        color_diff = orig_rgb - gen_rgb

        # 2. Multiply by mask to get difference only in generated area
        masked_diff = color_diff * mask

        # 3. Blur the masked difference with edge_width kernel
        blurred_diff = self._blur_2d(masked_diff, edge_width)

        # 4. Also blur the mask to create smooth normalization
        blurred_mask = self._blur_2d(mask, edge_width)

        # 5. Normalize: divide blurred_diff by blurred_mask to get average correction
        blurred_mask_safe = blurred_mask.clamp(min=0.001)
        normalized_diff = blurred_diff / blurred_mask_safe

        # 6. Apply the smoothed correction weighted by blurred mask and strength
        correction = normalized_diff * blurred_mask * strength

        harmonized = gen_rgb + correction

        # 7. Clamp and preserve alpha if present
        result = harmonized.clamp(0.0, 1.0)

        if gen.shape[-1] == 4:
            result = torch.cat([result, gen[..., 3:4]], dim=-1)

        # Zwolnij pamięć GPU po dużych operacjach
        del orig, gen, orig_rgb, gen_rgb, color_diff, masked_diff, blurred_diff, blurred_mask
        del blurred_mask_safe, normalized_diff, correction, harmonized
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return (result,)
