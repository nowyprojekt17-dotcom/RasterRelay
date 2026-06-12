import torch
import torch.nn.functional as F


class RasterRelayBackgroundPreserve:
    """
    Preserves original background pixels inside a broad edit mask while keeping
    generated object/color changes.

    This is useful for object color edits where the generation support mask
    intentionally includes surrounding context, but the background should not be
    visibly rewritten by the model.
    """

    CATEGORY = "RasterRelay"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("preserved_image",)
    FUNCTION = "preserve"
    DESCRIPTION = "Keeps generated object edits while restoring original background inside broad masks."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "original_image": ("IMAGE", {"tooltip": "Original crop"}),
                "generated_image": ("IMAGE", {"tooltip": "Generated crop"}),
                "mask": ("MASK", {"tooltip": "Crop-local edit mask"}),
                "object_luma_max": ("FLOAT", {"default": 0.58, "min": 0.0, "max": 1.0, "step": 0.01}),
                "red_keep_threshold": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 1.0, "step": 0.01}),
                "blend_radius": ("INT", {"default": 10, "min": 0, "max": 50}),
            },
            "optional": {
                "change_keep_threshold": ("FLOAT", {
                    "default": 0.08, "min": 0.0, "max": 1.0, "step": 0.01,
                    "tooltip": "Content-change level treated as intentional edit. Below = unintended tone drift, restored to original; above = kept generated. Lower it for very subtle edits (e.g. light retouch).",
                }),
            }
        }

    @staticmethod
    def _blur_mask(mask, radius):
        if radius <= 0:
            return mask

        kernel_size = radius * 6 + 1
        if kernel_size % 2 == 0:
            kernel_size += 1
        sigma = radius / 3.0
        x = torch.arange(kernel_size, dtype=torch.float32, device=mask.device) - (kernel_size - 1) / 2
        kernel = torch.exp(-0.5 * (x / sigma) ** 2)
        kernel = kernel / kernel.sum()

        m = mask.permute(0, 3, 1, 2)
        m = F.pad(m, (kernel_size // 2, kernel_size // 2, 0, 0), mode="replicate")
        m = F.conv2d(m, kernel.view(1, 1, 1, kernel_size), padding="valid")
        m = F.pad(m, (0, 0, kernel_size // 2, kernel_size // 2), mode="replicate")
        m = F.conv2d(m, kernel.view(1, 1, kernel_size, 1), padding="valid")
        return m.permute(0, 2, 3, 1)

    @staticmethod
    def _blur_rgb(img_bhwc, sigma):
        """Light Gaussian blur of a BHWC RGB tensor (denoises the delta map)."""
        if sigma <= 0:
            return img_bhwc
        k = int(sigma * 4) | 1
        k = max(3, k)
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

    def preserve(
        self,
        original_image,
        generated_image,
        mask,
        object_luma_max,
        red_keep_threshold,
        blend_radius,
        change_keep_threshold=0.08,
    ):
        device = generated_image.device
        dtype = generated_image.dtype
        orig = original_image.to(device=device, dtype=dtype)
        gen = generated_image.to(device=device, dtype=dtype)

        if mask.dim() == 2:
            mask = mask.unsqueeze(0)
        if mask.shape[0] == 1 and gen.shape[0] > 1:
            mask = mask.repeat(gen.shape[0], 1, 1)
        mask = mask.to(device=device, dtype=dtype)

        h, w = gen.shape[1:3]
        if mask.shape[1:3] != (h, w):
            mask_bchw = mask.unsqueeze(1)
            mask = F.interpolate(mask_bchw, size=(h, w), mode="bilinear", align_corners=False).squeeze(1)

        mask_4d = mask.unsqueeze(-1).clamp(0.0, 1.0)
        orig_rgb = orig[..., :3]
        gen_rgb = gen[..., :3]

        # Change magnitude on lightly blurred images: photographic grain and
        # pixel noise don't trigger "intent", only real content change does.
        # Measured on real runs the distribution is bimodal: unintended tone
        # drift sits below ~0.05, intentional edits above ~0.15, so a smooth
        # sigmoid around change_keep_threshold separates them robustly.
        orig_s = self._blur_rgb(orig_rgb, 2.0)
        gen_s = self._blur_rgb(gen_rgb, 2.0)
        edit_delta = (gen_s - orig_s).abs().amax(dim=-1, keepdim=True)

        softness = 0.02
        keep_generated = torch.sigmoid((edit_delta - change_keep_threshold) / softness)
        # hard dead-zones outside the transition band: pure drift is restored
        # EXACTLY to the original, clear intent is kept EXACTLY as generated
        keep_generated = torch.where(edit_delta <= change_keep_threshold - 2.5 * softness,
                                     torch.zeros_like(keep_generated), keep_generated)
        keep_generated = torch.where(edit_delta >= change_keep_threshold + 2.5 * softness,
                                     torch.ones_like(keep_generated), keep_generated)
        keep_generated = keep_generated * mask_4d
        # Asymmetric soft transition: DILATE keep before blurring so the
        # gen-vs-restored blend happens entirely OUTSIDE the edited object
        # (in background territory). A symmetric blur would bleed the
        # original object's pixels (e.g. the removed item) back at its edge.
        if blend_radius > 0:
            k = 2 * int(blend_radius) + 1
            kd = keep_generated.permute(0, 3, 1, 2)
            kd = F.max_pool2d(kd, kernel_size=k, stride=1, padding=k // 2)
            keep_generated = kd.permute(0, 2, 3, 1)
        # object_luma_max and red_keep_threshold remain in the signature so older
        # workflows keep loading; the neutral preserve logic is change-based.
        keep_generated = self._blur_mask(keep_generated, blend_radius).clamp(0.0, 1.0) * mask_4d

        composited = orig_rgb * (1.0 - keep_generated) + gen_rgb * keep_generated
        if gen.shape[-1] == 4:
            composited = torch.cat([composited, gen[..., 3:4]], dim=-1)
        return (composited.clamp(0.0, 1.0),)
