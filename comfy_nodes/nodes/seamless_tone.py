import torch
import torch.nn.functional as F


class RasterRelaySeamlessTone:
    """
    Seamless tone/colour matching by low-frequency diffusion.

    The classic problem: an inpainted region comes out brighter/different in
    colour than its surroundings, so the patch visibly stands out. A single
    global mean/std transfer (Reinhard) cannot fix a spatially varying lighting
    offset and often makes the seam worse.

    This node instead extrapolates the surrounding (unmasked) low-frequency
    colour INTO the masked region, then shifts only the generated patch's low
    frequency to that target. High-frequency detail (the actual generated
    content) is preserved, while brightness/colour AND gradients are matched to
    the surroundings, making the seam disappear.

    Algorithm (per channel, low frequency only):
      W           = 1 - mask                       # known surrounding pixels
      target_lf   = blur(original * W) / blur(W)   # surroundings diffused inward
      gen_lf      = blur(generated)
      correction  = (target_lf - gen_lf) * strength
      result      = generated + correction * mask  # only inside the selection

    `tone_radius` is the Gaussian sigma (px) of the low-frequency field. Larger =
    smoother, hides bigger lighting differences; ~1/4 of the selection radius is
    a good default. Implemented via downsample-blur-upsample so it stays fast
    even on large crops.
    """

    CATEGORY = "RasterRelay"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("toned_image",)
    FUNCTION = "match_tone"
    DESCRIPTION = "Seamless brightness/colour match by diffusing surrounding tone into the masked region (low-frequency, detail-preserving)."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "original_image": ("IMAGE", {"tooltip": "Original unedited crop (colour/brightness reference)"}),
                "generated_image": ("IMAGE", {"tooltip": "Generated/inpainted crop to correct"}),
                "mask": ("MASK", {"tooltip": "Inpaint mask (1 = generated region, 0 = original)"}),
                "tone_radius": ("INT", {
                    "default": 40, "min": 4, "max": 400, "step": 1,
                    "tooltip": "Gaussian sigma (px) of the low-frequency tone field. ~1/4 of the selection radius.",
                }),
                "strength": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "How strongly to pull the patch toward the surrounding tone (1 = full).",
                }),
            }
        }

    @staticmethod
    def _gaussian_kernel1d(k, sigma, device):
        x = torch.arange(k, dtype=torch.float32, device=device) - (k - 1) / 2
        g = torch.exp(-0.5 * (x / sigma) ** 2)
        return g / g.sum()

    def _blur_bchw(self, x, sigma):
        """Separable Gaussian blur on a BCHW tensor, fast via downsample for big sigma."""
        if sigma <= 0.5:
            return x
        device = x.device
        c = x.shape[1]
        # downsample so the effective kernel stays small
        factor = max(1, int(round(sigma / 4.0)))
        if factor > 1:
            h, w = x.shape[2], x.shape[3]
            sh, sw = max(1, h // factor), max(1, w // factor)
            xs = F.interpolate(x, size=(sh, sw), mode="area")
            s = sigma / factor
        else:
            xs = x
            s = sigma
        k = int(s * 4) | 1
        k = max(3, k)
        # clamp kernel to feature size
        k = min(k, (min(xs.shape[2], xs.shape[3]) // 1) | 1)
        if k < 3:
            blurred = xs
        else:
            kernel = self._gaussian_kernel1d(k, max(s, 0.5), device)
            kh = kernel.view(1, 1, 1, k).repeat(c, 1, 1, 1)
            kv = kernel.view(1, 1, k, 1).repeat(c, 1, 1, 1)
            pad = k // 2
            b = F.pad(xs, (pad, pad, 0, 0), mode="reflect")
            b = F.conv2d(b, kh, groups=c)
            b = F.pad(b, (0, 0, pad, pad), mode="reflect")
            blurred = F.conv2d(b, kv, groups=c)
        if factor > 1:
            blurred = F.interpolate(blurred, size=(x.shape[2], x.shape[3]), mode="bilinear", align_corners=False)
        return blurred

    def match_tone(self, original_image, generated_image, mask, tone_radius, strength):
        if strength <= 0.0:
            return (generated_image.clone(),)

        device = generated_image.device
        dtype = generated_image.dtype
        orig = original_image.to(device=device, dtype=dtype)
        gen = generated_image.to(device=device, dtype=dtype)

        orig_rgb = orig[..., :3]
        gen_rgb = gen[..., :3]

        # normalize mask to BHW1 at generated resolution
        if mask.dim() == 2:
            mask = mask.unsqueeze(0)
        if mask.dim() == 3:
            mask = mask.unsqueeze(-1)
        mask = mask.to(device=device, dtype=dtype)
        if mask.shape[0] == 1 and gen.shape[0] > 1:
            mask = mask.repeat(gen.shape[0], 1, 1, 1)
        h, w = gen.shape[1:3]
        if mask.shape[1:3] != (h, w):
            mp = F.interpolate(mask.permute(0, 3, 1, 2), size=(h, w), mode="bilinear", align_corners=False)
            mask = mp.permute(0, 2, 3, 1)
        mask = mask.clamp(0.0, 1.0)

        sigma = float(tone_radius)
        W = (1.0 - mask)  # BHW1, known surroundings

        orig_bchw = orig_rgb.permute(0, 3, 1, 2)
        gen_bchw = gen_rgb.permute(0, 3, 1, 2)
        W_bchw = W.permute(0, 3, 1, 2)

        eps = 1e-4
        num = self._blur_bchw(orig_bchw * W_bchw, sigma)
        den = self._blur_bchw(W_bchw, sigma).clamp(min=eps)
        target_lf = num / den
        gen_lf = self._blur_bchw(gen_bchw, sigma)

        correction = (target_lf - gen_lf) * strength
        result_bchw = gen_bchw + correction * mask.permute(0, 3, 1, 2)
        result = result_bchw.permute(0, 2, 3, 1).clamp(0.0, 1.0)

        if gen.shape[-1] == 4:
            result = torch.cat([result, gen[..., 3:4]], dim=-1)

        del orig_bchw, gen_bchw, W_bchw, num, den, target_lf, gen_lf, correction, result_bchw
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return (result,)
