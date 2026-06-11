import torch


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
                "alpha_mode": (["crop", "mask"], {
                    "default": "crop",
                    "tooltip": "crop = whole generated crop is present in the layer; mask = PNG alpha follows selection mask",
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

    def pad(self, image, mask, crop_left, crop_top, crop_width, crop_height, doc_width, doc_height, alpha_mode="crop"):
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
        if alpha_mode == "mask":
            mask_alpha = self._resize_mask(
                mask,
                target_crop_width,
                target_crop_height,
                batch_size,
                image.device,
                image.dtype,
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
        del image, image_rgb, mask_alpha
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return (padded,)
