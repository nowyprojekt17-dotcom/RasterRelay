import torch
import torch.nn.functional as F


class RasterRelayColorCalibrate:
    """
    Measures and inverts the model's systematic colour response.

    Insight: inside the edit crop there are many pixels that SHOULD be
    identical to the original (background/skin the model re-rendered without
    intending to change - the 'drift' population). Those pixels form
    calibration pairs (original -> generated). We fit a per-channel affine
    response gen = a*orig + b on them, invert it, and apply the inverse to the
    generated image. This removes the model's global colour/exposure cast from
    the WHOLE result - including the intentionally edited region - without
    undoing the semantic edit itself (an affine fit cannot revert brown->green;
    it only removes the systematic bias measured on should-be-identical areas).

    Fitting is regularised and clamped, and falls back to identity when there
    are too few calibration pixels.
    """

    CATEGORY = "RasterRelay"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("calibrated_image",)
    FUNCTION = "calibrate"
    DESCRIPTION = "Fits the model's colour drift on should-be-unchanged pixels and inverts it on the whole generated image (intent-safe cast removal)."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "original_image": ("IMAGE", {"tooltip": "Original crop (reference)"}),
                "generated_image": ("IMAGE", {"tooltip": "Generated crop to calibrate"}),
                "mask": ("MASK", {"tooltip": "Edit mask (1 = generated region)"}),
                "drift_threshold": ("FLOAT", {
                    "default": 0.10, "min": 0.01, "max": 1.0, "step": 0.01,
                    "tooltip": "Max content change for a pixel to count as a calibration pair (same as BackgroundPreserve threshold).",
                }),
                "strength": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "How much of the measured cast to remove.",
                }),
            }
        }

    @staticmethod
    def _blur_rgb(img_bhwc, sigma):
        if sigma <= 0:
            return img_bhwc
        k = max(3, int(sigma * 4) | 1)
        x = torch.arange(k, dtype=torch.float32, device=img_bhwc.device) - (k - 1) / 2
        kernel = torch.exp(-0.5 * (x / sigma) ** 2)
        kernel = kernel / kernel.sum()
        c = img_bhwc.shape[-1]
        kh = kernel.view(1, 1, 1, k).repeat(c, 1, 1, 1)
        kv = kernel.view(1, 1, k, 1).repeat(c, 1, 1, 1)
        b = img_bhwc.permute(0, 3, 1, 2)
        pad = k // 2
        b = F.pad(b, (pad, pad, 0, 0), mode="reflect")
        b = F.conv2d(b, kh, groups=c)
        b = F.pad(b, (0, 0, pad, pad), mode="reflect")
        b = F.conv2d(b, kv, groups=c)
        return b.permute(0, 2, 3, 1)

    def calibrate(self, original_image, generated_image, mask, drift_threshold, strength):
        if strength <= 0.0:
            return (generated_image.clone(),)

        device = generated_image.device
        dtype = generated_image.dtype
        orig = original_image.to(device=device, dtype=dtype)[..., :3]
        gen_full = generated_image.to(device=device, dtype=dtype)
        gen = gen_full[..., :3]

        if mask.dim() == 2:
            mask = mask.unsqueeze(0)
        m = mask.to(device=device, dtype=dtype)
        h, w = gen.shape[1:3]
        if m.shape[1:3] != (h, w):
            m = F.interpolate(m.unsqueeze(1), size=(h, w), mode="bilinear", align_corners=False).squeeze(1)
        if m.shape[0] == 1 and gen.shape[0] > 1:
            m = m.repeat(gen.shape[0], 1, 1)

        # calibration pairs: re-rendered pixels whose CONTENT did not change
        # (smooth delta below threshold). Use blurred images so grain doesn't
        # disqualify pixels.
        orig_s = self._blur_rgb(orig, 2.0)
        gen_s = self._blur_rgb(gen, 2.0)
        delta = (gen_s - orig_s).abs().amax(dim=-1)          # BHW
        pairs = (m > 0.5) & (delta < drift_threshold)

        n = pairs.sum()
        total = pairs.numel()
        if n < max(256, int(0.01 * total)):
            # not enough evidence - identity
            return (gen_full.clone(),)

        out = gen.clone()
        for c in range(3):
            g = gen_s[..., c][pairs]
            o = orig_s[..., c][pairs]
            g_mean, o_mean = g.mean(), o.mean()
            var_g = ((g - g_mean) ** 2).mean()
            cov = ((g - g_mean) * (o - o_mean)).mean()
            # ridge toward identity: blend the LS slope with 1.0 by evidence
            a = cov / (var_g + 1e-4)
            a = a.clamp(0.7, 1.4)
            b = (o_mean - a * g_mean).clamp(-0.15, 0.15)
            corrected = gen[..., c] * a + b
            out[..., c] = gen[..., c] + (corrected - gen[..., c]) * strength

        out = out.clamp(0.0, 1.0)
        if gen_full.shape[-1] == 4:
            out = torch.cat([out, gen_full[..., 3:4]], dim=-1)
        return (out,)


class RasterRelayReferenceColorLock:
    """
    Late colour guard for masked Photoshop edits.

    ColorCalibrate removes a measured global model cast. This node runs near
    the end of the workflow and enforces a stricter invariant: masked pixels
    that only drifted in colour are restored exactly to the source, while truly
    changed pixels get their low-frequency chroma pulled back toward the source
    and surrounding palette.
    """

    CATEGORY = "RasterRelay"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("locked_image",)
    FUNCTION = "lock_color"
    DESCRIPTION = "Restores drifted masked pixels to the source and locks changed pixels to source colour/chroma."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "original_image": ("IMAGE", {"tooltip": "Original crop/reference image"}),
                "generated_image": ("IMAGE", {"tooltip": "Generated crop after tone/grain correction"}),
                "mask": ("MASK", {"tooltip": "Crop-local edit mask"}),
                "lock_threshold": ("FLOAT", {
                    "default": 0.075, "min": 0.005, "max": 0.5, "step": 0.005,
                    "tooltip": "Smoothed RGB delta below this is treated as unwanted colour drift and restored exactly.",
                }),
                "transition_width": ("FLOAT", {
                    "default": 0.025, "min": 0.001, "max": 0.2, "step": 0.001,
                    "tooltip": "Soft transition between exact restore and changed-content colour lock.",
                }),
                "blur_radius": ("INT", {
                    "default": 48, "min": 4, "max": 400, "step": 1,
                    "tooltip": "Low-frequency radius used for source palette estimation.",
                }),
                "chroma_strength": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "How strongly changed pixels inherit source/reference chroma.",
                }),
                "luma_strength": ("FLOAT", {
                    "default": 0.35, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "How strongly changed pixels inherit source/reference low-frequency luminance.",
                }),
            },
            "optional": {
                "source_chroma_strength": ("FLOAT", {
                    "default": 0.0, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "Final hard colour lock. 1 keeps source RGB channel differences while using generated luminance.",
                }),
                "source_luma_strength": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "How much generated luminance/structure survives the source-chroma lock.",
                }),
                "source_saturation_strength": ("FLOAT", {
                    "default": 0.0, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "Final perceptual colour lock. 1 keeps source HSV hue/saturation while using generated value.",
                }),
            }
        }

    @staticmethod
    def _normalize_mask(mask, image, dtype):
        if mask.dim() == 2:
            mask = mask.unsqueeze(0)
        if mask.dim() == 3:
            mask = mask.unsqueeze(-1)
        mask = mask.to(device=image.device, dtype=dtype)
        if mask.shape[0] == 1 and image.shape[0] > 1:
            mask = mask.repeat(image.shape[0], 1, 1, 1)
        h, w = image.shape[1:3]
        if mask.shape[1:3] != (h, w):
            mask = F.interpolate(
                mask.permute(0, 3, 1, 2),
                size=(h, w),
                mode="bilinear",
                align_corners=False,
            ).permute(0, 2, 3, 1)
        return mask.clamp(0.0, 1.0)

    @staticmethod
    def _gaussian_kernel1d(k, sigma, device):
        x = torch.arange(k, dtype=torch.float32, device=device) - (k - 1) / 2
        kernel = torch.exp(-0.5 * (x / sigma) ** 2)
        return kernel / kernel.sum()

    def _blur_bchw(self, x, sigma):
        if sigma <= 0.5:
            return x
        device = x.device
        c = x.shape[1]
        factor = max(1, int(round(float(sigma) / 4.0)))
        if factor > 1:
            h, w = x.shape[2:4]
            xs = F.interpolate(x, size=(max(1, h // factor), max(1, w // factor)), mode="area")
            sigma = float(sigma) / factor
        else:
            xs = x
            sigma = float(sigma)

        k = int(sigma * 4) | 1
        k = max(3, k)
        k = min(k, (min(xs.shape[2], xs.shape[3]) // 1) | 1)
        if k < 3:
            blurred = xs
        else:
            kernel = self._gaussian_kernel1d(k, max(sigma, 0.5), device)
            kh = kernel.view(1, 1, 1, k).repeat(c, 1, 1, 1)
            kv = kernel.view(1, 1, k, 1).repeat(c, 1, 1, 1)
            pad = k // 2
            blurred = F.pad(xs, (pad, pad, 0, 0), mode="reflect")
            blurred = F.conv2d(blurred, kh, groups=c)
            blurred = F.pad(blurred, (0, 0, pad, pad), mode="reflect")
            blurred = F.conv2d(blurred, kv, groups=c)

        if factor > 1:
            blurred = F.interpolate(blurred, size=x.shape[2:4], mode="bilinear", align_corners=False)
        return blurred

    def _drift_weight(self, orig_rgb, gen_rgb, mask, lock_threshold, transition_width):
        orig_s = self._blur_bchw(orig_rgb.permute(0, 3, 1, 2), 2.0).permute(0, 2, 3, 1)
        gen_s = self._blur_bchw(gen_rgb.permute(0, 3, 1, 2), 2.0).permute(0, 2, 3, 1)
        delta = (gen_s - orig_s).abs().amax(dim=-1, keepdim=True)
        softness = max(float(transition_width), 1e-4)
        weight = torch.sigmoid((float(lock_threshold) - delta) / softness)
        weight = torch.where(
            delta <= float(lock_threshold) - 2.5 * softness,
            torch.ones_like(weight),
            weight,
        )
        weight = torch.where(
            delta >= float(lock_threshold) + 2.5 * softness,
            torch.zeros_like(weight),
            weight,
        )
        active_mask = (mask > 1e-4).to(dtype=mask.dtype)
        return weight * active_mask

    @staticmethod
    def _rgb_to_hsv(rgb):
        r = rgb[..., 0:1]
        g = rgb[..., 1:2]
        b = rgb[..., 2:3]
        maxc = rgb.amax(dim=-1, keepdim=True)
        minc = rgb.amin(dim=-1, keepdim=True)
        delta = maxc - minc
        safe_delta = delta.clamp(min=1e-6)
        hue = torch.zeros_like(maxc)

        red_is_max = (maxc == r) & (delta > 1e-6)
        green_is_max = (maxc == g) & (delta > 1e-6)
        blue_is_max = (maxc == b) & (delta > 1e-6)
        hue = torch.where(red_is_max, ((g - b) / safe_delta).remainder(6.0), hue)
        hue = torch.where(green_is_max, ((b - r) / safe_delta) + 2.0, hue)
        hue = torch.where(blue_is_max, ((r - g) / safe_delta) + 4.0, hue)
        hue = hue / 6.0
        saturation = torch.where(maxc > 1e-6, delta / maxc.clamp(min=1e-6), torch.zeros_like(maxc))
        return hue, saturation, maxc

    @staticmethod
    def _hsv_to_rgb(hue, saturation, value):
        hue6 = (hue * 6.0).remainder(6.0)
        chroma = value * saturation
        x = chroma * (1.0 - (hue6.remainder(2.0) - 1.0).abs())
        zeros = torch.zeros_like(chroma)

        r = torch.where(
            hue6 < 1.0,
            chroma,
            torch.where(hue6 < 2.0, x, torch.where(hue6 < 3.0, zeros, torch.where(hue6 < 4.0, zeros, torch.where(hue6 < 5.0, x, chroma)))),
        )
        g = torch.where(
            hue6 < 1.0,
            x,
            torch.where(hue6 < 2.0, chroma, torch.where(hue6 < 3.0, chroma, torch.where(hue6 < 4.0, x, torch.where(hue6 < 5.0, zeros, zeros)))),
        )
        b = torch.where(
            hue6 < 1.0,
            zeros,
            torch.where(hue6 < 2.0, zeros, torch.where(hue6 < 3.0, x, torch.where(hue6 < 4.0, chroma, torch.where(hue6 < 5.0, chroma, x)))),
        )
        m = value - chroma
        return torch.cat([r + m, g + m, b + m], dim=-1)

    def lock_color(
        self,
        original_image,
        generated_image,
        mask,
        lock_threshold,
        transition_width,
        blur_radius,
        chroma_strength,
        luma_strength,
        source_chroma_strength=0.0,
        source_luma_strength=1.0,
        source_saturation_strength=0.0,
    ):
        device = generated_image.device
        dtype = generated_image.dtype
        orig = original_image.to(device=device, dtype=dtype)
        gen = generated_image.to(device=device, dtype=dtype)
        orig_rgb = orig[..., :3]
        gen_rgb = gen[..., :3]
        mask = self._normalize_mask(mask, gen, dtype)

        if chroma_strength <= 0.0 and luma_strength <= 0.0 and lock_threshold <= 0.0:
            return (gen.clone(),)

        drift_weight = self._drift_weight(orig_rgb, gen_rgb, mask, lock_threshold, transition_width)
        changed_weight = (mask * (1.0 - drift_weight)).clamp(0.0, 1.0)

        orig_bchw = orig_rgb.permute(0, 3, 1, 2)
        gen_bchw = gen_rgb.permute(0, 3, 1, 2)
        known = (1.0 - mask + drift_weight).clamp(0.0, 1.0).permute(0, 3, 1, 2)
        sigma = float(blur_radius)
        reference_lf = self._blur_bchw(orig_bchw * known, sigma) / self._blur_bchw(known, sigma).clamp(min=1e-4)
        generated_lf = self._blur_bchw(gen_bchw, sigma)
        correction = reference_lf - generated_lf

        luma_weights = torch.tensor([0.2126, 0.7152, 0.0722], device=device, dtype=dtype).view(1, 3, 1, 1)
        correction_luma = (correction * luma_weights).sum(dim=1, keepdim=True)
        correction_chroma = correction - correction_luma
        correction = correction_chroma * float(chroma_strength) + correction_luma * float(luma_strength)

        corrected = (gen_bchw + correction * changed_weight.permute(0, 3, 1, 2)).permute(0, 2, 3, 1)
        out_rgb = corrected * (1.0 - drift_weight) + orig_rgb * drift_weight

        source_saturation_strength = float(source_saturation_strength)
        if source_saturation_strength > 0.0:
            orig_hue, orig_sat, _orig_value = self._rgb_to_hsv(orig_rgb)
            _out_hue, _out_sat, out_value = self._rgb_to_hsv(out_rgb)
            source_hsv_rgb = self._hsv_to_rgb(orig_hue, orig_sat, out_value)
            hsv_mix = (mask * source_saturation_strength).clamp(0.0, 1.0)
            out_rgb = out_rgb * (1.0 - hsv_mix) + source_hsv_rgb * hsv_mix

        source_chroma_strength = float(source_chroma_strength)
        if source_chroma_strength > 0.0:
            # This is the final hard colour lock. Preserve generated structure
            # as luminance, but take colour from the source. With strength=1,
            # pairwise RGB channel differences (R-G, R-B, G-B) match the
            # original exactly; luma is clipped only to keep channels in gamut.
            luma_nhwc = luma_weights.view(1, 1, 1, 3)
            orig_luma = (orig_rgb * luma_nhwc).sum(dim=-1, keepdim=True)
            out_luma = (out_rgb * luma_nhwc).sum(dim=-1, keepdim=True)
            luma_delta = (out_luma - orig_luma) * float(source_luma_strength)
            luma_delta = luma_delta.clamp(
                min=-orig_rgb.amin(dim=-1, keepdim=True),
                max=1.0 - orig_rgb.amax(dim=-1, keepdim=True),
            )
            source_chroma_rgb = orig_rgb + luma_delta
            chroma_mix = (mask * source_chroma_strength).clamp(0.0, 1.0)
            out_rgb = out_rgb * (1.0 - chroma_mix) + source_chroma_rgb * chroma_mix

        out = out_rgb.clamp(0.0, 1.0)

        if gen.shape[-1] == 4:
            out = torch.cat([out, gen[..., 3:4]], dim=-1)

        del orig_bchw, gen_bchw, known, reference_lf, generated_lf, correction, corrected
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return (out,)
