from .server import api  # noqa: F401 - triggers route registration
from .nodes.selection_mask import RasterRelaySelectionMask
from .nodes.lora_stack import RasterRelayLoraStack
from .nodes.pad_to_document import RasterRelayPadToDocument
from .nodes.save_image_rgba import RasterRelaySaveImage
from .nodes.match_and_align import (
    RasterRelaySmartCropAligner,
    RasterRelaySmartCropTrimmer,
    RasterRelayVaeDriftMatch,
)
from .nodes.color_harmonize import RasterRelayColorHarmonize
from .nodes.color_match import RasterRelayColorMatch
from .nodes.grain_transfer import RasterRelayGrainTransfer
from .nodes.edge_harmonize import RasterRelayEdgeHarmonize
from .nodes.area_match import RasterRelayAreaMatch
from .nodes.mask_cropper import RasterRelayMaskCropper
from .nodes.background_preserve import RasterRelayBackgroundPreserve
from .nodes.seamless_tone import RasterRelaySeamlessTone
from .nodes.mask_edge_refine import RasterRelayMaskEdgeRefine
from .nodes.color_calibrate import RasterRelayColorCalibrate

NODE_CLASS_MAPPINGS = {
    "RasterRelaySelectionMask": RasterRelaySelectionMask,
    "RasterRelayLoraStack": RasterRelayLoraStack,
    "RasterRelayPadToDocument": RasterRelayPadToDocument,
    "RasterRelaySaveImage": RasterRelaySaveImage,
    "RasterRelaySmartCropAligner": RasterRelaySmartCropAligner,
    "RasterRelaySmartCropTrimmer": RasterRelaySmartCropTrimmer,
    "RasterRelayVaeDriftMatch": RasterRelayVaeDriftMatch,
    "RasterRelayGrainTransfer": RasterRelayGrainTransfer,
    "RasterRelayColorHarmonize": RasterRelayColorHarmonize,
    "RasterRelayColorMatch": RasterRelayColorMatch,
    "RasterRelayEdgeHarmonize": RasterRelayEdgeHarmonize,
    "RasterRelayAreaMatch": RasterRelayAreaMatch,
    "RasterRelayMaskCropper": RasterRelayMaskCropper,
    "RasterRelayBackgroundPreserve": RasterRelayBackgroundPreserve,
    "RasterRelaySeamlessTone": RasterRelaySeamlessTone,
    "RasterRelayMaskEdgeRefine": RasterRelayMaskEdgeRefine,
    "RasterRelayColorCalibrate": RasterRelayColorCalibrate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RasterRelaySelectionMask": "RasterRelay Selection Mask (biblioteka)",
    "RasterRelayLoraStack": "RasterRelay LoRA Stack",
    "RasterRelayPadToDocument": "RasterRelay Pad To Document",
    "RasterRelaySaveImage": "RasterRelay Save Image (RGBA)",
    "RasterRelaySmartCropAligner": "RasterRelay Smart Crop Aligner (biblioteka)",
    "RasterRelaySmartCropTrimmer": "RasterRelay Smart Crop Trimmer (biblioteka)",
    "RasterRelayVaeDriftMatch": "RasterRelay VAE Drift Match",
    "RasterRelayGrainTransfer": "RasterRelay Grain Transfer",
    "RasterRelayColorHarmonize": "RasterRelay Color Harmonize (biblioteka)",
    "RasterRelayColorMatch": "RasterRelay Color Match (biblioteka)",
    "RasterRelayEdgeHarmonize": "RasterRelay Edge Harmonize (biblioteka)",
    "RasterRelayAreaMatch": "RasterRelay Area Match (biblioteka)",
    "RasterRelayMaskCropper": "RasterRelay Mask Cropper (biblioteka)",
    "RasterRelayBackgroundPreserve": "RasterRelay Background Preserve",
    "RasterRelaySeamlessTone": "RasterRelay Seamless Tone",
    "RasterRelayMaskEdgeRefine": "RasterRelay Mask Edge Refine",
    "RasterRelayColorCalibrate": "RasterRelay Color Calibrate",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
