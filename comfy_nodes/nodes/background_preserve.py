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
                "change_keep_threshold": ("FLOAT", {"default": 0.04, "min": 0.0, "max": 1.0, "step": 0.01}),
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

    def preserve(
        self,
        original_image,
        generated_image,
        mask,
        object_luma_max,
        red_keep_threshold,
        blend_radius,
        change_keep_threshold=0.04,
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

        edit_delta = (gen_rgb - orig_rgb).abs().amax(dim=-1, keepdim=True)

        # object_luma_max and red_keep_threshold remain in the signature so older
        # workflows keep loading; the neutral preserve logic is change-based.
        object_from_change = edit_delta > change_keep_threshold
        keep_generated = object_from_change.to(dtype=dtype) * mask_4d
        keep_generated = self._blur_mask(keep_generated, blend_radius).clamp(0.0, 1.0) * mask_4d

        composited = orig_rgb * (1.0 - keep_generated) + gen_rgb * keep_generated
        if gen.shape[-1] == 4:
            composited = torch.cat([composited, gen[..., 3:4]], dim=-1)
        return (composited.clamp(0.0, 1.0),)
