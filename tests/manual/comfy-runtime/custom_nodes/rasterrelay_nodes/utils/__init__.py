"""
Common mask processing utilities for RasterRelay nodes.
Provides shared functions for Gaussian blur, feathering, and mask manipulation.
"""

import torch
import torch.nn.functional as F


def gaussian_kernel(kernel_size, sigma):
    """
    Create a 1D Gaussian kernel.

    Args:
        kernel_size: Size of the kernel (should be odd)
        sigma: Standard deviation of the Gaussian

    Returns:
        1D tensor of shape (kernel_size,) containing the Gaussian kernel
    """
    x = torch.arange(kernel_size, dtype=torch.float32) - (kernel_size - 1) / 2
    kernel = torch.exp(-0.5 * (x / sigma) ** 2)
    kernel = kernel / kernel.sum()
    return kernel


def blur_mask(mask, blend_radius):
    """
    Apply separable Gaussian blur to a mask tensor.

    Args:
        mask: Mask tensor in BHWC format (batch, height, width, channels)
        blend_radius: Blur radius in pixels

    Returns:
        Blurred mask tensor in BHWC format
    """
    if blend_radius <= 0:
        return mask

    device = mask.device
    kernel_size = blend_radius * 6 + 1
    if kernel_size % 2 == 0:
        kernel_size += 1
    sigma = blend_radius / 3.0

    kernel = gaussian_kernel(kernel_size, sigma).to(device)

    m_bchw = mask.permute(0, 3, 1, 2)

    # Separable 1D Gaussian horizontal pass
    m_bchw = F.pad(m_bchw, (kernel_size // 2, kernel_size // 2, 0, 0), mode="replicate")
    kernel_h = kernel.view(1, 1, 1, kernel_size)
    m_bchw = F.conv2d(m_bchw, kernel_h, padding="valid")

    # Vertical pass
    m_bchw = F.pad(m_bchw, (0, 0, kernel_size // 2, kernel_size // 2), mode="replicate")
    kernel_v = kernel.view(1, 1, kernel_size, 1)
    m_bchw = F.conv2d(m_bchw, kernel_v, padding="valid")

    return m_bchw.permute(0, 2, 3, 1)


def apply_feathering(mask_tensor, feather_radius):
    """
    Apply Gaussian feathering to a mask tensor.

    Args:
        mask_tensor: Mask tensor in BHW format (batch, height, width)
        feather_radius: Feather radius in pixels

    Returns:
        Feathered mask tensor in BHW format
    """
    if feather_radius <= 0:
        return mask_tensor

    kernel_size = feather_radius * 6 + 1
    if kernel_size % 2 == 0:
        kernel_size += 1

    sigma = feather_radius / 3.0
    kernel = gaussian_kernel(kernel_size, sigma)

    mask = mask_tensor.unsqueeze(0)  # Add channel dimension: 1BHW
    kernel = kernel.view(1, 1, 1, kernel_size).to(mask.device)

    # Horizontal pass
    mask = F.pad(mask, (kernel_size // 2, kernel_size // 2, 0, 0), mode="replicate")
    mask = F.conv2d(mask, kernel, padding="valid")

    # Vertical pass
    kernel_v = kernel.view(1, 1, kernel_size, 1)
    mask = F.pad(mask, (0, 0, kernel_size // 2, kernel_size // 2), mode="replicate")
    mask = F.conv2d(mask, kernel_v, padding="valid")

    return mask.squeeze(0)  # Remove channel dimension: BHW
