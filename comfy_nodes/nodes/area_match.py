import torch
import torch.nn.functional as F


class RasterRelayAreaMatch:
    """
    Matches the generated area's exposure, contrast and color to the surrounding
    original area. Uses Reinhard transfer in LAB space WITHOUT preserving luminance
    - so brightness/exposure is also corrected.

    Algorithm:
    1. Sample color statistics (mean/std in LAB) from surrounding ring.
    2. Sample from generated area inside mask.
    3. Full Reinhard transfer: match both chrominance AND luminance.
    4. Blend result with feathered mask for seamless transition.
    """

    CATEGORY = "RasterRelay"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("matched_image",)
    FUNCTION = "match_area"
    DESCRIPTION = "Matches generated area's exposure, contrast and color to the surrounding area."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "original_image": ("IMAGE", {"tooltip": "Original unedited image"}),
                "generated_image": ("IMAGE", {"tooltip": "Generated/inpainted image to correct"}),
                "mask": ("MASK", {"tooltip": "Inpainting mask (1 = generated, 0 = original)"}),
                "strength": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "Correction strength.",
                }),
                "margin": ("INT", {
                    "default": 40, "min": 10, "max": 200, "step": 5,
                    "tooltip": "Pixel margin around mask for reference color sampling.",
                }),
                "blur_radius": ("INT", {
                    "default": 20, "min": 0, "max": 80, "step": 1,
                    "tooltip": "Gaussian blur radius for smooth mask edges.",
                }),
            }
        }

    @staticmethod
    def _gaussian_kernel1d(kernel_size, sigma, device):
        x = torch.arange(kernel_size, dtype=torch.float32, device=device) - (kernel_size - 1) / 2
        kernel = torch.exp(-0.5 * (x / sigma) ** 2)
        return kernel / kernel.sum()

    def _blur_2d(self, image, radius):
        if radius <= 0:
            return image
        device = image.device
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
        kernel_h = kernel.view(1, 1, 1, k).repeat(c, 1, 1, 1)
        kernel_v = kernel.view(1, 1, k, 1).repeat(c, 1, 1, 1)
        x = image.permute(0, 3, 1, 2)
        pad = k // 2
        x = F.pad(x, (pad, pad, 0, 0), mode="reflect")
        x = F.conv2d(x, kernel_h, padding=0, groups=c)
        x = F.pad(x, (0, 0, pad, pad), mode="reflect")
        x = F.conv2d(x, kernel_v, padding=0, groups=c)
        return x.permute(0, 2, 3, 1)

    @staticmethod
    def _rgb_to_lab(rgb):
        rgb = rgb.clamp(1e-6, 1.0 - 1e-6)
        srgb_r = rgb[..., 0:1]
        srgb_g = rgb[..., 1:2]
        srgb_b = rgb[..., 2:3]
        linear_r = torch.where(srgb_r > 0.04045, ((srgb_r + 0.055) / 1.055) ** 2.4, srgb_r / 12.92)
        linear_g = torch.where(srgb_g > 0.04045, ((srgb_g + 0.055) / 1.055) ** 2.4, srgb_g / 12.92)
        linear_b = torch.where(srgb_b > 0.04045, ((srgb_b + 0.055) / 1.055) ** 2.4, srgb_b / 12.92)
        x = linear_r * 0.4124564 + linear_g * 0.3575761 + linear_b * 0.1804375
        y = linear_r * 0.2126729 + linear_g * 0.7151522 + linear_b * 0.0721750
        z = linear_r * 0.0193339 + linear_g * 0.1191920 + linear_b * 0.9503041
        xyz_ref_x = 0.95047
        xyz_ref_y = 1.0
        xyz_ref_z = 1.08883
        xn, yn, zn = x / xyz_ref_x, y / xyz_ref_y, z / xyz_ref_z
        delta = 6.0 / 29.0
        delta3 = delta ** 3
        fx = torch.where(xn > delta3, xn ** (1.0 / 3.0), xn / (3.0 * delta ** 2) + 4.0 / 29.0)
        fy = torch.where(yn > delta3, yn ** (1.0 / 3.0), yn / (3.0 * delta ** 2) + 4.0 / 29.0)
        fz = torch.where(zn > delta3, zn ** (1.0 / 3.0), zn / (3.0 * delta ** 2) + 4.0 / 29.0)
        L = 116.0 * fy - 16.0
        a = 500.0 * (fx - fy)
        b_lab = 200.0 * (fy - fz)
        return torch.cat([L, a, b_lab], dim=-1)

    @staticmethod
    def _lab_to_rgb(lab):
        L = lab[..., 0:1]
        a = lab[..., 1:2]
        b_lab = lab[..., 2:3]
        fy = (L + 16.0) / 116.0
        fx = a / 500.0 + fy
        fz = fy - b_lab / 200.0
        delta = 6.0 / 29.0
        delta3 = delta ** 3
        xn = torch.where(fx > delta, fx ** 3.0, 3.0 * delta ** 2 * (fx - 4.0 / 29.0))
        yn = torch.where(fy > delta, fy ** 3.0, 3.0 * delta ** 2 * (fy - 4.0 / 29.0))
        zn = torch.where(fz > delta, fz ** 3.0, 3.0 * delta ** 2 * (fz - 4.0 / 29.0))
        x = xn * 0.95047
        y = yn * 1.0
        z = zn * 1.08883
        linear_r = x * 3.2404542 + y * -1.5371385 + z * -0.4985314
        linear_g = x * -0.9692660 + y * 1.8760108 + z * 0.0415560
        linear_b = x * 0.0556434 + y * -0.2040259 + z * 1.0572252
        linear = torch.cat([linear_r, linear_g, linear_b], dim=-1)
        srgb = torch.where(
            linear > 0.0031308,
            1.055 * (linear ** (1.0 / 2.4)) - 0.055,
            12.92 * linear,
        )
        return srgb

    def match_area(self, original_image, generated_image, mask, strength, margin, blur_radius):
        if strength <= 0.0:
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

        # 1. Create surrounding ring
        dilate_radius = margin // 2
        if dilate_radius < 1:
            dilate_radius = 1
        dilated = self._blur_2d(mask, dilate_radius)
        surrounding_mask = (dilated - mask).clamp(0.0, 1.0)

        # 2. Convert to LAB
        orig_lab = self._rgb_to_lab(orig_rgb)
        gen_lab = self._rgb_to_lab(gen_rgb)

        # 3. Weighted mean/std from surrounding (original)
        surr_w = surrounding_mask.clamp(0.0, 1.0)
        surr_total = surr_w.sum(dim=(1, 2), keepdim=True).clamp(min=1.0)

        ref_mean = (orig_lab * surr_w).sum(dim=(1, 2), keepdim=True) / surr_total
        diff_sq = (orig_lab - ref_mean).pow(2) * surr_w
        ref_std = (diff_sq.sum(dim=(1, 2), keepdim=True) / surr_total).sqrt().clamp(min=1e-6)

        # 4. Weighted mean/std from generated area
        gen_w = mask.clamp(0.0, 1.0)
        gen_total = gen_w.sum(dim=(1, 2), keepdim=True).clamp(min=1.0)

        gen_mean = (gen_lab * gen_w).sum(dim=(1, 2), keepdim=True) / gen_total
        diff_sq2 = (gen_lab - gen_mean).pow(2) * gen_w
        gen_std = (diff_sq2.sum(dim=(1, 2), keepdim=True) / gen_total).sqrt().clamp(min=1e-6)

        # 5. Full Reinhard transfer (including luminance)
        corrected_lab = (gen_lab - gen_mean) * (ref_std / gen_std) + ref_mean

        # 6. Blend with strength
        blended_lab = gen_lab + (corrected_lab - gen_lab) * strength

        # 7. Back to RGB
        blended_rgb = self._lab_to_rgb(blended_lab)

        # 8. Feathered mask for smooth transition
        feathered = self._blur_2d(mask, blur_radius).clamp(0.0, 1.0)

        # 9. Composite: blend corrected area with original generated
        result = gen_rgb * (1.0 - feathered) + blended_rgb * feathered
        result = result.clamp(0.0, 1.0)

        if gen.shape[-1] == 4:
            result = torch.cat([result, gen[..., 3:4]], dim=-1)

        return (result,)
