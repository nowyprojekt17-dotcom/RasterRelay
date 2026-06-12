import base64
import numpy as np
import torch

# Try relative import first (when loaded as part of package),
# fall back to local implementation (when loaded directly in tests)
try:
    from ..utils.mask_processing import gaussian_kernel as _shared_gaussian_kernel
    def _gaussian_kernel_local(kernel_size, sigma):
        return _shared_gaussian_kernel(kernel_size, sigma)
except (ImportError, SystemError):
    def _gaussian_kernel_local(kernel_size, sigma):
        """Create a 1D Gaussian kernel."""
        x = torch.arange(kernel_size, dtype=torch.float32) - (kernel_size - 1) / 2
        kernel = torch.exp(-0.5 * (x / sigma) ** 2)
        kernel = kernel / kernel.sum()
        return kernel


class RasterRelaySelectionMask:
    """
    Creates a MASK tensor from raw Photoshop selection pixel data.
    Handles feathering on GPU via PyTorch convolutions.

    Example:
        >>> node = RasterRelaySelectionMask()
        >>> mask = node.create_mask(
        ...     selection_pixels=base64_data,
        ...     sel_width=256, sel_height=256,
        ...     mask_width=1024, mask_height=1024,
        ...     sel_left=100, sel_top=50,
        ...     feather=12
        ... )
        # Returns MASK tensor ready for ComfyUI workflow
    """
    CATEGORY = "RasterRelay"
    RETURN_TYPES = ("MASK",)
    RETURN_NAMES = ("mask",)
    FUNCTION = "create_mask"
    DESCRIPTION = "Creates a MASK tensor from raw selection pixel data with GPU feathering."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "selection_pixels": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "tooltip": "Base64-encoded uint8 array of selection mask values (0-255)",
                }),
                "sel_width": ("INT", {
                    "default": 256,
                    "min": 1,
                    "max": 16384,
                    "tooltip": "Width of the raw selection in pixels",
                }),
                "sel_height": ("INT", {
                    "default": 256,
                    "min": 1,
                    "max": 16384,
                    "tooltip": "Height of the raw selection in pixels",
                }),
                "mask_width": ("INT", {
                    "default": 1024,
                    "min": 1,
                    "max": 16384,
                    "tooltip": "Width of the output padded mask",
                }),
                "mask_height": ("INT", {
                    "default": 1024,
                    "min": 1,
                    "max": 16384,
                    "tooltip": "Height of the output padded mask",
                }),
                "sel_left": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 16384,
                    "tooltip": "X offset of selection within padded mask",
                }),
                "sel_top": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 16384,
                    "tooltip": "Y offset of selection within padded mask",
                }),
                "feather": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 256,
                    "tooltip": "Feather radius in pixels (0 = no feather)",
                }),
            }
        }

    def create_mask(
        self,
        selection_pixels,
        sel_width,
        sel_height,
        mask_width,
        mask_height,
        sel_left,
        sel_top,
        feather,
    ):
        # Decode base64 selection data
        sel_array = np.frombuffer(base64.b64decode(selection_pixels), dtype=np.uint8)
        if len(sel_array) != sel_width * sel_height:
            raise ValueError(
                f"Selection pixel count {len(sel_array)} != {sel_width}x{sel_height} = {sel_width * sel_height}"
            )

        # Reshape to 2D selection image, normalize to [0, 1]
        sel_2d = sel_array.reshape(sel_height, sel_width).astype(np.float32) / 255.0

        # Create full padded mask (all zeros = black)
        full_mask = np.zeros((mask_height, mask_width), dtype=np.float32)

        # Place selection at correct offset
        end_y = min(sel_top + sel_height, mask_height)
        end_x = min(sel_left + sel_width, mask_width)
        sel_end_y = end_y - sel_top
        sel_end_x = end_x - sel_left

        if sel_end_y > 0 and sel_end_x > 0:
            full_mask[sel_top:end_y, sel_left:end_x] = sel_2d[:sel_end_y, :sel_end_x]

        # Convert to PyTorch tensor (BHW format for MASK)
        mask = torch.from_numpy(full_mask).unsqueeze(0)

        # Apply feathering if requested
        if feather > 0:
            kernel_size = feather * 6 + 1
            if kernel_size % 2 == 0:
                kernel_size += 1

            sigma = feather / 3.0
            kernel = _gaussian_kernel_local(kernel_size, sigma)

            mask = mask.unsqueeze(0)
            kernel = kernel.view(1, 1, 1, kernel_size).to(mask.device)

            # Horizontal pass
            mask = torch.nn.functional.pad(mask, (kernel_size // 2, kernel_size // 2, 0, 0), mode="replicate")
            mask = torch.nn.functional.conv2d(mask, kernel, padding="valid")

            # Vertical pass
            kernel_v = kernel.view(1, 1, kernel_size, 1)
            mask = torch.nn.functional.pad(mask, (0, 0, kernel_size // 2, kernel_size // 2), mode="replicate")
            mask = torch.nn.functional.conv2d(mask, kernel_v, padding="valid")

            mask = mask.squeeze(0)

        return (mask,)
