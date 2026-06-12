import torch
import torch.nn.functional as F


class RasterRelayColorMatch:
    """Global color transfer — matches colors, tones and contrast of the output
    image to the original input image.

    Useful after Flux Klein (or any VAE pipeline) to correct global color
    shifts that the model introduces even outside the edited area.

    Three methods available:
      - reinhard_lab : Classic Reinhard color transfer in CIE LAB space.
        Separates luminance from chrominance for perceptually natural results.
      - histogram_match : Per-channel cumulative-distribution matching.
        Handles arbitrary colour distributions and extreme shifts.
      - mkl_transfer : Monge-Kantorovitch Linear transfer via covariance SVD.
        Best quality — transfers full inter-channel covariance structure.
    """

    CATEGORY = "RasterRelay"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("corrected_image",)
    FUNCTION = "match_colors"
    DESCRIPTION = "Global color transfer from reference to target image. Matches colours, tones, contrast and white balance."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "reference_image": ("IMAGE", {"tooltip": "Original input image — colour reference"}),
                "target_image": ("IMAGE", {"tooltip": "Generated/output image — to be corrected"}),
                "method": (["reinhard_lab", "histogram_match", "mkl_transfer"], {
                    "default": "reinhard_lab",
                    "tooltip": "Colour-transfer algorithm"
                }),
                "strength": ("FLOAT", {"default": 0.85, "min": 0.0, "max": 1.0, "step": 0.05,
                                       "tooltip": "0 = no change, 1 = full correction"}),
                "preserve_luminance": ("BOOLEAN", {"default": True,
                                                   "tooltip": "Transfer only chrominance, keep target luminance"}),
            },
            "optional": {
                "mask": ("MASK", {"tooltip": "Optional mask — correct only inside masked area"}),
            },
        }

    # ------------------------------------------------------------------ #
    #  RGB ↔ CIE LAB  (D65 illuminant, pure PyTorch — no OpenCV)          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _rgb_to_lab(rgb):
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

    # ------------------------------------------------------------------ #
    #  Method 1 — Reinhard colour transfer in LAB                         #
    # ------------------------------------------------------------------ #

    def _reinhard_lab_transfer(self, reference, target, preserve_luminance=False):
        ref_lab = self._rgb_to_lab(reference)
        tgt_lab = self._rgb_to_lab(target)

        ref_mean = ref_lab.mean(dim=(0, 1), keepdim=True)
        ref_std = ref_lab.std(dim=(0, 1), keepdim=True).clamp(min=1e-6)
        tgt_mean = tgt_lab.mean(dim=(0, 1), keepdim=True)
        tgt_std = tgt_lab.std(dim=(0, 1), keepdim=True).clamp(min=1e-6)

        if preserve_luminance:
            ref_mean[..., 0:1] = tgt_mean[..., 0:1]
            ref_std[..., 0:1] = tgt_std[..., 0:1]

        corrected_lab = (tgt_lab - tgt_mean) * (ref_std / tgt_std) + ref_mean
        return self._lab_to_rgb(corrected_lab)

    # ------------------------------------------------------------------ #
    #  Method 2 — Histogram matching (per-channel CDF)                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _histogram_match_channel(source, reference, bins=256):
        src_flat = source.flatten()
        ref_flat = reference.flatten()

        src_hist = torch.histc(src_flat, bins=bins, min=0.0, max=1.0)
        ref_hist = torch.histc(ref_flat, bins=bins, min=0.0, max=1.0)

        src_sum = src_hist.sum()
        ref_sum = ref_hist.sum()
        if src_sum == 0 or ref_sum == 0:
            return source

        src_cdf = torch.cumsum(src_hist, dim=0) / src_sum
        ref_cdf = torch.cumsum(ref_hist, dim=0) / ref_sum

        idx = torch.searchsorted(ref_cdf, src_cdf).clamp(0, bins - 1)
        lut = idx.float() / max(bins - 1, 1)

        src_binned = (source * bins).long().clamp(0, bins - 1)
        matched = lut[src_binned]

        return matched

    def _histogram_match_transfer(self, reference, target):
        result = torch.empty_like(target)
        for c in range(3):
            result[..., c] = self._histogram_match_channel(
                target[..., c], reference[..., c]
            )
        return result.clamp(0.0, 1.0)

    # ------------------------------------------------------------------ #
    #  Method 3 — MKL (Monge-Kantorovitch Linear) transfer                  #
    # ------------------------------------------------------------------ #

    def _mkl_transfer(self, reference, target, preserve_luminance=False):
        if preserve_luminance:
            ref_lab = self._rgb_to_lab(reference)
            tgt_lab = self._rgb_to_lab(target)
            ab_ref = ref_lab[..., 1:]
            ab_tgt = tgt_lab[..., 1:]
            corrected_ab = self._mkl_matrix(ab_ref, ab_tgt)
            corrected_lab = torch.cat([tgt_lab[..., :1], corrected_ab], dim=-1)
            return self._lab_to_rgb(corrected_lab)
        return self._mkl_matrix(reference, target)

    def _mkl_matrix(self, reference, target):
        h_ref, w_ref, c = reference.shape
        h_tgt, w_tgt, _ = target.shape

        n_ref = h_ref * w_ref
        n_tgt = h_tgt * w_tgt

        ref_flat = reference.reshape(n_ref, c)
        tgt_flat = target.reshape(n_tgt, c)

        mu_ref = ref_flat.mean(dim=0, keepdim=True)
        mu_tgt = tgt_flat.mean(dim=0, keepdim=True)

        ref_centered = ref_flat - mu_ref
        tgt_centered = tgt_flat - mu_tgt

        cov_ref = (ref_centered.T @ ref_centered) / max(n_ref - 1, 1)
        cov_tgt = (tgt_centered.T @ tgt_centered) / max(n_tgt - 1, 1)

        U_r, S_r, V_r = torch.linalg.svd(cov_ref)
        U_t, S_t, V_t = torch.linalg.svd(cov_tgt)

        S_r_sqrt = torch.sqrt(S_r.clamp(min=1e-8))
        S_t_inv_sqrt = 1.0 / torch.sqrt(S_t.clamp(min=1e-8))

        sqrt_ref = U_r @ torch.diag(S_r_sqrt) @ V_r
        inv_sqrt_tgt = U_t @ torch.diag(S_t_inv_sqrt) @ V_t

        T = sqrt_ref @ inv_sqrt_tgt

        result = (tgt_centered @ T.T) + mu_ref
        return result.reshape(h_tgt, w_tgt, c).clamp(0.0, 1.0)

    # ------------------------------------------------------------------ #
    #  Mask helpers                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _gaussian_kernel(kernel_size, sigma):
        x = torch.arange(kernel_size, dtype=torch.float32) - (kernel_size - 1) / 2
        kernel = torch.exp(-0.5 * (x / sigma) ** 2)
        kernel = kernel / kernel.sum()
        return kernel

    @staticmethod
    def _blur_mask(mask_4d, radius):
        if radius <= 0:
            return mask_4d

        kernel_size = radius * 6 + 1
        if kernel_size % 2 == 0:
            kernel_size += 1
        sigma = radius / 3.0

        device = mask_4d.device
        kernel = RasterRelayColorMatch._gaussian_kernel(kernel_size, sigma).to(device)

        m = mask_4d.permute(0, 3, 1, 2)
        m = F.pad(m, (kernel_size // 2, kernel_size // 2, 0, 0), mode="replicate")
        m = F.conv2d(m, kernel.view(1, 1, 1, kernel_size), padding="valid")
        m = F.pad(m, (0, 0, kernel_size // 2, kernel_size // 2), mode="replicate")
        m = F.conv2d(m, kernel.view(1, 1, kernel_size, 1), padding="valid")
        return m.permute(0, 2, 3, 1)

    # ------------------------------------------------------------------ #
    #  Main entry point                                                    #
    # ------------------------------------------------------------------ #

    def match_colors(self, reference_image, target_image, method, strength,
                     preserve_luminance=False, mask=None):
        if strength <= 0.0:
            return (target_image.clone(),)

        device = target_image.device
        dtype = target_image.dtype

        ref = reference_image[..., :3].to(device=device, dtype=dtype)
        tgt = target_image.to(device=device, dtype=dtype)

        b = tgt.shape[0]
        if ref.shape[0] == 1 and b > 1:
            ref = ref.repeat(b, 1, 1, 1)

        results = []
        for i in range(b):
            ref_i = ref[i] if ref.shape[0] > 1 else ref[0]
            tgt_i = tgt[i]

            if method == "reinhard_lab":
                corrected = self._reinhard_lab_transfer(ref_i, tgt_i[..., :3], preserve_luminance)
            elif method == "histogram_match":
                corrected = self._histogram_match_transfer(ref_i, tgt_i[..., :3])
            elif method == "mkl_transfer":
                corrected = self._mkl_transfer(ref_i, tgt_i[..., :3], preserve_luminance)
            else:
                corrected = tgt_i[..., :3]

            results.append(corrected)

        corrected_batch = torch.stack(results, dim=0)

        if mask is not None:
            mask = mask.to(device=device, dtype=dtype)
            if mask.dim() == 2:
                mask = mask.unsqueeze(0)
            if mask.dim() == 3:
                mask = mask.unsqueeze(-1)
            if mask.shape[0] == 1 and b > 1:
                mask = mask.repeat(b, 1, 1, 1)

            h, w = tgt.shape[1:3]
            if mask.shape[1:3] != (h, w):
                mp = mask.permute(0, 3, 1, 2)
                mp = F.interpolate(mp, size=(h, w), mode="bilinear", align_corners=False)
                mask = mp.permute(0, 2, 3, 1)

            feathered = self._blur_mask(mask.clamp(0.0, 1.0), radius=3)
            corrected_rgb = corrected_batch[..., :3]
            tgt_rgb = tgt[..., :3]
            blended = tgt_rgb * (1.0 - feathered) + corrected_rgb * feathered
        else:
            tgt_rgb = tgt[..., :3]
            corrected_rgb = corrected_batch[..., :3]
            blended = tgt_rgb * (1.0 - strength) + corrected_rgb * strength

        if tgt.shape[-1] == 4:
            blended = torch.cat([blended, tgt[..., 3:4]], dim=-1)

        return (blended.clamp(0.0, 1.0),)
