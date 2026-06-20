import torch
import torch.nn.functional as F

# Try relative import first (when loaded as part of package),
# fall back to local implementation (when loaded directly in tests)
try:
    from ..utils.mask_processing import blur_mask as _shared_blur_mask
    def _blur_mask_wrapper(mask, blend_radius):
        """Wrapper dla wspólnej funkcji blur_mask, zachowuje kompatybilność."""
        return _shared_blur_mask(mask, blend_radius)
except (ImportError, SystemError):
    def _gaussian_kernel(kernel_size, sigma):
        x = torch.arange(kernel_size, dtype=torch.float32) - (kernel_size - 1) / 2
        kernel = torch.exp(-0.5 * (x / sigma) ** 2)
        kernel = kernel / kernel.sum()
        return kernel

    def _blur_mask_wrapper(mask, blend_radius):
        """Applies separable Gaussian blur to a BHWC mask tensor."""
        if blend_radius <= 0:
            return mask

        device = mask.device
        kernel_size = blend_radius * 6 + 1
        if kernel_size % 2 == 0:
            kernel_size += 1
        sigma = blend_radius / 3.0

        kernel = _gaussian_kernel(kernel_size, sigma).to(device)

        m_bchw = mask.permute(0, 3, 1, 2)

        m_bchw = F.pad(m_bchw, (kernel_size // 2, kernel_size // 2, 0, 0), mode="replicate")
        kernel_h = kernel.view(1, 1, 1, kernel_size)
        m_bchw = F.conv2d(m_bchw, kernel_h, padding="valid")

        m_bchw = F.pad(m_bchw, (0, 0, kernel_size // 2, kernel_size // 2), mode="replicate")
        kernel_v = kernel.view(1, 1, kernel_size, 1)
        m_bchw = F.conv2d(m_bchw, kernel_v, padding="valid")

        return m_bchw.permute(0, 2, 3, 1)


class RasterRelayColorHarmonize:
    """
    Fixes color mismatch between AI-generated inpainted regions and the original image
    using Reinhard color transfer in LAB color space.

    Algorithm:
    1. Convert both images from RGB to LAB color space (pure PyTorch, no OpenCV).
    2. Sample color statistics (mean/std per channel) from:
       - Reference region: original image pixels in a margin around the mask border.
       - Target region: generated image pixels inside the mask.
    3. Apply Reinhard transfer: shift and scale target LAB channels to match reference.
    4. Blend the correction by `strength` and composite using a Gaussian-blurred mask
       for seamless edges.

    Example:
        >>> harmonizer = RasterRelayColorHarmonize()
        >>> result = harmonizer.harmonize(
        ...     original_image, generated_image, mask,
        ...     strength=0.85, blend_radius=20, margin=30
        ... )
        # Colors of generated region now match surrounding original image
    """

    CATEGORY = "RasterRelay"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("harmonized_image",)
    FUNCTION = "harmonize"
    DESCRIPTION = "Matches colors of generated region to surrounding original image using Reinhard LAB transfer."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "original_image": ("IMAGE", {"tooltip": "Original unedited image (RGB or RGBA)"}),
                "generated_image": ("IMAGE", {"tooltip": "AI-generated/inpainted image"}),
                "mask": ("MASK", {"tooltip": "Inpainting mask (1 = generated region, 0 = original)"}),
                "strength": ("FLOAT", {"default": 0.85, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "Color correction intensity (0 = no change, 1 = full transfer)"}),
                "blend_radius": ("INT", {"default": 20, "min": 0, "max": 80, "tooltip": "Gaussian blur radius for smooth mask edges"}),
                "margin": ("INT", {"default": 30, "min": 5, "max": 200, "tooltip": "Pixel margin around mask for reference color sampling"}),
                "interior_weight": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "How much correction to apply deep inside the mask. 0 = only at the seam, 1 = full color transfer everywhere."}),
                "edge_boost": ("FLOAT", {"default": 1.2, "min": 1.0, "max": 3.0, "step": 0.05, "tooltip": "Multiplier for correction at the seam region. >1 = stronger seam blending."}),
            }
        }

    def _blur_mask(self, mask, blend_radius):
        """Applies separable Gaussian blur to a BHWC mask tensor."""
        return _blur_mask_wrapper(mask, blend_radius)

    @staticmethod
    def _rgb_to_lab(rgb):
        """
        Converts an RGB image tensor (values in [0, 1]) to CIE LAB color space.

        Pipeline: RGB → linear RGB → XYZ (D65) → LAB
        Uses standard sRGB companding and D65 white point (0.95047, 1.0, 1.08883).
        """
        eps = 0.008856
        kappa = 903.3

        linear = torch.where(
            rgb <= 0.04045,
            rgb / 12.92,
            ((rgb + 0.055) / 1.055).clamp(min=1e-10) ** 2.4,
        )

        r, g, b = linear[..., 0], linear[..., 1], linear[..., 2]

        x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
        y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
        z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041

        xn, yn, zn = 0.95047, 1.0, 1.08883

        def f(t):
            return torch.where(
                t > eps,
                t.clamp(min=1e-10) ** (1.0 / 3.0),
                (kappa * t + 16.0) / 116.0,
            )

        fx, fy, fz = f(x / xn), f(y / yn), f(z / zn)

        L = 116.0 * fy - 16.0
        a = 500.0 * (fx - fy)
        b_ch = 200.0 * (fy - fz)

        return torch.stack([L, a, b_ch], dim=-1)

    @staticmethod
    def _lab_to_rgb(lab):
        """
        Converts CIE LAB tensor back to sRGB [0, 1].
        """
        eps = 0.008856
        kappa = 903.3

        L, a, b_ch = lab[..., 0], lab[..., 1], lab[..., 2]

        fy = (L + 16.0) / 116.0
        fx = a / 500.0 + fy
        fz = fy - b_ch / 200.0

        def f_inv(t):
            return torch.where(
                t ** 3 > eps,
                t.clamp(min=0.0) ** 3,
                (116.0 * t - 16.0) / kappa,
            )

        xn, yn, zn = 0.95047, 1.0, 1.08883
        x = f_inv(fx) * xn
        y = f_inv(fy) * yn
        z = f_inv(fz) * zn

        r_lin = x * 3.2404542 + y * -1.5371385 + z * -0.4985314
        g_lin = x * -0.9692660 + y * 1.8760108 + z * 0.0415560
        b_lin = x * 0.0556434 + y * -0.2040259 + z * 1.0572252

        linear = torch.stack([r_lin, g_lin, b_lin], dim=-1)

        srgb = torch.where(
            linear <= 0.0031308,
            linear * 12.92,
            1.055 * linear.clamp(min=1e-10) ** (1.0 / 2.4) - 0.055,
        )

        return srgb.clamp(0.0, 1.0)

    def _dilate_mask(self, mask_bhwc, margin):
        """
        Expands the mask by `margin` pixels using max-pool dilation.
        Returns the dilated mask (BHWC, same device/dtype).
        """
        if margin <= 0:
            return mask_bhwc

        m = mask_bhwc.permute(0, 3, 1, 2)
        k = margin * 2 + 1
        dilated = F.max_pool2d(m, kernel_size=k, stride=1, padding=margin)
        return dilated.permute(0, 2, 3, 1)

    def _erode_mask(self, mask_bhwc, margin):
        """Shrinks the mask by `margin` pixels using min-pool erosion."""
        if margin <= 0:
            return mask_bhwc

        m = mask_bhwc.permute(0, 3, 1, 2)
        k = margin * 2 + 1
        eroded = -F.max_pool2d(-m, kernel_size=k, stride=1, padding=margin)
        return eroded.permute(0, 2, 3, 1).clamp(0.0, 1.0)

    def _correction_weight(self, mask_bhwc, blend_radius, interior_weight=0.6, edge_boost=1.2):
        """
        Builds an inside-mask correction weight. The boundary receives full
        correction (boosted by `edge_boost`), while the interior receives
        `interior_weight` correction so intended edits are not over-neutralized
        but the whole region still follows the reference colour distribution.
        """
        mask_bhwc = mask_bhwc.clamp(0.0, 1.0)
        if blend_radius <= 0:
            return mask_bhwc

        eroded = self._erode_mask(mask_bhwc, blend_radius)
        edge = (mask_bhwc - eroded).clamp(0.0, 1.0)
        edge = self._blur_mask(edge, max(1, blend_radius // 2)).clamp(0.0, 1.0)

        # Apply edge boost (clamp to avoid runaway brightness)
        edge = (edge * edge_boost).clamp(0.0, 1.0)

        return (mask_bhwc * (interior_weight + (1.0 - interior_weight) * edge)).clamp(0.0, 1.0)

    @staticmethod
    def _channel_stats(lab, mask_bool):
        """
        Computes per-channel mean and std for the 3 LAB channels,
        using only pixels where mask_bool is True.
        Returns (mean, std) each of shape (3,).
        """
        if mask_bool.sum() == 0:
            return (
                torch.zeros(3, dtype=lab.dtype, device=lab.device),
                torch.ones(3, dtype=lab.dtype, device=lab.device),
            )

        pixels = lab[mask_bool]
        mean = pixels.mean(dim=0)
        std = pixels.std(dim=0).clamp(min=1e-6)
        return mean, std

    def harmonize(self, original_image, generated_image, mask, strength, blend_radius, margin,
                  interior_weight=0.6, edge_boost=1.2):
        if strength <= 0.0:
            return (generated_image.clone(),)

        device = generated_image.device
        dtype = generated_image.dtype

        orig = original_image.to(device=device, dtype=dtype)
        gen = generated_image.to(device=device, dtype=dtype)

        if mask.dim() == 2:
            mask = mask.unsqueeze(0)
        if mask.shape[0] == 1 and gen.shape[0] > 1:
            mask = mask.repeat(gen.shape[0], 1, 1)
        mask = mask.to(device=device, dtype=dtype)

        b, h, w, _ = gen.shape

        if mask.shape[1] != h or mask.shape[2] != w:
            mask_bchw = mask.unsqueeze(1) if mask.dim() == 3 else mask.permute(0, 3, 1, 2)
            mask_resized = F.interpolate(mask_bchw.float(), size=(h, w), mode="bilinear", align_corners=False)
            if mask.dim() == 3:
                mask = mask_resized.squeeze(1)
            else:
                mask = mask_resized.permute(0, 2, 3, 1)

        mask_4d = mask.unsqueeze(-1) if mask.dim() == 3 else mask

        orig_rgb = orig[..., :3]
        gen_rgb = gen[..., :3]

        orig_lab = self._rgb_to_lab(orig_rgb)
        gen_lab = self._rgb_to_lab(gen_rgb)

        mask_bool = mask_4d.squeeze(-1) > 0.5
        dilated_mask = self._dilate_mask(mask_4d, margin)
        ref_bool = (dilated_mask.squeeze(-1) > 0.5) & ~mask_bool

        results = []
        for i in range(b):
            bi_mask = mask_bool[i] if b > 1 else mask_bool[0]
            bi_ref = ref_bool[i] if b > 1 else ref_bool[0]

            ref_mean, ref_std = self._channel_stats(orig_lab[i], bi_ref)
            tgt_mean, tgt_std = self._channel_stats(gen_lab[i], bi_mask)

            lab_i = gen_lab[i]
            corrected = (lab_i - tgt_mean) * (ref_std / tgt_std) + ref_mean

            blended_lab = lab_i * (1.0 - strength) + corrected * strength

            corrected_rgb = self._lab_to_rgb(blended_lab)

            results.append(corrected_rgb)

        corrected_batch = torch.stack(results, dim=0)

        correction_weight = self._correction_weight(mask_4d, blend_radius, interior_weight, edge_boost)
        composited = gen_rgb * (1.0 - correction_weight) + corrected_batch * correction_weight

        if gen.shape[-1] == 4:
            composited = torch.cat([composited, gen[..., 3:4]], dim=-1)

        # Zwolnij pamięć GPU po dużych operacjach
        del orig, gen, orig_rgb, gen_rgb, orig_lab, gen_lab, corrected_batch, correction_weight
        del mask, mask_4d, mask_bool, dilated_mask, ref_bool, results
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return (composited.clamp(0.0, 1.0),)
