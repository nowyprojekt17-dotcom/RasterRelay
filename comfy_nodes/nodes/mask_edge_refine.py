import torch
import torch.nn.functional as F


class RasterRelayMaskEdgeRefine:
    """
    Snaps a soft selection mask to the real image edges using a guided filter.

    Problem: a Photoshop selection (even feathered) cuts through fine structures
    like hair strands with a smooth curve that ignores the actual content. When
    that mask is used for compositing, strands get blended with a halo.

    The guided filter (He et al.) re-estimates the mask as a locally-linear
    function of the guide image, so the mask transition follows real edges:
    strands stay crisp, flat areas keep the smooth feather.

    Only the transition band is refined - pixels where the input mask is fully
    inside (>= 0.995) or fully outside (<= 0.005) are preserved exactly, so the
    edit region and the protected region never change.
    """

    CATEGORY = "RasterRelay"
    RETURN_TYPES = ("MASK",)
    RETURN_NAMES = ("refined_mask",)
    FUNCTION = "refine"
    DESCRIPTION = "Edge-aware mask refinement (guided filter): the mask transition snaps to real image edges like hair strands."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {"tooltip": "Guide image (the original crop)"}),
                "mask": ("MASK", {"tooltip": "Soft selection mask to refine"}),
                "radius": ("INT", {
                    "default": 8, "min": 2, "max": 64, "step": 1,
                    "tooltip": "Guided-filter window radius (px). ~ width of the structures to snap to.",
                }),
                "edge_sensitivity": ("FLOAT", {
                    "default": 0.02, "min": 0.001, "max": 0.5, "step": 0.001,
                    "tooltip": "Lower = snaps harder to edges (eps of the guided filter).",
                }),
                "strength": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "Blend between the input mask (0) and the refined mask (1).",
                }),
            }
        }

    @staticmethod
    def _box(x, r):
        """Separable box filter on BCHW with reflect padding."""
        k = 2 * r + 1
        kernel = torch.ones(1, 1, 1, k, device=x.device, dtype=x.dtype) / k
        c = x.shape[1]
        kh = kernel.repeat(c, 1, 1, 1)
        kv = kernel.view(1, 1, k, 1).repeat(c, 1, 1, 1)
        x = F.pad(x, (r, r, 0, 0), mode="reflect")
        x = F.conv2d(x, kh, groups=c)
        x = F.pad(x, (0, 0, r, r), mode="reflect")
        x = F.conv2d(x, kv, groups=c)
        return x

    def refine(self, image, mask, radius, edge_sensitivity, strength):
        if strength <= 0.0:
            return (mask.clone(),)

        device = image.device
        dtype = image.dtype

        # normalize mask to B1HW at image resolution
        if mask.dim() == 2:
            mask = mask.unsqueeze(0)
        m = mask.to(device=device, dtype=dtype).unsqueeze(1)  # B1HW
        h, w = image.shape[1:3]
        if m.shape[2:] != (h, w):
            m = F.interpolate(m, size=(h, w), mode="bilinear", align_corners=False)
        if m.shape[0] == 1 and image.shape[0] > 1:
            m = m.repeat(image.shape[0], 1, 1, 1)

        # guide = luma of the image, B1HW
        rgb = image[..., :3].to(device=device, dtype=dtype).permute(0, 3, 1, 2)
        lw = torch.tensor([0.2126, 0.7152, 0.0722], device=device, dtype=dtype).view(1, 3, 1, 1)
        I = (rgb * lw).sum(dim=1, keepdim=True)

        r = int(radius)
        eps = float(edge_sensitivity) ** 2

        mean_I = self._box(I, r)
        mean_p = self._box(m, r)
        corr_Ip = self._box(I * m, r)
        corr_II = self._box(I * I, r)
        var_I = (corr_II - mean_I * mean_I).clamp(min=0.0)
        cov_Ip = corr_Ip - mean_I * mean_p
        a = cov_Ip / (var_I + eps)
        b = mean_p - a * mean_I
        q = (self._box(a, r) * I + self._box(b, r)).clamp(0.0, 1.0)

        refined = m + (q - m) * strength
        # never touch fully-inside / fully-outside pixels
        refined = torch.where(m >= 0.995, m, refined)
        refined = torch.where(m <= 0.005, m, refined)
        out = refined.squeeze(1).clamp(0.0, 1.0)

        del rgb, I, mean_I, mean_p, corr_Ip, corr_II, var_I, cov_Ip, a, b, q, refined
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return (out,)
