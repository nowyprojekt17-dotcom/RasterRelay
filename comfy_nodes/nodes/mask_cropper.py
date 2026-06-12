class RasterRelayMaskCropper:
    """
    Crops a full-document MASK to the same crop rectangle as the source image.

    RasterRelay sends a cropped source image to the generation path, while the
    Photoshop visibility mask remains full-document sized. Generation and
    post-processing nodes need the mask in crop-local coordinates.
    """

    CATEGORY = "RasterRelay"
    RETURN_TYPES = ("MASK",)
    RETURN_NAMES = ("cropped_mask",)
    FUNCTION = "crop"
    DESCRIPTION = "Crops a full-document mask to crop-local coordinates."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "document_mask": ("MASK", {"tooltip": "Full document mask"}),
                "crop_left": ("INT", {"default": 0, "min": 0, "max": 16384}),
                "crop_top": ("INT", {"default": 0, "min": 0, "max": 16384}),
                "crop_width": ("INT", {"default": 512, "min": 1, "max": 16384}),
                "crop_height": ("INT", {"default": 512, "min": 1, "max": 16384}),
            }
        }

    def crop(self, document_mask, crop_left, crop_top, crop_width, crop_height):
        if crop_width <= 0 or crop_height <= 0:
            raise ValueError(f"RasterRelayMaskCropper: crop dimensions must be positive, got {crop_width}x{crop_height}")

        if crop_width > 16384 or crop_height > 16384:
            raise ValueError(f"RasterRelayMaskCropper: crop dimensions too large (max 16384), got {crop_width}x{crop_height}")

        if crop_left < 0 or crop_top < 0:
            raise ValueError(f"RasterRelayMaskCropper: crop offsets must be non-negative, got left={crop_left}, top={crop_top}")

        if document_mask.dim() == 2:
            document_mask = document_mask.unsqueeze(0)

        _, doc_h, doc_w = document_mask.shape

        # Clamp crop region to document bounds
        left = max(0, min(crop_left, doc_w))
        top = max(0, min(crop_top, doc_h))
        right = max(left, min(crop_left + crop_width, doc_w))
        bottom = max(top, min(crop_top + crop_height, doc_h))

        if right <= left or bottom <= top:
            raise ValueError(
                f"RasterRelayMaskCropper: crop region is outside document bounds. "
                f"Document: {doc_w}x{doc_h}, crop: left={crop_left}, top={crop_top}, "
                f"width={crop_width}, height={crop_height}"
            )

        cropped = document_mask[:, top:bottom, left:right]
        return (cropped,)
