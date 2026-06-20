import torch
import torch.nn.functional as F


class RasterRelayPadToDocument:
    """
    Composites a cropped generated image back to the original document size.
    The generated crop is resized to the exact requested crop dimensions if a
    model rounded it to its internal grid. By default alpha covers the whole crop
    rectangle so Photoshop's layer mask, not the PNG transparency, controls the
    visible selection shape.
    """
    CATEGORY = "RasterRelay"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "pad"
    DESCRIPTION = "Pads a cropped image to full document dimensions at the correct offset."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {"tooltip": "The generated (cropped) image to pad"}),
                "mask": ("MASK", {"tooltip": "Selection mask for the generated crop"}),
                "crop_left": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 16384,
                    "tooltip": "Left offset where the cropped region was taken from",
                }),
                "crop_top": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 16384,
                    "tooltip": "Top offset where the cropped region was taken from",
                }),
                "crop_width": ("INT", {
                    "default": 1920,
                    "min": 1,
                    "max": 16384,
                    "tooltip": "Exact crop width expected by Photoshop",
                }),
                "crop_height": ("INT", {
                    "default": 1080,
                    "min": 1,
                    "max": 16384,
                    "tooltip": "Exact crop height expected by Photoshop",
                }),
                "doc_width": ("INT", {
                    "default": 1920,
                    "min": 1,
                    "max": 16384,
                    "tooltip": "Original document width in pixels",
                }),
                "doc_height": ("INT", {
                    "default": 1080,
                    "min": 1,
                    "max": 16384,
                    "tooltip": "Original document height in pixels",
                }),
            },
            "optional": {
                "alpha_mode": (["crop", "mask", "change"], {
                    "default": "crop",
                    "tooltip": "crop = whole generated crop is present; mask = alpha follows selection; change = alpha follows actual pixel changes vs original",
                }),
                "original_image": ("IMAGE", {
                    "tooltip": "Original crop, used only by alpha_mode=change",
                }),
                "change_threshold": ("FLOAT", {
                    "default": 0.012,
                    "min": 0.0,
                    "max": 0.25,
                    "step": 0.001,
                    "tooltip": "RGB delta below this is hidden in change-alpha mode.",
                }),
                "change_transition_width": ("FLOAT", {
                    "default": 0.012,
                    "min": 0.001,
                    "max": 0.1,
                    "step": 0.001,
                    "tooltip": "Soft transition width for change-alpha mode.",
                }),
                "alpha_grow": ("INT", {
                    "default": 4,
                    "min": 0,
                    "max": 64,
                    "step": 1,
                    "tooltip": "Dilates changed alpha so edited interiors remain covered.",
                }),
                "alpha_feather": ("INT", {
                    "default": 3,
                    "min": 0,
                    "max": 64,
                    "step": 1,
                    "tooltip": "Feathers the generated change alpha.",
                }),
                "precompensate_alpha_composite": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Adjust PNG RGB so alpha compositing over the original recreates the locked crop colours.",
                }),
                "force_opaque_for_composite_lock": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "When a requested composite colour cannot be represented through partial alpha, make that pixel opaque.",
                }),
            },
        }

    @staticmethod
    def _resize_image(image, width, height):
        if image.shape[1] == height and image.shape[2] == width:
            return image

        channels_first = image.permute(0, 3, 1, 2)
        resized = torch.nn.functional.interpolate(
            channels_first,
            size=(height, width),
            mode="bilinear",
            align_corners=False,
        )
        return resized.permute(0, 2, 3, 1)

    @staticmethod
    def _resize_mask(mask, width, height, batch_size, device, dtype):
        if mask.dim() == 2:
            mask = mask.unsqueeze(0)
        if mask.dim() == 3:
            mask = mask.unsqueeze(1)

        mask = mask.to(device=device, dtype=dtype)
        if mask.shape[0] == 1 and batch_size > 1:
            mask = mask.repeat(batch_size, 1, 1, 1)

        if mask.shape[-2] != height or mask.shape[-1] != width:
            mask = torch.nn.functional.interpolate(
                mask,
                size=(height, width),
                mode="bilinear",
                align_corners=False,
            )

        return mask.squeeze(1).clamp(0.0, 1.0)

    @staticmethod
    def _blur_mask(mask_bhw, radius):
        if radius <= 0:
            return mask_bhw
        radius = int(radius)
        kernel_size = max(3, radius * 6 + 1)
        if kernel_size % 2 == 0:
            kernel_size += 1
        sigma = max(radius / 3.0, 0.5)
        x = torch.arange(kernel_size, dtype=torch.float32, device=mask_bhw.device) - (kernel_size - 1) / 2
        kernel = torch.exp(-0.5 * (x / sigma) ** 2)
        kernel = kernel / kernel.sum()
        m = mask_bhw.unsqueeze(1)
        pad = kernel_size // 2
        m = F.pad(m, (pad, pad, 0, 0), mode="replicate")
        m = F.conv2d(m, kernel.view(1, 1, 1, kernel_size))
        m = F.pad(m, (0, 0, pad, pad), mode="replicate")
        m = F.conv2d(m, kernel.view(1, 1, kernel_size, 1))
        return m.squeeze(1).clamp(0.0, 1.0)

    def _change_alpha(
        self,
        image_rgb,
        original_image,
        mask,
        width,
        height,
        change_threshold,
        change_transition_width,
        alpha_grow,
        alpha_feather,
    ):
        if original_image is None:
            return self._resize_mask(mask, width, height, image_rgb.shape[0], image_rgb.device, image_rgb.dtype)

        original = original_image.to(device=image_rgb.device, dtype=image_rgb.dtype)
        original = self._resize_image(original, width, height)[..., :image_rgb.shape[-1]]
        selection = self._resize_mask(mask, width, height, image_rgb.shape[0], image_rgb.device, image_rgb.dtype)
        delta = (image_rgb - original).abs().amax(dim=-1)
        softness = max(float(change_transition_width), 1e-4)
        alpha = torch.sigmoid((delta - float(change_threshold)) / softness)
        alpha = torch.where(
            delta <= float(change_threshold) - 2.5 * softness,
            torch.zeros_like(alpha),
            alpha,
        )
        alpha = torch.where(
            delta >= float(change_threshold) + 2.5 * softness,
            torch.ones_like(alpha),
            alpha,
        )
        alpha = alpha * selection
        if alpha_grow > 0:
            k = 2 * int(alpha_grow) + 1
            alpha = F.max_pool2d(alpha.unsqueeze(1), kernel_size=k, stride=1, padding=k // 2).squeeze(1)
            alpha = alpha * selection
        alpha = self._blur_mask(alpha, int(alpha_feather)) * selection
        return alpha.clamp(0.0, 1.0)

    def _original_rgb(self, original_image, image_rgb, width, height):
        if original_image is None:
            return None
        original = original_image.to(device=image_rgb.device, dtype=image_rgb.dtype)
        return self._resize_image(original, width, height)[..., :image_rgb.shape[-1]]

    @staticmethod
    def _precompensate_alpha_composite(image_rgb, original_rgb, alpha, force_opaque):
        if original_rgb is None:
            return image_rgb, alpha

        alpha_u8 = (alpha.clamp(0.0, 1.0) * 255.0).round()
        positive = alpha_u8 > 0
        if not positive.any():
            return original_rgb, alpha_u8 / 255.0

        original_u8 = (original_rgb.clamp(0.0, 1.0) * 255.0).round()
        desired_u8 = (image_rgb.clamp(0.0, 1.0) * 255.0).round()
        alpha_u8_nhwc = alpha_u8.unsqueeze(-1)
        positive_nhwc = positive.unsqueeze(-1)
        safe_alpha = alpha_u8_nhwc.clamp(min=1.0)
        raw_u8 = ((desired_u8 * 255.0 - original_u8 * (255.0 - alpha_u8_nhwc)) / safe_alpha).round()
        raw_u8_clamped = raw_u8.clamp(0.0, 255.0)
        simulated = ((raw_u8_clamped * alpha_u8_nhwc + original_u8 * (255.0 - alpha_u8_nhwc)) / 255.0).round()
        exact = ((simulated - desired_u8).abs() <= 0.0).all(dim=-1)

        if force_opaque:
            force = positive & ~exact
            if force.any():
                alpha_u8 = torch.where(force, torch.full_like(alpha_u8, 255.0), alpha_u8)
                alpha_u8_nhwc = alpha_u8.unsqueeze(-1)
                raw_u8_clamped = torch.where(force.unsqueeze(-1), desired_u8, raw_u8_clamped)

        raw_rgb = raw_u8_clamped / 255.0
        rgb = torch.where(positive_nhwc, raw_rgb, original_u8 / 255.0)
        return rgb.clamp(0.0, 1.0), (alpha_u8 / 255.0).clamp(0.0, 1.0)

    def pad(
        self,
        image,
        mask,
        crop_left,
        crop_top,
        crop_width,
        crop_height,
        doc_width,
        doc_height,
        alpha_mode="crop",
        original_image=None,
        change_threshold=0.012,
        change_transition_width=0.012,
        alpha_grow=4,
        alpha_feather=3,
        precompensate_alpha_composite=False,
        force_opaque_for_composite_lock=True,
    ):
        # Walidacja parametrów
        if crop_left < 0 or crop_top < 0:
            raise ValueError(f"RasterRelayPadToDocument: crop offsets must be non-negative, got left={crop_left}, top={crop_top}")
        if crop_width <= 0 or crop_height <= 0:
            raise ValueError(f"RasterRelayPadToDocument: crop dimensions must be positive, got {crop_width}x{crop_height}")
        if crop_left + crop_width > doc_width or crop_top + crop_height > doc_height:
            raise ValueError(f"RasterRelayPadToDocument: crop region exceeds document bounds. Doc: {doc_width}x{doc_height}, crop: {crop_left},{crop_top}+{crop_width}x{crop_height}")

        batch_size, _img_h, _img_w, channels = image.shape
        rgb_channels = min(3, channels)
        target_crop_width = max(1, int(crop_width))
        target_crop_height = max(1, int(crop_height))
        image = self._resize_image(image, target_crop_width, target_crop_height)
        image_rgb = image[:, :, :, :rgb_channels]
        mask_alpha = None
        original_rgb = None
        if alpha_mode == "mask":
            mask_alpha = self._resize_mask(
                mask,
                target_crop_width,
                target_crop_height,
                batch_size,
                image.device,
                image.dtype,
            )
        elif alpha_mode == "change":
            mask_alpha = self._change_alpha(
                image_rgb,
                original_image,
                mask,
                target_crop_width,
                target_crop_height,
                change_threshold,
                change_transition_width,
                alpha_grow,
                alpha_feather,
            )
            original_rgb = self._original_rgb(original_image, image_rgb, target_crop_width, target_crop_height)
            if original_rgb is not None:
                alpha_visible = (mask_alpha > (0.5 / 255.0)).unsqueeze(-1)
                image_rgb = torch.where(alpha_visible, image_rgb, original_rgb)
                if precompensate_alpha_composite:
                    image_rgb, mask_alpha = self._precompensate_alpha_composite(
                        image_rgb,
                        original_rgb,
                        mask_alpha,
                        bool(force_opaque_for_composite_lock),
                    )

        padded = torch.zeros((batch_size, doc_height, doc_width, 4), dtype=image.dtype, device=image.device)

        paste_w = min(target_crop_width, doc_width - crop_left)
        paste_h = min(target_crop_height, doc_height - crop_top)

        if paste_w > 0 and paste_h > 0:
            padded[:, crop_top:crop_top + paste_h, crop_left:crop_left + paste_w, :rgb_channels] = image_rgb[:, :paste_h, :paste_w, :]
            if mask_alpha is None:
                padded[:, crop_top:crop_top + paste_h, crop_left:crop_left + paste_w, 3] = 1.0
            else:
                padded[:, crop_top:crop_top + paste_h, crop_left:crop_left + paste_w, 3] = mask_alpha[:, :paste_h, :paste_w]

        # Zwolnij pamięć GPU po dużych operacjach
        del image, image_rgb, mask_alpha, original_rgb
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return (padded,)
