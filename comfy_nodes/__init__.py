from .server import api  # noqa: F401 - triggers route registration
from .nodes.selection_mask import RasterRelaySelectionMask
from .nodes.lora_stack import RasterRelayLoraStack
from .nodes.pad_to_document import RasterRelayPadToDocument
from .nodes.save_image_rgba import RasterRelaySaveImage
from .nodes.match_and_align import (
    RasterRelaySmartCropAligner,
    RasterRelaySmartCropTrimmer,
    RasterRelayVaeDriftMatch,
    RasterRelayGrainInjector,
)

NODE_CLASS_MAPPINGS = {
    "RasterRelaySelectionMask": RasterRelaySelectionMask,
    "RasterRelayLoraStack": RasterRelayLoraStack,
    "RasterRelayPadToDocument": RasterRelayPadToDocument,
    "RasterRelaySaveImage": RasterRelaySaveImage,
    "RasterRelaySmartCropAligner": RasterRelaySmartCropAligner,
    "RasterRelaySmartCropTrimmer": RasterRelaySmartCropTrimmer,
    "RasterRelayVaeDriftMatch": RasterRelayVaeDriftMatch,
    "RasterRelayGrainInjector": RasterRelayGrainInjector,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RasterRelaySelectionMask": "RasterRelay Selection Mask",
    "RasterRelayLoraStack": "RasterRelay LoRA Stack",
    "RasterRelayPadToDocument": "RasterRelay Pad To Document",
    "RasterRelaySaveImage": "RasterRelay Save Image (RGBA)",
    "RasterRelaySmartCropAligner": "RasterRelay Smart Crop Aligner",
    "RasterRelaySmartCropTrimmer": "RasterRelay Smart Crop Trimmer",
    "RasterRelayVaeDriftMatch": "RasterRelay VAE Drift Match",
    "RasterRelayGrainInjector": "RasterRelay Grain Injector",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
