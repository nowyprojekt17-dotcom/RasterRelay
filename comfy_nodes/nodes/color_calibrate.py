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
